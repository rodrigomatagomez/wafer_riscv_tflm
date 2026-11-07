/* Shared macros for directed assembly tests (tb/directed/*.S).
 * Convention (see tb/soc_tb.sv header): write TX=1 on pass / TX=0 on fail,
 * then EBREAK as the intentional, documented clean-stop mechanism.
 */
#ifndef WAFER_TEST_MACROS_S
#define WAFER_TEST_MACROS_S

.equ MMIO_TX, 0x10000000

.macro TEST_PASS
    li   t6, MMIO_TX
    li   t5, 1
    sw   t5, 0(t6)
    ebreak
.endm

.macro TEST_FAIL
    li   t6, MMIO_TX
    sw   zero, 0(t6)
    ebreak
.endm

#endif
