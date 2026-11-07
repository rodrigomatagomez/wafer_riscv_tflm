/* MMIO register map for rv32im_core, per claude_implementation_prompt.txt
 * Section 5. All registers are 32-bit, write-only, at aligned addresses
 * starting at 0x10000000. See rtl/mmio.sv for the RTL-side implementation.
 */
#ifndef WAFER_MMIO_H
#define WAFER_MMIO_H

#include <stdint.h>

#define MMIO_BASE             ((volatile uint32_t *)0x10000000u)
#define MMIO_TX               (*(volatile uint32_t *)0x10000000u)
#define MMIO_CASE_ID          (*(volatile uint32_t *)0x10000004u)
#define MMIO_SCORE_0          (*(volatile uint32_t *)0x10000008u)
#define MMIO_SCORE_1          (*(volatile uint32_t *)0x1000000Cu)
#define MMIO_SCORE_2          (*(volatile uint32_t *)0x10000010u)
#define MMIO_SCORE_3          (*(volatile uint32_t *)0x10000014u)
#define MMIO_PREDICTED_CLASS  (*(volatile uint32_t *)0x10000018u)
#define MMIO_MEASURE          (*(volatile uint32_t *)0x1000001Cu)
#define MMIO_STATUS           (*(volatile uint32_t *)0x10000020u)

static inline void mmio_putc(char c) {
    MMIO_TX = (uint32_t)(unsigned char)c;
}

static inline void mmio_puts(const char *s) {
    while (*s) {
        mmio_putc(*s);
        s++;
    }
}

#endif /* WAFER_MMIO_H */
