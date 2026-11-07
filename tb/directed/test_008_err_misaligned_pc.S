/* Expect: ERR_HALT cause=1 (MISALIGNED_PC). JALR to rs1+imm with the
 * resulting (LSB-cleared) target not 4-byte aligned, e.g. target 0x202
 * (binary ...10) survives the spec's LSB clear but still has bit 1 set.
 */
.option norvc
.section .text
.global main
main:
    li   t0, 0x203
    jalr zero, 0(t0)
