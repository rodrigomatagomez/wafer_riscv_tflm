// Sequential (shift-add / restoring-division) implementation of the eight
// RV32M instructions. Shared 32-cycle iterative datapath for multiply and
// for divide/remainder, selected by `op`. Not a single-cycle `*`/`/`
// operator: this is an explicit multi-cycle hardware algorithm, matching
// the multicycle nature of the rest of the core.
//
// Correctness notes (see docs/decisions.md / docs/findings.md for the
// worked-through edge cases):
//  - Multiply: compute unsigned magnitudes of the (possibly signed)
//    operands, run a 32-iteration shift-add unsigned multiplier, then
//    two's-complement-negate the 64-bit product if exactly one operand was
//    negative (never for MULHU; only rs1 for MULHSU; both for MUL/MULH).
//  - Divide/remainder: compute unsigned magnitudes (abs(rs1), abs(rs2) when
//    the operation is signed; raw values when unsigned), run a 32-iteration
//    restoring unsigned divider, sign-correct quotient/remainder, then
//    override with the RISC-V-mandated divide-by-zero results
//    (quotient = all-ones, remainder = rs1) regardless of sign. The
//    signed-overflow case (INT_MIN / -1) requires no special case: it falls
//    out of the magnitude-based algorithm correctly (verified by hand).
import rv32im_pkg::*;

module rv32im_muldiv (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  muldiv_op_e  op,
    input  logic [31:0] rs1,
    input  logic [31:0] rs2,
    output logic        busy,
    output logic        done,
    output logic [31:0] result
);
  typedef enum logic [1:0] {S_IDLE, S_RUN, S_DONE} state_e;
  state_e state;

  logic is_mul;
  logic is_signed1, is_signed2; // whether rs1 / rs2 should be treated as signed for THIS op
  always_comb begin
    is_mul = (op == MD_MUL) || (op == MD_MULH) || (op == MD_MULHSU) || (op == MD_MULHU);
    unique case (op)
      MD_MUL, MD_MULH: begin is_signed1 = 1'b1; is_signed2 = 1'b1; end
      MD_MULHSU:        begin is_signed1 = 1'b1; is_signed2 = 1'b0; end
      MD_MULHU:         begin is_signed1 = 1'b0; is_signed2 = 1'b0; end
      MD_DIV, MD_REM:   begin is_signed1 = 1'b1; is_signed2 = 1'b1; end
      default:          begin is_signed1 = 1'b0; is_signed2 = 1'b0; end // DIVU, REMU
    endcase
  end

  logic sign1, sign2;
  assign sign1 = is_signed1 && rs1[31];
  assign sign2 = is_signed2 && rs2[31];

  logic [31:0] mag1, mag2;
  assign mag1 = sign1 ? (~rs1 + 32'd1) : rs1;
  assign mag2 = sign2 ? (~rs2 + 32'd1) : rs2;

  // ---- shared iteration counter ----
  logic [5:0] count;

  // ---- multiply datapath: 64-bit shift-right accumulate ----
  logic [64:0] mul_p; // {carry, product[63:0]} ; mul_p[64] unused guard bit
  logic [31:0] mcand;

  // ---- divide datapath: 64-bit {remainder, quotient} register ----
  logic [63:0] div_r;
  logic [31:0] divisor;

  // Combinational "add if LSB set" step for the multiplier accumulator,
  // computed separately so the FSM below performs a single non-blocking
  // write to `mul_p` per cycle (two non-blocking writes to overlapping
  // bits in the same always_ff would silently drop the add: the later
  // whole-register shift assignment would win over the earlier partial
  // accumulator-add assignment at the NBA update step).
  logic [64:0] mul_p_added;
  always_comb begin
    mul_p_added = mul_p;
    if (mul_p[0]) mul_p_added[64:32] = mul_p[64:32] + {1'b0, mcand};
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      state <= S_IDLE;
      busy  <= 1'b0;
      done  <= 1'b0;
    end else begin
      done <= 1'b0;
      unique case (state)
        S_IDLE: begin
          if (start) begin
            busy  <= 1'b1;
            count <= 6'd0;
            if (is_mul) begin
              mul_p  <= {33'b0, mag1}; // {upper33, lower32} ; upper33 incl extra guard bit always 0
              mcand  <= mag2;
            end else begin
              div_r   <= {32'b0, mag1};
              divisor <= mag2;
            end
            state <= S_RUN;
          end
        end

        S_RUN: begin
          if (is_mul) begin
            mul_p <= {1'b0, mul_p_added[64:1]};
          end else begin
            logic [63:0] shifted;
            logic [32:0] trial;
            shifted = div_r << 1;
            trial   = {1'b0, shifted[63:32]} - {1'b0, divisor};
            if (!trial[32]) begin
              div_r <= {trial[31:0], shifted[31:1], 1'b1};
            end else begin
              div_r <= {shifted[63:32], shifted[31:1], 1'b0};
            end
          end
          if (count == 6'd31) begin
            state <= S_DONE;
          end else begin
            count <= count + 6'd1;
          end
        end

        S_DONE: begin
          busy  <= 1'b0;
          done  <= 1'b1;
          state <= S_IDLE;
        end

        default: state <= S_IDLE;
      endcase
    end
  end

  // ---- result mux (combinational, valid when `done`) ----
  logic [63:0] mul_product_mag;
  assign mul_product_mag = mul_p[63:0];

  logic mul_neg;
  assign mul_neg = sign1 ^ sign2;
  logic [63:0] mul_product_signed;
  assign mul_product_signed = mul_neg ? (~mul_product_mag + 64'd1) : mul_product_mag;

  logic [31:0] quot_mag, rem_mag;
  assign quot_mag = div_r[31:0];
  assign rem_mag  = div_r[63:32];

  logic quot_neg, rem_neg;
  assign quot_neg = sign1 ^ sign2;
  assign rem_neg  = sign1;

  logic [31:0] quot_signed, rem_signed;
  assign quot_signed = quot_neg ? (~quot_mag + 32'd1) : quot_mag;
  assign rem_signed  = rem_neg  ? (~rem_mag  + 32'd1) : rem_mag;

  logic div_by_zero;
  assign div_by_zero = (rs2 == 32'b0);

  always_comb begin
    unique case (op)
      MD_MUL:    result = mul_product_signed[31:0];
      MD_MULH:   result = mul_product_signed[63:32];
      MD_MULHSU: result = mul_product_signed[63:32];
      MD_MULHU:  result = mul_product_signed[63:32];
      MD_DIV:    result = div_by_zero ? 32'hFFFFFFFF : quot_signed;
      MD_DIVU:   result = div_by_zero ? 32'hFFFFFFFF : quot_mag;
      MD_REM:    result = div_by_zero ? rs1          : rem_signed;
      MD_REMU:   result = div_by_zero ? rs1          : rem_mag;
      default:   result = 32'b0;
    endcase
  end
endmodule
