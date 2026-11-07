// Top-level testbench: instantiates soc_top (synthesizable system) plus the
// testbench-only ram_model, drives clock/reset, and prints structured,
// line-oriented markers that scripts/run_rtl_test.py parses:
//
//   RETIRE cycle=<n> pc=<hex8> instr=<hex8>
//   ERR_HALT cycle=<n> cause=<n> pc=<hex8> instr=<hex8>
//   MMIO_TX cycle=<n> byte=<dec>
//   MMIO_MEASURE cycle=<n> value=<dec>
//   MMIO_PREDICTED_CLASS cycle=<n> case_id=<dec> class=<dec> score0=<dec> score1=<dec> score2=<dec> score3=<dec>
//   MMIO_STATUS cycle=<n> value=<dec>
//   SIM_TIMEOUT cycle=<n>
//
// Directed processor tests (tb/directed/) use the convention: a test
// program writes a single result byte to TX (1 = PASS, 0 = FAIL, matching
// the test's own internal checks) and then executes EBREAK as its
// intentional, documented clean-stop mechanism (there is no OS exit
// syscall in this environment per prompt Section 5 policy). EBREAK always
// produces an ERR_HALT/cause=EBREAK marker; for these tests that is the
// *expected* outcome, and scripts/run_rtl_test.py checks the preceding
// MMIO_TX byte, not the absence of a halt.
import rv32im_pkg::*;

module soc_tb;
  logic clk = 0;
  logic rst = 1;
  always #5 clk = ~clk;

  int max_cycles;
  initial if (!$value$plusargs("MAXCYCLES=%d", max_cycles)) max_cycles = 2_000_000;

  // Per-instruction RETIRE tracing is needed for the processor-verification
  // tests (compared against scripts/isa_reference_model.py) but must stay
  // OFF for large functional runs (e.g. TFLM inference, which can retire
  // many millions of instructions) -- per prompt Section 7: "Avoid dumping
  // every signal across millions of cycles; use retirement traces and
  // bounded diagnostic waveform windows." Default off; enable with +TRACE=1.
  int trace_enable;
  initial if (!$value$plusargs("TRACE=%d", trace_enable)) trace_enable = 0;

  longint unsigned cycle_count;
  always_ff @(posedge clk) begin
    if (rst) cycle_count <= 0;
    else cycle_count <= cycle_count + 1;
  end

  // ---- DUT + memory model ----
  logic        ram_req_valid;
  logic [31:0] ram_req_addr;
  logic        ram_req_we;
  logic [3:0]  ram_req_wstrb;
  logic [31:0] ram_req_wdata;
  logic        ram_req_ready;
  logic        ram_resp_valid;
  logic [31:0] ram_resp_rdata;

  logic        err_halt;
  err_cause_e  err_cause;
  logic [31:0] err_pc;
  logic [31:0] err_instr;
  logic        retire_valid;
  logic [31:0] retire_pc;
  logic [31:0] retire_instr;
  logic        retire_reg_we;
  logic [4:0]  retire_rd_addr;
  logic [31:0] retire_rd_wdata;

  logic [31:0] mmio_tx_reg;
  logic         mmio_tx_write_pulse;
  logic [31:0] mmio_case_id_reg;
  logic [31:0] mmio_score_reg [0:3];
  logic [31:0] mmio_predicted_class_reg;
  logic         mmio_predicted_class_write_pulse;
  logic [31:0] mmio_measure_reg;
  logic         mmio_measure_write_pulse;
  logic [31:0] mmio_status_reg;
  logic         mmio_status_write_pulse;

  soc_top u_soc (
      .clk(clk), .rst(rst),
      .ram_req_valid(ram_req_valid), .ram_req_addr(ram_req_addr),
      .ram_req_we(ram_req_we), .ram_req_wstrb(ram_req_wstrb), .ram_req_wdata(ram_req_wdata),
      .ram_req_ready(ram_req_ready),
      .ram_resp_valid(ram_resp_valid), .ram_resp_rdata(ram_resp_rdata),
      .err_halt(err_halt), .err_cause(err_cause), .err_pc(err_pc), .err_instr(err_instr),
      .retire_valid(retire_valid), .retire_pc(retire_pc), .retire_instr(retire_instr),
      .retire_reg_we(retire_reg_we), .retire_rd_addr(retire_rd_addr), .retire_rd_wdata(retire_rd_wdata),
      .mmio_tx_reg(mmio_tx_reg), .mmio_tx_write_pulse(mmio_tx_write_pulse),
      .mmio_case_id_reg(mmio_case_id_reg), .mmio_score_reg(mmio_score_reg),
      .mmio_predicted_class_reg(mmio_predicted_class_reg),
      .mmio_predicted_class_write_pulse(mmio_predicted_class_write_pulse),
      .mmio_measure_reg(mmio_measure_reg), .mmio_measure_write_pulse(mmio_measure_write_pulse),
      .mmio_status_reg(mmio_status_reg), .mmio_status_write_pulse(mmio_status_write_pulse)
  );

  ram_model u_ram (
      .clk(clk), .rst(rst),
      .req_valid(ram_req_valid), .req_addr(ram_req_addr),
      .req_we(ram_req_we), .req_wstrb(ram_req_wstrb), .req_wdata(ram_req_wdata),
      .req_ready(ram_req_ready),
      .resp_valid(ram_resp_valid), .resp_rdata(ram_resp_rdata)
  );

  // ---- reset sequence ----
  initial begin
    rst = 1;
    repeat (4) @(posedge clk);
    rst = 0;
  end

  // ---- observation ----
  always_ff @(posedge clk) begin
    if (!rst && retire_valid && trace_enable) begin
      $display("RETIRE cycle=%0d pc=%08x instr=%08x rd_we=%0d rd_addr=%0d rd_wdata=%08x",
                cycle_count, retire_pc, retire_instr, retire_reg_we, retire_rd_addr, retire_rd_wdata);
    end
  end

  logic err_reported;
  always_ff @(posedge clk) begin
    if (rst) begin
      err_reported <= 1'b0;
    end else if (err_halt && !err_reported) begin
      $display("ERR_HALT cycle=%0d cause=%0d pc=%08x instr=%08x", cycle_count, err_cause, err_pc, err_instr);
      err_reported <= 1'b1;
      $finish;
    end
  end

  always_ff @(posedge clk) begin
    if (!rst && mmio_tx_write_pulse) begin
      $display("MMIO_TX cycle=%0d byte=%0d", cycle_count, mmio_tx_reg[7:0]);
    end
  end

  always_ff @(posedge clk) begin
    if (!rst && mmio_measure_write_pulse) begin
      $display("MMIO_MEASURE cycle=%0d value=%0d", cycle_count, mmio_measure_reg);
    end
  end

  always_ff @(posedge clk) begin
    if (!rst && mmio_predicted_class_write_pulse) begin
      $display("MMIO_PREDICTED_CLASS cycle=%0d case_id=%0d class=%0d score0=%0d score1=%0d score2=%0d score3=%0d",
               cycle_count, mmio_case_id_reg, mmio_predicted_class_reg,
               $signed(mmio_score_reg[0]), $signed(mmio_score_reg[1]),
               $signed(mmio_score_reg[2]), $signed(mmio_score_reg[3]));
    end
  end

  always_ff @(posedge clk) begin
    if (!rst && mmio_status_write_pulse) begin
      $display("MMIO_STATUS cycle=%0d value=%0d", cycle_count, mmio_status_reg);
      $finish;
    end
  end

  always_ff @(posedge clk) begin
    if (!rst && cycle_count >= max_cycles) begin
      $display("SIM_TIMEOUT cycle=%0d", cycle_count);
      $finish;
    end
  end
endmodule
