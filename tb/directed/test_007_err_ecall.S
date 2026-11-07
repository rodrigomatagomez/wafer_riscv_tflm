/* Expect: ERR_HALT cause=6 (ECALL). */
.option norvc
.section .text
.global main
main:
    ecall
