// Lightweight alternative to tb/ram_model.sv, same external interface and
// same observable timing, for use once rv32im_core.sv's single-outstanding-
// request property was verified (see docs/decisions.md D-007 and
// docs/findings.md): the core never issues a new mem_req before the
// previous response has arrived (confirmed by inspection of
// rtl/rv32im_core.sv's FSM: S_FETCH->S_FETCH_WAIT->S_DECODE->...->
// S_WRITEBACK->S_FETCH, and S_MEM_ADDR->S_MEM_WAIT->S_WRITEBACK->S_FETCH --
// at least one extra state always separates a response from the next
// request).
//
// tb/ram_model.sv ages a MAXLAT=64-deep shift-register pipeline (two
// 64-element arrays) EVERY clock cycle, regardless of whether a request is
// outstanding -- 126+ signal updates per cycle for a design that, by the
// property above, only ever has 0 or 1 response actually in flight. This
// version replaces that with a single pending-response flag, one captured
// response word, and one countdown counter: O(1) state updated per cycle
// instead of O(MAXLAT).
//
// Same plusargs as tb/ram_model.sv: +MEMFILE=, +FIXEDLAT=, +READYWAIT=,
// +RANDWAIT=. Same byte-write-strobe semantics. Same req_ready backpressure
// behavior. This module does NOT support more than one outstanding request
// at a time -- by design, matching the verified core property -- and
// includes a runtime check that flags (via $error, does not corrupt state)
// if that assumption is ever violated by a different core/testbench.
module ram_model_lite #(
    parameter int WORDS = 262144 // 1 MiB / 4
)(
    input  logic        clk,
    input  logic        rst,
    input  logic        req_valid,
    input  logic [31:0] req_addr,
    input  logic        req_we,
    input  logic [3:0]  req_wstrb,
    input  logic [31:0] req_wdata,
    output logic        req_ready,
    output logic        resp_valid,
    output logic [31:0] resp_rdata
);
  logic [31:0] mem [0:WORDS-1];

  int fixed_lat;
  int ready_wait;
  int rand_wait_max;
  string memfile;

  initial begin
    if (!$value$plusargs("FIXEDLAT=%d", fixed_lat)) fixed_lat = 2;
    if (!$value$plusargs("READYWAIT=%d", ready_wait)) ready_wait = 0;
    if (!$value$plusargs("RANDWAIT=%d", rand_wait_max)) rand_wait_max = 0;
    if ($value$plusargs("MEMFILE=%s", memfile)) begin
      $display("[ram_model_lite] loading %s", memfile);
      $readmemh(memfile, mem);
    end else begin
      $display("[ram_model_lite] WARNING: no +MEMFILE= given, RAM left uninitialized (X)");
    end
  end

  // ---- req_ready: identical backpressure semantics to tb/ram_model.sv ----
  int ready_ctr;
  always_ff @(posedge clk) begin
    if (rst) begin
      ready_ctr <= 0;
    end else if (!req_valid) begin
      ready_ctr <= 0;
    end else if (ready_ctr < ready_wait) begin
      ready_ctr <= ready_ctr + 1;
    end
  end
  assign req_ready = !(req_valid && (ready_ctr < ready_wait));

  logic        accepted;
  assign accepted = req_valid && req_ready;

  logic [31:0] word_index;
  assign word_index = req_addr[31:2];

  // ---- single-outstanding pending-response tracker ----
  logic        pend_valid;
  logic [31:0] pend_rdata;
  int          pend_remaining; // cycles still to wait after acceptance, minus 1

  // Defensive check: this lite model is only valid for a strictly
  // single-outstanding-request core. If a new request is ever accepted
  // while a previous response is still pending delivery, that would be a
  // real protocol violation for this simplified model (the prior response
  // would be silently dropped) -- report it loudly rather than corrupt
  // silently. Not expected to ever fire for rv32im_core.sv (see docs/
  // decisions.md D-007); kept as a safety net for any future core reuse.
  always_ff @(posedge clk) begin
    if (!rst && accepted && pend_valid) begin
      $error("[ram_model_lite] protocol violation: new request accepted while a previous response (data=%08x) was still pending -- this lite RAM model only supports a single outstanding request. Use tb/ram_model.sv instead for a core that pipelines requests.", pend_rdata);
    end
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      pend_valid     <= 1'b0;
      pend_rdata     <= 32'b0;
      pend_remaining <= 0;
      resp_valid     <= 1'b0;
      resp_rdata     <= 32'b0;
    end else begin
      resp_valid <= 1'b0;

      if (accepted) begin
        int lat;
        int extra;
        extra = (rand_wait_max > 0) ? ($urandom_range(rand_wait_max, 0)) : 0;
        lat = fixed_lat + extra;
        if (lat < 1) lat = 1;

        if (req_we) begin
          if (req_wstrb[0]) mem[word_index][7:0]   <= req_wdata[7:0];
          if (req_wstrb[1]) mem[word_index][15:8]  <= req_wdata[15:8];
          if (req_wstrb[2]) mem[word_index][23:16] <= req_wdata[23:16];
          if (req_wstrb[3]) mem[word_index][31:24] <= req_wdata[31:24];
          pend_rdata <= 32'b0;
        end else begin
          pend_rdata <= mem[word_index];
        end
        pend_valid     <= 1'b1;
        pend_remaining <= lat - 1;
      end else if (pend_valid) begin
        if (pend_remaining == 0) begin
          resp_valid <= 1'b1;
          resp_rdata <= pend_rdata;
          pend_valid <= 1'b0;
        end else begin
          pend_remaining <= pend_remaining - 1;
        end
      end
    end
  end
endmodule
