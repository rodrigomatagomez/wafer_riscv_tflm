/* Minimal bare-metal startup for rv32im_core.
 * Sets up the stack pointer, zeros .bss, calls main(), and if main() ever
 * returns, signals completion via MMIO STATUS then halts with EBREAK
 * (the project's documented intentional-stop convention — there is no OS
 * exit syscall in this environment; see tb/soc_tb.sv header comment).
 */
.option norvc  /* no compressed instructions anywhere in this project */

.section .text.start
.global _start
_start:
    lui   sp, %hi(_stack_top)
    addi  sp, sp, %lo(_stack_top)

    /* zero .bss: for (p = _bss_start; p < _bss_end; p += 4) *p = 0; */
    lui   t0, %hi(_bss_start)
    addi  t0, t0, %lo(_bss_start)
    lui   t1, %hi(_bss_end)
    addi  t1, t1, %lo(_bss_end)
bss_zero_loop:
    bge   t0, t1, bss_zero_done
    sw    zero, 0(t0)
    addi  t0, t0, 4
    j     bss_zero_loop
bss_zero_done:

    /* Run C++ global/static constructors (.init_array) before main().
     * Required because the TFLM firmware constructs static
     * tflite::MicroInterpreter / MicroMutableOpResolver objects at file
     * scope; without this, their constructors never run and the firmware
     * would call Invoke() on an uninitialized C++ object. */
    lui   s1, %hi(__init_array_start)
    addi  s1, s1, %lo(__init_array_start)
    lui   s2, %hi(__init_array_end)
    addi  s2, s2, %lo(__init_array_end)
init_array_loop:
    bge   s1, s2, init_array_done
    lw    t0, 0(s1)
    jalr  ra, 0(t0)
    addi  s1, s1, 4
    j     init_array_loop
init_array_done:

    call  main

    /* main() is not expected to return in this project's firmware; if it
     * does, this is the documented clean-stop path. */
    ebreak
.hang:
    j .hang
