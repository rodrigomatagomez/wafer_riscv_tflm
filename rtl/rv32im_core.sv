// RV32IM multicycle core.
//
// Memory interface (documented here and in docs/findings.md): a simple
// request/response bus. The core asserts mem_req_valid with address/we/
// wstrb/wdata held stable and waits for mem_req_ready (request accepted)
// before deasserting; it then waits for a later mem_resp_valid pulse
// carrying mem_resp_rdata (reads) or mem_resp_err (fault) before
// proceeding. Both reads and writes always use a word-aligned address;
// sub-word placement (byte/halfword lane selection, sign/zero extension)
// is done entirely on the core side via wstrb (writes) and byte-offset
// extraction (reads) — the memory behind this interface only ever
// stores/returns whole 32-bit words.
//
// Execution-environment policy (prompt Section 5): misaligned halfword/word
// accesses, illegal instructions, out-of-range memory accesses, and
// ECALL/EBREAK all transition to a terminal S_ERR state that holds the
// faulting PC, instruction, and a cause code for observation. There is no
// NOP fallback for anything not explicitly decoded as a legal RV32IM
// encoding. FENCE (the only MISC-MEM encoding accepted) is treated as a
// pure pc+4 no-op, matching the prompt's note that FENCE may complete
// without additional effects in this simple sequential environment.
import rv32im_pkg::*;

module rv32im_core (
    input  logic        clk,
    input  logic        rst,

    output logic        mem_req_valid,
    output logic [31:0] mem_req_addr,
    output logic        mem_req_we,
    output logic [3:0]  mem_req_wstrb,
    output logic [31:0] mem_req_wdata,
    input  logic        mem_req_ready,
    input  logic        mem_resp_valid,
    input  logic        mem_resp_err,
    input  logic [31:0] mem_resp_rdata,

    output logic        err_halt,
    output err_cause_e  err_cause,
    output logic [31:0] err_pc,
    output logic [31:0] err_instr,

    // Retirement trace port (one pulse per instruction that reaches
    // writeback), used by tb/ to build the retired-instruction log that is
    // compared against the Python ISA reference model (docs/findings.md).
    // Includes the actual register write (if any) so the comparison covers
    // real architectural state, not just the (pc, instr) control-flow
    // skeleton.
    output logic        retire_valid,
    output logic [31:0] retire_pc,
    output logic [31:0] retire_instr,
    output logic        retire_reg_we,
    output logic [4:0]  retire_rd_addr,
    output logic [31:0] retire_rd_wdata
);
  typedef enum logic [3:0] {
    S_RESET, S_FETCH, S_FETCH_WAIT, S_DECODE, S_EXECUTE,
    S_MULDIV, S_MEM_ADDR, S_MEM_WAIT, S_WRITEBACK, S_ERR
  } state_e;
  state_e state;

  logic [31:0] pc;
  logic [31:0] instr;
  logic [31:0] load_data_reg;

  // ---- decode (pure combinational function of `instr`) ----
  logic [6:0] opcode;
  logic [2:0] funct3;
  logic [6:0] funct7;
  logic [4:0] rd_addr, rs1_addr, rs2_addr;
  assign opcode   = instr[6:0];
  assign funct3   = instr[14:12];
  assign funct7   = instr[31:25];
  assign rd_addr  = instr[11:7];
  assign rs1_addr = instr[19:15];
  assign rs2_addr = instr[24:20];

  logic [31:0] imm_i, imm_s, imm_b, imm_u, imm_j;
  assign imm_i = {{20{instr[31]}}, instr[31:20]};
  assign imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
  assign imm_b = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
  assign imm_u = {instr[31:12], 12'b0};
  assign imm_j = {{11{instr[31]}}, instr[31], instr[19:12], instr[20], instr[30:21], 1'b0};

  logic is_load, is_store, is_branch, is_jal, is_jalr, is_lui, is_auipc;
  logic is_op, is_op_imm, is_fence, is_system, is_muldiv;
  assign is_load    = (opcode == OPC_LOAD);
  assign is_store   = (opcode == OPC_STORE);
  assign is_branch  = (opcode == OPC_BRANCH);
  assign is_jal     = (opcode == OPC_JAL);
  assign is_jalr    = (opcode == OPC_JALR);
  assign is_lui     = (opcode == OPC_LUI);
  assign is_auipc   = (opcode == OPC_AUIPC);
  assign is_op      = (opcode == OPC_OP);
  assign is_op_imm  = (opcode == OPC_OP_IMM);
  assign is_fence   = (opcode == OPC_MISC_MEM);
  assign is_system  = (opcode == OPC_SYSTEM);
  assign is_muldiv  = is_op && (funct7 == F7_MULDIV);

  // ---- illegal-instruction detection ----
  logic illegal;
  always_comb begin
    unique case (opcode)
      OPC_LOAD:     illegal = !(funct3 inside {F3_B, F3_H, F3_W, F3_BU, F3_HU});
      OPC_MISC_MEM: illegal = (funct3 != 3'b000);
      OPC_OP_IMM: begin
        if (funct3 == F3_SLL)
          illegal = (funct7 != F7_BASE);
        else if (funct3 == F3_SRL_SRA)
          illegal = !(funct7 == F7_BASE || funct7 == F7_ALT);
        else
          illegal = 1'b0;
      end
      OPC_AUIPC: illegal = 1'b0;
      OPC_STORE:    illegal = !(funct3 inside {F3_B, F3_H, F3_W});
      OPC_OP: begin
        if (funct7 == F7_MULDIV) illegal = 1'b0;
        else if (funct7 == F7_BASE) illegal = 1'b0;
        else if (funct7 == F7_ALT) illegal = !(funct3 == F3_ADD_SUB || funct3 == F3_SRL_SRA);
        else illegal = 1'b1;
      end
      OPC_LUI: illegal = 1'b0;
      OPC_BRANCH: illegal = (funct3 == 3'b010) || (funct3 == 3'b011);
      OPC_JALR: illegal = (funct3 != 3'b000);
      OPC_JAL: illegal = 1'b0;
      OPC_SYSTEM:
        illegal = !(funct3 == 3'b000 && rd_addr == 5'b0 && rs1_addr == 5'b0
                     && (instr[31:20] == IMM_ECALL || instr[31:20] == IMM_EBREAK));
      default: illegal = 1'b1;
    endcase
  end
  logic is_ecall, is_ebreak;
  assign is_ecall  = is_system && (instr[31:20] == IMM_ECALL);
  assign is_ebreak = is_system && (instr[31:20] == IMM_EBREAK);

  // ---- register file ----
  logic [31:0] rs1_data, rs2_data;
  logic        reg_we; // combinational; see assignment near pc_misaligned below
  logic [31:0] rd_wdata;
  rv32im_regfile u_regfile (
      .clk(clk), .rst(rst),
      .rs1_addr(rs1_addr), .rs2_addr(rs2_addr),
      .rs1_data(rs1_data), .rs2_data(rs2_data),
      .we(reg_we), .rd_addr(rd_addr), .rd_data(rd_wdata)
  );

  // ---- ALU (reused as the address/target adder too) ----
  logic [31:0] alu_a, alu_b, alu_result;
  alu_op_e     alu_op;
  rv32im_alu u_alu (.a(alu_a), .b(alu_b), .op(alu_op), .result(alu_result));

  always_comb begin
    alu_a  = rs1_data;
    alu_b  = imm_i;
    alu_op = ALU_ADD;
    unique case (opcode)
      OPC_OP: begin
        alu_a = rs1_data; alu_b = rs2_data;
        unique case (funct3)
          F3_ADD_SUB: alu_op = (funct7 == F7_ALT) ? ALU_SUB : ALU_ADD;
          F3_SLL:     alu_op = ALU_SLL;
          F3_SLT:     alu_op = ALU_SLT;
          F3_SLTU:    alu_op = ALU_SLTU;
          F3_XOR:     alu_op = ALU_XOR;
          F3_SRL_SRA: alu_op = (funct7 == F7_ALT) ? ALU_SRA : ALU_SRL;
          F3_OR:      alu_op = ALU_OR;
          F3_AND:     alu_op = ALU_AND;
          default:    alu_op = ALU_ADD;
        endcase
      end
      OPC_OP_IMM: begin
        alu_a = rs1_data; alu_b = imm_i;
        unique case (funct3)
          F3_ADD_SUB: alu_op = ALU_ADD;
          F3_SLL:     alu_op = ALU_SLL;
          F3_SLT:     alu_op = ALU_SLT;
          F3_SLTU:    alu_op = ALU_SLTU;
          F3_XOR:     alu_op = ALU_XOR;
          F3_SRL_SRA: alu_op = instr[30] ? ALU_SRA : ALU_SRL;
          F3_OR:      alu_op = ALU_OR;
          F3_AND:     alu_op = ALU_AND;
          default:    alu_op = ALU_ADD;
        endcase
      end
      OPC_LOAD:   begin alu_a = rs1_data; alu_b = imm_i; alu_op = ALU_ADD; end
      OPC_STORE:  begin alu_a = rs1_data; alu_b = imm_s; alu_op = ALU_ADD; end
      OPC_JALR:   begin alu_a = rs1_data; alu_b = imm_i; alu_op = ALU_ADD; end
      OPC_AUIPC:  begin alu_a = pc;       alu_b = imm_u; alu_op = ALU_ADD; end
      OPC_LUI:    begin alu_a = 32'b0;    alu_b = imm_u; alu_op = ALU_PASSB; end
      OPC_BRANCH: begin alu_a = pc;       alu_b = imm_b; alu_op = ALU_ADD; end
      OPC_JAL:    begin alu_a = pc;       alu_b = imm_j; alu_op = ALU_ADD; end
      default:    begin alu_a = 32'b0;    alu_b = 32'b0; alu_op = ALU_ADD; end
    endcase
  end

  // ---- M-extension unit ----
  logic        md_start, md_busy, md_done;
  logic [31:0] md_result;
  muldiv_op_e  md_op;
  assign md_op = muldiv_op_e'(funct3);
  assign md_start = (state == S_EXECUTE) && is_muldiv;
  rv32im_muldiv u_muldiv (
      .clk(clk), .rst(rst), .start(md_start), .op(md_op),
      .rs1(rs1_data), .rs2(rs2_data),
      .busy(md_busy), .done(md_done), .result(md_result)
  );

  // ---- branch condition ----
  logic branch_taken;
  always_comb begin
    unique case (funct3)
      F3_BEQ:  branch_taken = (rs1_data == rs2_data);
      F3_BNE:  branch_taken = (rs1_data != rs2_data);
      F3_BLT:  branch_taken = ($signed(rs1_data) <  $signed(rs2_data));
      F3_BGE:  branch_taken = ($signed(rs1_data) >= $signed(rs2_data));
      F3_BLTU: branch_taken = (rs1_data <  rs2_data);
      F3_BGEU: branch_taken = (rs1_data >= rs2_data);
      default: branch_taken = 1'b0;
    endcase
  end

  // ---- load/store address, size, sign, and byte-lane handling ----
  logic [1:0]  byte_offset;
  logic [1:0]  ls_size;      // 00=byte, 01=half, 10=word
  logic        ls_unsigned;
  logic        ls_misaligned;
  assign byte_offset = alu_result[1:0];
  assign ls_size      = funct3[1:0];
  assign ls_unsigned  = funct3[2];
  assign ls_misaligned = (ls_size == 2'b01 && byte_offset[0] != 1'b0) ||
                         (ls_size == 2'b10 && byte_offset != 2'b00);

  logic [31:0] store_wdata_word;
  logic [3:0]  store_wstrb;
  always_comb begin
    unique case (ls_size)
      2'b00: begin store_wstrb = 4'b0001 << byte_offset; store_wdata_word = {4{rs2_data[7:0]}}; end
      2'b01: begin store_wstrb = 4'b0011 << byte_offset; store_wdata_word = {2{rs2_data[15:0]}}; end
      default: begin store_wstrb = 4'b1111; store_wdata_word = rs2_data; end
    endcase
  end

  logic [31:0] load_extracted;
  always_comb begin
    unique case (funct3)
      F3_B:  load_extracted = {{24{load_data_reg[8*byte_offset+7]}}, load_data_reg[8*byte_offset +: 8]};
      F3_BU: load_extracted = {24'b0, load_data_reg[8*byte_offset +: 8]};
      F3_H:  load_extracted = {{16{load_data_reg[16*byte_offset[1]+15]}}, load_data_reg[16*byte_offset[1] +: 16]};
      F3_HU: load_extracted = {16'b0, load_data_reg[16*byte_offset[1] +: 16]};
      default: load_extracted = load_data_reg;
    endcase
  end

  // ---- next-PC and register writeback muxes ----
  logic [31:0] next_pc_candidate;
  logic        reg_writes;
  logic [31:0] rd_wdata_mux;
  always_comb begin
    unique case (1'b1)
      is_jal:  next_pc_candidate = alu_result;              // pc + imm_j
      is_jalr: next_pc_candidate = {alu_result[31:1], 1'b0}; // (rs1+imm_i) & ~1
      (is_branch && branch_taken): next_pc_candidate = alu_result; // pc + imm_b
      default: next_pc_candidate = pc + 32'd4;
    endcase

    reg_writes = is_op || is_op_imm || is_lui || is_auipc || is_jal || is_jalr || is_load;

    unique case (1'b1)
      is_load:            rd_wdata_mux = load_extracted;
      (is_jal || is_jalr): rd_wdata_mux = pc + 32'd4;
      is_muldiv:           rd_wdata_mux = md_result;
      default:             rd_wdata_mux = alu_result;
    endcase
  end
  assign rd_wdata = rd_wdata_mux;

  logic pc_misaligned;
  assign pc_misaligned = (next_pc_candidate[1:0] != 2'b00);

  // reg_we MUST be combinational (not registered through the FSM), so that
  // the register file — which samples `we`/`rd_data` on the very same clock
  // edge the FSM uses to advance `pc` and leave S_WRITEBACK — captures the
  // write using the *current* (pre-edge) pc/instr-derived rd_wdata. An
  // earlier draft set this via a registered `reg_we <= ...` inside the FSM,
  // which would have delayed the actual write by one cycle into S_FETCH,
  // by which point `pc` had already advanced — silently corrupting the
  // link register value written by JAL/JALR (pc+4 using the *new* pc).
  assign reg_we = (state == S_WRITEBACK) && !pc_misaligned && reg_writes;

  // ---- memory request driving ----
  logic [31:0] ls_word_addr;
  assign ls_word_addr = {alu_result[31:2], 2'b00};

  always_comb begin
    mem_req_valid = 1'b0;
    mem_req_addr  = 32'b0;
    mem_req_we    = 1'b0;
    mem_req_wstrb = 4'b0000;
    mem_req_wdata = 32'b0;
    unique case (state)
      S_FETCH: begin
        mem_req_valid = 1'b1;
        mem_req_addr  = pc;
        mem_req_we    = 1'b0;
      end
      S_MEM_ADDR: begin
        mem_req_valid = 1'b1;
        mem_req_addr  = ls_word_addr;
        mem_req_we    = is_store;
        mem_req_wstrb = is_store ? store_wstrb : 4'b0000;
        mem_req_wdata = store_wdata_word;
      end
      default: ;
    endcase
  end

  // ---- retirement trace (pulses once per instruction, in S_WRITEBACK,
  // for every instruction that is about to successfully commit) ----
  assign retire_valid    = (state == S_WRITEBACK);
  assign retire_pc       = pc;
  assign retire_instr    = instr;
  assign retire_reg_we   = reg_we;
  assign retire_rd_addr  = rd_addr;
  assign retire_rd_wdata = rd_wdata;

  // ---- main FSM ----
  always_ff @(posedge clk) begin
    if (rst) begin
      state     <= S_RESET;
      pc        <= 32'b0;
      err_halt  <= 1'b0;
      err_cause <= ERR_NONE;
      err_pc    <= 32'b0;
      err_instr <= 32'b0;
    end else begin
      unique case (state)
        S_RESET: state <= S_FETCH;

        S_FETCH: begin
          if (mem_req_ready) state <= S_FETCH_WAIT;
        end

        S_FETCH_WAIT: begin
          if (mem_resp_valid) begin
            if (mem_resp_err) begin
              state     <= S_ERR;
              err_cause <= ERR_OUT_OF_RANGE;
              err_pc    <= pc;
              err_instr <= 32'b0;
              err_halt  <= 1'b1;
            end else begin
              instr <= mem_resp_rdata;
              state <= S_DECODE;
            end
          end
        end

        S_DECODE: begin
          if (illegal) begin
            state     <= S_ERR;
            err_cause <= ERR_ILLEGAL_INSTR;
            err_pc    <= pc;
            err_instr <= instr;
            err_halt  <= 1'b1;
          end else if (is_ecall) begin
            state     <= S_ERR;
            err_cause <= ERR_ECALL;
            err_pc    <= pc;
            err_instr <= instr;
            err_halt  <= 1'b1;
          end else if (is_ebreak) begin
            state     <= S_ERR;
            err_cause <= ERR_EBREAK;
            err_pc    <= pc;
            err_instr <= instr;
            err_halt  <= 1'b1;
          end else begin
            state <= S_EXECUTE;
          end
        end

        S_EXECUTE: begin
          if (is_muldiv) begin
            state <= S_MULDIV;
          end else if (is_load || is_store) begin
            if (ls_misaligned) begin
              state     <= S_ERR;
              err_cause <= is_load ? ERR_MISALIGNED_LD : ERR_MISALIGNED_ST;
              err_pc    <= pc;
              err_instr <= instr;
              err_halt  <= 1'b1;
            end else begin
              state <= S_MEM_ADDR;
            end
          end else begin
            state <= S_WRITEBACK;
          end
        end

        S_MULDIV: begin
          if (md_done) state <= S_WRITEBACK;
        end

        S_MEM_ADDR: begin
          if (mem_req_ready) state <= S_MEM_WAIT;
        end

        S_MEM_WAIT: begin
          if (mem_resp_valid) begin
            if (mem_resp_err) begin
              state     <= S_ERR;
              err_cause <= ERR_OUT_OF_RANGE;
              err_pc    <= pc;
              err_instr <= instr;
              err_halt  <= 1'b1;
            end else begin
              if (is_load) load_data_reg <= mem_resp_rdata;
              state <= S_WRITEBACK;
            end
          end
        end

        S_WRITEBACK: begin
          if (pc_misaligned) begin
            state     <= S_ERR;
            err_cause <= ERR_MISALIGNED_PC;
            err_pc    <= pc;
            err_instr <= instr;
            err_halt  <= 1'b1;
          end else begin
            pc    <= next_pc_candidate;
            state <= S_FETCH;
          end
        end

        S_ERR: state <= S_ERR;

        default: state <= S_ERR;
      endcase
    end
  end
endmodule
