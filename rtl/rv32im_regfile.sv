// 32 x 32-bit general-purpose register file. x0 is hardwired to zero.
// Combinational read, synchronous write.
module rv32im_regfile (
    input  logic        clk,
    input  logic        rst,
    input  logic [4:0]  rs1_addr,
    input  logic [4:0]  rs2_addr,
    output logic [31:0] rs1_data,
    output logic [31:0] rs2_data,
    input  logic        we,
    input  logic [4:0]  rd_addr,
    input  logic [31:0] rd_data
);
  logic [31:0] regs [1:31];

  assign rs1_data = (rs1_addr == 5'd0) ? 32'b0 : regs[rs1_addr];
  assign rs2_data = (rs2_addr == 5'd0) ? 32'b0 : regs[rs2_addr];

  integer i;
  always_ff @(posedge clk) begin
    if (rst) begin
      for (i = 1; i <= 31; i = i + 1) regs[i] <= 32'b0;
    end else if (we && rd_addr != 5'd0) begin
      regs[rd_addr] <= rd_data;
    end
  end
endmodule
