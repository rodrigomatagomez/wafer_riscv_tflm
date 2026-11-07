// Synthesizable system: core + address decode/bus + MMIO. The RAM array
// itself is deliberately NOT instantiated here — it is a testbench-provided
// memory model (tb/ram_model.sv) connected through the ram_* port below,
// per the prompt's instruction to keep the simulation memory model and
// testbench code identified separately from synthesizable datapath RTL.
//
// Address map:
//   0x0000_0000 .. 0x000F_FFFF  RAM (1 MiB), forwarded to ram_* port
//   0x1000_0000 .. 0x1000_0023  MMIO registers (see rtl/mmio.sv)
//   anything else               out-of-range: a 1-cycle registered error
//                               response (mem_resp_valid=1, mem_resp_err=1)
module soc_top (
    input  logic        clk,
    input  logic        rst,

    // RAM-facing port, driven by a testbench memory model.
    output logic        ram_req_valid,
    output logic [31:0] ram_req_addr,
    output logic        ram_req_we,
    output logic [3:0]  ram_req_wstrb,
    output logic [31:0] ram_req_wdata,
    input  logic        ram_req_ready,
    input  logic        ram_resp_valid,
    input  logic [31:0] ram_resp_rdata,

    output logic              err_halt,
    output rv32im_pkg::err_cause_e err_cause,
    output logic [31:0]       err_pc,
    output logic [31:0]       err_instr,

    output logic        retire_valid,
    output logic [31:0] retire_pc,
    output logic [31:0] retire_instr,
    output logic        retire_reg_we,
    output logic [4:0]  retire_rd_addr,
    output logic [31:0] retire_rd_wdata,

    output logic [31:0] mmio_tx_reg,
    output logic         mmio_tx_write_pulse,
    output logic [31:0] mmio_case_id_reg,
    output logic [31:0] mmio_score_reg [0:3],
    output logic [31:0] mmio_predicted_class_reg,
    output logic         mmio_predicted_class_write_pulse,
    output logic [31:0] mmio_measure_reg,
    output logic         mmio_measure_write_pulse,
    output logic [31:0] mmio_status_reg,
    output logic         mmio_status_write_pulse
);
  localparam logic [31:0] RAM_TOP     = 32'h0010_0000; // exclusive
  localparam logic [31:0] MMIO_BASE   = 32'h1000_0000;
  localparam logic [31:0] MMIO_TOP    = 32'h1000_0024; // exclusive

  logic        core_req_valid;
  logic [31:0] core_req_addr;
  logic        core_req_we;
  logic [3:0]  core_req_wstrb;
  logic [31:0] core_req_wdata;
  logic        core_req_ready;
  logic        core_resp_valid;
  logic        core_resp_err;
  logic [31:0] core_resp_rdata;

  rv32im_core u_core (
      .clk(clk), .rst(rst),
      .mem_req_valid(core_req_valid), .mem_req_addr(core_req_addr),
      .mem_req_we(core_req_we), .mem_req_wstrb(core_req_wstrb), .mem_req_wdata(core_req_wdata),
      .mem_req_ready(core_req_ready),
      .mem_resp_valid(core_resp_valid), .mem_resp_err(core_resp_err), .mem_resp_rdata(core_resp_rdata),
      .err_halt(err_halt), .err_cause(err_cause), .err_pc(err_pc), .err_instr(err_instr),
      .retire_valid(retire_valid), .retire_pc(retire_pc), .retire_instr(retire_instr),
      .retire_reg_we(retire_reg_we), .retire_rd_addr(retire_rd_addr), .retire_rd_wdata(retire_rd_wdata)
  );

  logic is_ram, is_mmio, is_invalid;
  assign is_ram     = (core_req_addr < RAM_TOP);
  assign is_mmio    = (core_req_addr >= MMIO_BASE) && (core_req_addr < MMIO_TOP);
  assign is_invalid = !is_ram && !is_mmio;

  // MMIO sub-module
  logic mmio_req_ready, mmio_resp_valid, mmio_resp_err;
  logic [31:0] mmio_resp_rdata;
  mmio u_mmio (
      .clk(clk), .rst(rst),
      .req_valid(core_req_valid && is_mmio),
      .req_addr(core_req_addr), .req_we(core_req_we),
      .req_wstrb(core_req_wstrb), .req_wdata(core_req_wdata),
      .req_ready(mmio_req_ready),
      .resp_valid(mmio_resp_valid), .resp_err(mmio_resp_err), .resp_rdata(mmio_resp_rdata),
      .tx_reg(mmio_tx_reg), .tx_write_pulse(mmio_tx_write_pulse),
      .case_id_reg(mmio_case_id_reg), .score_reg(mmio_score_reg),
      .predicted_class_reg(mmio_predicted_class_reg),
      .predicted_class_write_pulse(mmio_predicted_class_write_pulse),
      .measure_reg(mmio_measure_reg), .measure_write_pulse(mmio_measure_write_pulse),
      .status_reg(mmio_status_reg), .status_write_pulse(mmio_status_write_pulse)
  );

  // RAM pass-through (combinational forwarding of the request fields)
  assign ram_req_valid = core_req_valid && is_ram;
  assign ram_req_addr  = core_req_addr;
  assign ram_req_we    = core_req_we;
  assign ram_req_wstrb = core_req_wstrb;
  assign ram_req_wdata = core_req_wdata;

  // Invalid-range request: accept immediately, fault one cycle later.
  logic invalid_pending;
  always_ff @(posedge clk) begin
    if (rst) begin
      invalid_pending <= 1'b0;
    end else begin
      invalid_pending <= core_req_valid && is_invalid && core_req_ready;
    end
  end

  // Remember which target a request was accepted into, so the response mux
  // below is correct even though core_req_addr may no longer reflect it by
  // the time a (possibly multi-cycle) RAM response arrives.
  typedef enum logic [1:0] {TGT_NONE, TGT_RAM, TGT_MMIO, TGT_INVALID} target_e;
  target_e in_flight;
  logic accepted;
  assign accepted = core_req_valid && core_req_ready;
  always_ff @(posedge clk) begin
    if (rst) begin
      in_flight <= TGT_NONE;
    end else if (accepted) begin
      in_flight <= is_ram ? TGT_RAM : (is_mmio ? TGT_MMIO : TGT_INVALID);
    end
  end

  assign core_req_ready = is_ram ? ram_req_ready : 1'b1; // MMIO and invalid both accept same-cycle

  always_comb begin
    unique case (in_flight)
      TGT_RAM: begin
        core_resp_valid = ram_resp_valid;
        core_resp_err   = 1'b0;
        core_resp_rdata = ram_resp_rdata;
      end
      TGT_MMIO: begin
        core_resp_valid = mmio_resp_valid;
        core_resp_err   = mmio_resp_err;
        core_resp_rdata = mmio_resp_rdata;
      end
      TGT_INVALID: begin
        core_resp_valid = invalid_pending;
        core_resp_err   = invalid_pending;
        core_resp_rdata = 32'b0;
      end
      default: begin
        core_resp_valid = 1'b0;
        core_resp_err   = 1'b0;
        core_resp_rdata = 32'b0;
      end
    endcase
  end
endmodule
