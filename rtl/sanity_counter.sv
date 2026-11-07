module sanity_counter(input logic clk, input logic rst, output logic [3:0] count);
  always_ff @(posedge clk or posedge rst)
    if (rst) count <= 4'd0;
    else count <= count + 4'd1;
endmodule
