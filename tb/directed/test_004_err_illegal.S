/* Expect: ERR_HALT cause=4 (ILLEGAL_INSTR). opcode 0b1111111 is not a legal
 * RV32I/M major opcode. The harness checks the ERR_HALT cause field, not a
 * TX pass/fail byte (this program never reaches the TEST_PASS/FAIL path).
 */
.option norvc
.section .text
.global main
main:
    .word 0xFFFFFFFF
