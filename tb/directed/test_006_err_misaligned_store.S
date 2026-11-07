/* Expect: ERR_HALT cause=3 (MISALIGNED_ST). SH to an odd address. */
.option norvc
.section .text
.global main
main:
    li   t0, 0x1001
    sh   zero, 0(t0)
