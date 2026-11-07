// Testbench-only behavioral RAM model. NOT synthesizable datapath RTL —
// this stands in for the 1 MiB unified program/data memory described in
// claude_implementation_prompt.txt Section 5, with a documented, controllable
// response latency so processor tests can exercise real wait states instead
// of an instantaneous memory (prompt Section 5: "Do not make execution
// depend on an instantaneous response").
//
// Configuration via Verilog plusargs (set with Zenith's `+name=value` CLI
// syntax, see docs/animas_capabilities.md):
//   +MEMFILE=<path>   $readmemh memory image (word per line, hex, no 0x)
//   +FIXEDLAT=<N>     cycles between request acceptance and response
//                     (default 2 — i.e. NOT same-cycle/instantaneous)
//   +READYWAIT=<N>    cycles req_ready stays low before accepting a new
//                     request (default 0 — exercised explicitly by a
//                     dedicated directed test, see tb/directed/ list)
//   +RANDWAIT=<N>     adds 0..N extra random response-latency cycles per
//                     access (default 0; uses $urandom, seeded via
//                     Zenith's --seed for reproducibility)
module ram_model #(
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
      $display("[ram_model] loading %s", memfile);
      $readmemh(memfile, mem);
    end else begin
      // Deliberately not zero-filled here: a procedural loop writing every
      // `mem` element in this initial block conflicts (Zenith error
      // ZEN-6033, "overlapping longest static prefixes", LRM 9.2.2.4) with
      // the always_ff block below that also drives `mem` on real writes.
      // $readmemh is exempt from that check. Every real test supplies
      // +MEMFILE=...; this path (left X) only fires for a deliberately
      // memory-less smoke test and is not relied on for pass/fail evidence.
      $display("[ram_model] WARNING: no +MEMFILE= given, RAM left uninitialized (X)");
    end
  end

  // ---- req_ready: configurable initial backpressure per new request ----
  // While a request is presented (req_valid=1) but not yet old enough
  // (ready_ctr < ready_wait), req_ready stays low, forcing the core to hold
  // the request stable across cycles — exercising its wait-on-ready path.
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

  // ---- response pipeline: a small shift register of pending completions ----
  localparam int MAXLAT = 64;
  logic        pend_valid [0:MAXLAT-1];
  logic [31:0] pend_rdata [0:MAXLAT-1];
  int i;

  logic accepted;
  assign accepted = req_valid && req_ready;

  logic [31:0] word_index;
  assign word_index = req_addr[31:2];

  always_ff @(posedge clk) begin
    if (rst) begin
      for (i = 0; i < MAXLAT; i = i + 1) pend_valid[i] <= 1'b0;
      resp_valid <= 1'b0;
      resp_rdata <= 32'b0;
    end else begin
      // age the pending-response pipeline by one slot each cycle
      for (i = 0; i < MAXLAT - 1; i = i + 1) begin
        pend_valid[i] <= pend_valid[i+1];
        pend_rdata[i] <= pend_rdata[i+1];
      end
      pend_valid[MAXLAT-1] <= 1'b0;

      if (accepted) begin
        int lat;
        int extra;
        extra = (rand_wait_max > 0) ? ($urandom_range(rand_wait_max, 0)) : 0;
        lat = fixed_lat + extra;
        if (lat < 1) lat = 1;
        if (lat > MAXLAT) lat = MAXLAT;
        if (req_we) begin
          if (req_wstrb[0]) mem[word_index][7:0]   <= req_wdata[7:0];
          if (req_wstrb[1]) mem[word_index][15:8]  <= req_wdata[15:8];
          if (req_wstrb[2]) mem[word_index][23:16] <= req_wdata[23:16];
          if (req_wstrb[3]) mem[word_index][31:24] <= req_wdata[31:24];
          pend_valid[lat-1] <= 1'b1;
          pend_rdata[lat-1] <= 32'b0;
        end else begin
          pend_valid[lat-1] <= 1'b1;
          pend_rdata[lat-1] <= mem[word_index];
        end
      end

      resp_valid <= pend_valid[0];
      resp_rdata <= pend_rdata[0];
    end
  end
endmodule
