/* Directed test 002: byte/halfword/word loads and stores, sign extension,
 * and write-strobe correctness (adjacent bytes must not be disturbed).
 */
.option norvc
#include "test_macros.S"

.section .data
.align 4
scratch:
    .word 0
    .word 0

.section .text
.global main
main:
    /* SB/LB/LBU sign vs zero extension */
    la   t0, scratch
    li   t1, 0xFFFFFF80   /* store byte 0x80 at offset 0 */
    sb   t1, 0(t0)
    lb   t2, 0(t0)
    li   t3, 0xFFFFFF80   /* LB must sign-extend 0x80 -> negative */
    bne  t2, t3, fail
    lbu  t2, 0(t0)
    li   t3, 0x00000080   /* LBU must zero-extend */
    bne  t2, t3, fail

    /* SH/LH/LHU */
    li   t1, 0xFFFF8000
    sh   t1, 0(t0)
    lh   t2, 0(t0)
    li   t3, 0xFFFF8000
    bne  t2, t3, fail
    lhu  t2, 0(t0)
    li   t3, 0x00008000
    bne  t2, t3, fail

    /* SW/LW full word round-trip */
    li   t1, 0xDEADBEEF
    sw   t1, 0(t0)
    lw   t2, 0(t0)
    bne  t2, t1, fail

    /* write-strobe isolation: SB at offset 1 must not disturb byte 0 or
     * bytes 2-3 of the same word */
    li   t1, 0x11223344
    sw   t1, 4(t0)
    li   t1, 0xAA
    sb   t1, 5(t0)        /* overwrite only byte 1 (0x22 -> 0xAA) */
    lw   t2, 4(t0)
    li   t3, 0x1122AA44
    bne  t2, t3, fail

    /* halfword write-strobe isolation at offset 2 */
    li   t1, 0x11223344
    sw   t1, 4(t0)
    li   t1, 0xBBCC
    sh   t1, 6(t0)         /* overwrite upper half only */
    lw   t2, 4(t0)
    li   t3, 0xBBCC3344
    bne  t2, t3, fail

    j pass
fail:
    TEST_FAIL
pass:
    TEST_PASS
