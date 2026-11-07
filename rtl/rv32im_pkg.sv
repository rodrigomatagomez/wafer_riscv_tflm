// RV32IM shared constants: opcodes, funct3/funct7, ALU operation codes.
// Written from the RISC-V ISA specification (https://docs.riscv.org/reference/isa/),
// not derived from or copied out of any existing processor implementation.
package rv32im_pkg;

  // Major opcodes (bits [6:0])
  localparam logic [6:0] OPC_LOAD     = 7'b0000011;
  localparam logic [6:0] OPC_MISC_MEM = 7'b0001111; // FENCE
  localparam logic [6:0] OPC_OP_IMM   = 7'b0010011;
  localparam logic [6:0] OPC_AUIPC    = 7'b0010111;
  localparam logic [6:0] OPC_STORE    = 7'b0100011;
  localparam logic [6:0] OPC_OP       = 7'b0110011; // also M-extension
  localparam logic [6:0] OPC_LUI      = 7'b0110111;
  localparam logic [6:0] OPC_BRANCH   = 7'b1100011;
  localparam logic [6:0] OPC_JALR     = 7'b1100111;
  localparam logic [6:0] OPC_JAL      = 7'b1101111;
  localparam logic [6:0] OPC_SYSTEM   = 7'b1110011; // ECALL/EBREAK

  // funct3 for OP / OP_IMM
  localparam logic [2:0] F3_ADD_SUB = 3'b000;
  localparam logic [2:0] F3_SLL     = 3'b001;
  localparam logic [2:0] F3_SLT     = 3'b010;
  localparam logic [2:0] F3_SLTU    = 3'b011;
  localparam logic [2:0] F3_XOR     = 3'b100;
  localparam logic [2:0] F3_SRL_SRA = 3'b101;
  localparam logic [2:0] F3_OR      = 3'b110;
  localparam logic [2:0] F3_AND     = 3'b111;

  // funct3 for M-extension (OPC_OP, funct7 = 0000001)
  localparam logic [2:0] F3_MUL    = 3'b000;
  localparam logic [2:0] F3_MULH   = 3'b001;
  localparam logic [2:0] F3_MULHSU = 3'b010;
  localparam logic [2:0] F3_MULHU  = 3'b011;
  localparam logic [2:0] F3_DIV    = 3'b100;
  localparam logic [2:0] F3_DIVU   = 3'b101;
  localparam logic [2:0] F3_REM    = 3'b110;
  localparam logic [2:0] F3_REMU   = 3'b111;

  localparam logic [6:0] F7_BASE = 7'b0000000;
  localparam logic [6:0] F7_ALT  = 7'b0100000; // SUB, SRA
  localparam logic [6:0] F7_MULDIV = 7'b0000001;

  // funct3 for LOAD/STORE
  localparam logic [2:0] F3_B  = 3'b000;
  localparam logic [2:0] F3_H  = 3'b001;
  localparam logic [2:0] F3_W  = 3'b010;
  localparam logic [2:0] F3_BU = 3'b100;
  localparam logic [2:0] F3_HU = 3'b101;

  // funct3 for BRANCH
  localparam logic [2:0] F3_BEQ  = 3'b000;
  localparam logic [2:0] F3_BNE  = 3'b001;
  localparam logic [2:0] F3_BLT  = 3'b100;
  localparam logic [2:0] F3_BGE  = 3'b101;
  localparam logic [2:0] F3_BLTU = 3'b110;
  localparam logic [2:0] F3_BGEU = 3'b111;

  // SYSTEM immediates (imm[11:0] field distinguishes ECALL/EBREAK)
  localparam logic [11:0] IMM_ECALL  = 12'h000;
  localparam logic [11:0] IMM_EBREAK = 12'h001;

  // ALU operation encoding used internally between decode and execute.
  typedef enum logic [3:0] {
    ALU_ADD, ALU_SUB, ALU_SLL, ALU_SLT, ALU_SLTU, ALU_XOR,
    ALU_SRL, ALU_SRA, ALU_OR, ALU_AND, ALU_PASSB
  } alu_op_e;

  // M-extension operation encoding.
  typedef enum logic [2:0] {
    MD_MUL, MD_MULH, MD_MULHSU, MD_MULHU, MD_DIV, MD_DIVU, MD_REM, MD_REMU
  } muldiv_op_e;

  // Error-halt cause codes, captured for observation per prompt Section 5.
  typedef enum logic [2:0] {
    ERR_NONE           = 3'd0,
    ERR_MISALIGNED_PC  = 3'd1,
    ERR_MISALIGNED_LD  = 3'd2,
    ERR_MISALIGNED_ST  = 3'd3,
    ERR_ILLEGAL_INSTR  = 3'd4,
    ERR_OUT_OF_RANGE   = 3'd5,
    ERR_ECALL          = 3'd6,
    ERR_EBREAK         = 3'd7
  } err_cause_e;

endpackage
