/* Expect: ERR_HALT cause=2 (MISALIGNED_LD). LW from an address not a
 * multiple of 4.
 */
.option norvc
.section .text
.global main
main:
    li   t0, 0x1002
    lw   t1, 0(t0)
