/* Directed test 003: the complete RV32M extension, including
 * MULH/MULHSU/MULHU, signed/unsigned division and remainder, division by
 * zero, and signed overflow (INT_MIN / -1), per the RISC-V ISA spec.
 */
.option norvc
#include "test_macros.S"

.section .text
.global main
main:
    /* MUL: low 32 bits, sign-agnostic */
    li   t0, 6
    li   t1, 7
    mul  t2, t0, t1
    li   t3, 42
    bne  t2, t3, fail

    li   t0, -3
    li   t1, 5
    mul  t2, t0, t1       /* -15 */
    li   t3, -15
    bne  t2, t3, fail

    /* MULH: high 32 bits of signed * signed.
     * 0x7FFFFFFF * 2 = 0xFFFFFFFE (64-bit) -> high32 = 0x00000000 */
    li   t0, 0x7FFFFFFF
    li   t1, 2
    mulh t2, t0, t1
    bne  t2, zero, fail

    /* MULH: (-2) * (-2) = 4 (64-bit 0x0000000000000004) -> high32 = 0 */
    li   t0, -2
    li   t1, -2
    mulh t2, t0, t1
    bne  t2, zero, fail

    /* MULH: (-1) * 0x7FFFFFFF = -0x7FFFFFFF = 0xFFFFFFFF80000001 (64-bit)
     * -> high32 = 0xFFFFFFFF */
    li   t0, -1
    li   t1, 0x7FFFFFFF
    mulh t2, t0, t1
    li   t3, 0xFFFFFFFF
    bne  t2, t3, fail

    /* MULHU: 0xFFFFFFFF * 0xFFFFFFFF (unsigned) = 0xFFFFFFFE00000001
     * -> high32 = 0xFFFFFFFE */
    li   t0, 0xFFFFFFFF
    li   t1, 0xFFFFFFFF
    mulhu t2, t0, t1
    li   t3, 0xFFFFFFFE
    bne  t2, t3, fail

    /* MULHSU: rs1 signed, rs2 unsigned. (-1) * 0xFFFFFFFF(unsigned)
     * = -4294967295 = 0xFFFFFFFF00000001 (64-bit) -> high32=0xFFFFFFFF */
    li   t0, -1
    li   t1, 0xFFFFFFFF
    mulhsu t2, t0, t1
    li   t3, 0xFFFFFFFF
    bne  t2, t3, fail

    /* DIV / REM, normal signed case */
    li   t0, -17
    li   t1, 5
    div  t2, t0, t1       /* -3 (truncating toward zero) */
    li   t3, -3
    bne  t2, t3, fail
    rem  t2, t0, t1       /* -2 (sign follows dividend) */
    li   t3, -2
    bne  t2, t3, fail

    /* DIVU / REMU, unsigned case */
    li   t0, 17
    li   t1, 5
    divu t2, t0, t1
    li   t3, 3
    bne  t2, t3, fail
    remu t2, t0, t1
    li   t3, 2
    bne  t2, t3, fail

    /* Division by zero: DIV -> -1 (all ones), REM -> dividend */
    li   t0, 123
    li   t1, 0
    div  t2, t0, t1
    li   t3, -1
    bne  t2, t3, fail
    rem  t2, t0, t1
    bne  t2, t0, fail

    /* Division by zero, unsigned: DIVU -> all ones, REMU -> dividend */
    li   t0, 456
    li   t1, 0
    divu t2, t0, t1
    li   t3, -1
    bne  t2, t3, fail
    remu t2, t0, t1
    bne  t2, t0, fail

    /* Signed overflow: INT_MIN / -1 -> quotient = INT_MIN, remainder = 0 */
    li   t0, 0x80000000
    li   t1, -1
    div  t2, t0, t1
    bne  t2, t0, fail
    rem  t2, t0, t1
    bne  t2, zero, fail

    j pass
fail:
    TEST_FAIL
pass:
    TEST_PASS
