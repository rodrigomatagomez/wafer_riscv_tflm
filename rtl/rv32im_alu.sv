// Combinational ALU for the base integer instructions.
import rv32im_pkg::*;

module rv32im_alu (
    input  logic [31:0]   a,
    input  logic [31:0]   b,
    input  alu_op_e       op,
    output logic [31:0]   result
);
  logic signed [31:0] a_s, b_s;
  assign a_s = a;
  assign b_s = b;

  always_comb begin
    unique case (op)
      ALU_ADD:   result = a + b;
      ALU_SUB:   result = a - b;
      ALU_SLL:   result = a << b[4:0];
      ALU_SLT:   result = {31'b0, (a_s < b_s)};
      ALU_SLTU:  result = {31'b0, (a < b)};
      ALU_XOR:   result = a ^ b;
      ALU_SRL:   result = a >> b[4:0];
      ALU_SRA:   result = a_s >>> b[4:0]; // signed->unsigned assignment copies bits as-is
      ALU_OR:    result = a | b;
      ALU_AND:   result = a & b;
      ALU_PASSB: result = b;
      default:   result = 32'b0;
    endcase
  end
endmodule
