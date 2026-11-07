module sanity_counter_tb;
  logic clk = 0;
  logic rst = 1;
  logic [3:0] count;

  sanity_counter dut(.clk(clk), .rst(rst), .count(count));

  always #5 clk = ~clk;

  initial begin
    rst = 1;
    repeat (2) @(posedge clk);
    rst = 0;
    repeat (20) @(posedge clk);
    $display("SANITY final count=%0d", count);
    if (count !== 4'd4) begin
      $display("SANITY FAIL: unexpected count");
      $finish;
    end
    $display("SANITY PASS");
    $finish;
  end
endmodule
