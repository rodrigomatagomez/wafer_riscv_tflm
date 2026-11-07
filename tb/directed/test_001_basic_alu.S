/* Directed test 001: basic ALU ops, x0 hardwiring, negative immediates,
 * sign extension, and taken/untaken branches.
 * Convention: writes TX=1 and EBREAK on pass, TX=0 and EBREAK on any failure.
 */
.option norvc
#include "test_macros.S"

.section .text
.global main
main:
    /* x0 must always read as zero regardless of writes */
    addi x0, x0, 5
    bne  x0, zero, fail

    /* ADDI with a negative immediate; sign extension of a small negative */
    li   t0, -1          /* expands to addi t0, zero, -1 -> 0xFFFFFFFF */
    li   t1, 0xFFFFFFFF
    bne  t0, t1, fail

    /* ADD / SUB */
    li   t0, 100
    li   t1, 58
    add  t2, t0, t1
    li   t3, 158
    bne  t2, t3, fail

    sub  t2, t0, t1
    li   t3, 42
    bne  t2, t3, fail

    /* SLT / SLTU signed vs unsigned distinction */
    li   t0, -1          /* 0xFFFFFFFF */
    li   t1, 1
    slt  t2, t0, t1       /* signed: -1 < 1 => 1 */
    li   t3, 1
    bne  t2, t3, fail

    sltu t2, t0, t1       /* unsigned: 0xFFFFFFFF < 1 => 0 */
    bne  t2, zero, fail

    /* shifts */
    li   t0, 1
    slli t1, t0, 31
    li   t2, 0x80000000
    bne  t1, t2, fail

    srli t1, t2, 31       /* logical: 0x80000000 >> 31 = 1 */
    li   t3, 1
    bne  t1, t3, fail

    srai t1, t2, 31       /* arithmetic: sign-extends -> all ones */
    li   t3, 0xFFFFFFFF
    bne  t1, t3, fail

    /* XOR / OR / AND */
    li   t0, 0x0F0F0F0F
    li   t1, 0x00FF00FF
    xor  t2, t0, t1
    li   t3, 0x0FF00FF0
    bne  t2, t3, fail
    or   t2, t0, t1
    li   t3, 0x0FFF0FFF
    bne  t2, t3, fail
    and  t2, t0, t1
    li   t3, 0x000F000F
    bne  t2, t3, fail

    /* untaken branch must not be taken */
    li   t0, 1
    li   t1, 2
    beq  t0, t1, fail    /* 1 == 2 is false; must fall through */

    /* taken branch must be taken (jump over a fail) */
    li   t0, 5
    li   t1, 5
    beq  t0, t1, taken_ok
    j    fail
taken_ok:

    /* JAL / JALR with return address check */
    jal  ra, subroutine
    li   t3, 1
    bne  a0, t3, fail
    j    pass

subroutine:
    li   a0, 1
    jalr zero, 0(ra)

fail:
    TEST_FAIL
pass:
    TEST_PASS
