// MMIO register block for the wafer-classification demo (prompt Section 5).
// All registers are write-only from the CPU's perspective (reads return the
// last written value, which is harmless and avoids X-propagation, but is
// not part of the required behavior). Only full-word (wstrb==4'b1111)
// accesses at these exact word-aligned addresses are accepted; anything
// else presented to this block is reported as an error response so
// firmware mistakes are not silently absorbed.
//
// Address map (byte offsets from BASE = 0x10000000):
//   0x00 TX               0x10 SCORE_2
//   0x04 CASE_ID          0x14 SCORE_3
//   0x08 SCORE_0          0x18 PREDICTED_CLASS
//   0x0C SCORE_1          0x1C MEASURE
//                         0x20 STATUS
module mmio #(
    parameter logic [31:0] BASE = 32'h1000_0000
)(
    input  logic        clk,
    input  logic        rst,

    input  logic        req_valid,
    input  logic [31:0]  req_addr,
    input  logic        req_we,
    input  logic [3:0]  req_wstrb,
    input  logic [31:0] req_wdata,
    output logic        req_ready,
    output logic        resp_valid,
    output logic        resp_err,
    output logic [31:0] resp_rdata,

    // Observed register values, for the testbench to capture/export.
    output logic [31:0] tx_reg,
    output logic        tx_write_pulse,
    output logic [31:0] case_id_reg,
    output logic [31:0] score_reg [0:3],
    output logic [31:0] predicted_class_reg,
    output logic         predicted_class_write_pulse,
    output logic [31:0] measure_reg,
    output logic         measure_write_pulse,
    output logic [31:0] status_reg,
    output logic         status_write_pulse
);
  // 6 bits: offsets run 0x00..0x20, and 0x20 does not fit in 5 bits (needs
  // bit 5) — an earlier draft used [4:0] here, which silently truncated
  // OFF_STATUS (0x20) to 0, aliasing it onto OFF_TX. Caught by Zenith's own
  // "vector literal too large for the given number of bits" + "duplicate
  // case item" warnings on the first compile; see docs/issues.md.
  localparam logic [5:0] OFF_TX      = 6'h00;
  localparam logic [5:0] OFF_CASEID  = 6'h04;
  localparam logic [5:0] OFF_SCORE0  = 6'h08;
  localparam logic [5:0] OFF_SCORE1  = 6'h0C;
  localparam logic [5:0] OFF_SCORE2  = 6'h10;
  localparam logic [5:0] OFF_SCORE3  = 6'h14;
  localparam logic [5:0] OFF_PRED    = 6'h18;
  localparam logic [5:0] OFF_MEASURE = 6'h1C;
  localparam logic [5:0] OFF_STATUS  = 6'h20;

  logic [5:0] offset;
  assign offset = req_addr[5:0] - BASE[5:0];

  logic word_aligned_full_write;
  assign word_aligned_full_write = req_we && (req_wstrb == 4'b1111) && (req_addr[1:0] == 2'b00);
  logic known_offset;
  assign known_offset = (offset == OFF_TX) || (offset == OFF_CASEID) ||
                         (offset == OFF_SCORE0) || (offset == OFF_SCORE1) ||
                         (offset == OFF_SCORE2) || (offset == OFF_SCORE3) ||
                         (offset == OFF_PRED) || (offset == OFF_MEASURE) ||
                         (offset == OFF_STATUS);

  assign req_ready = 1'b1; // always accepts in the same cycle it is asserted

  always_ff @(posedge clk) begin
    tx_write_pulse              <= 1'b0;
    predicted_class_write_pulse <= 1'b0;
    measure_write_pulse         <= 1'b0;
    status_write_pulse          <= 1'b0;
    resp_valid <= 1'b0;
    resp_err   <= 1'b0;
    resp_rdata <= 32'b0;

    if (rst) begin
      tx_reg               <= 32'b0;
      case_id_reg          <= 32'b0;
      score_reg[0]         <= 32'b0;
      score_reg[1]         <= 32'b0;
      score_reg[2]         <= 32'b0;
      score_reg[3]         <= 32'b0;
      predicted_class_reg  <= 32'b0;
      measure_reg          <= 32'b0;
      status_reg           <= 32'b0;
    end else if (req_valid) begin
      resp_valid <= 1'b1;
      if (!known_offset || !req_we || !word_aligned_full_write) begin
        resp_err <= 1'b1;
      end else begin
        resp_rdata <= req_wdata;
        unique case (offset)
          OFF_TX:      begin tx_reg              <= req_wdata; tx_write_pulse <= 1'b1; end
          OFF_CASEID:  case_id_reg         <= req_wdata;
          OFF_SCORE0:  score_reg[0]        <= req_wdata;
          OFF_SCORE1:  score_reg[1]        <= req_wdata;
          OFF_SCORE2:  score_reg[2]        <= req_wdata;
          OFF_SCORE3:  score_reg[3]        <= req_wdata;
          OFF_PRED:    begin predicted_class_reg <= req_wdata; predicted_class_write_pulse <= 1'b1; end
          OFF_MEASURE: begin measure_reg   <= req_wdata; measure_write_pulse <= 1'b1; end
          OFF_STATUS:  begin status_reg    <= req_wdata; status_write_pulse <= 1'b1; end
          default: ;
        endcase
      end
    end
  end
endmodule
