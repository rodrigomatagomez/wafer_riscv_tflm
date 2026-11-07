/* Linker script for the rv32im_core unified 1 MiB program/data memory.
 * Memory map per claude_implementation_prompt.txt Section 5:
 *   RAM: 0x00000000 .. 0x000FFFFF (1 MiB), reset PC = 0x00000000.
 *   Initial SP = 0x00100000 (top of RAM), 16-byte aligned, growing downward.
 *   An explicit 64 KiB stack region is reserved at the top of RAM.
 */
ENTRY(_start)

MEMORY
{
  RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 0x00100000
}

STACK_SIZE = 0x10000; /* 64 KiB, explicitly reserved per prompt Section 5 */

SECTIONS
{
  . = 0x00000000;

  .text : {
    KEEP(*(.text.start))
    *(.text .text.*)
  } > RAM

  .rodata : {
    *(.rodata .rodata.*)
  } > RAM

  .init_array : {
    PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))
    KEEP(*(.init_array))
    PROVIDE_HIDDEN(__init_array_end = .);
  } > RAM

  .data : {
    . = ALIGN(4);
    _data_start = .;
    *(.data .data.*)
    _data_end = .;
  } > RAM

  .bss : {
    . = ALIGN(4);
    _bss_start = .;
    *(.bss .bss.*)
    *(COMMON)
    _bss_end = .;
  } > RAM

  . = ALIGN(16);
  _heap_start = .;

  _stack_top    = ORIGIN(RAM) + LENGTH(RAM);
  _stack_bottom = _stack_top - STACK_SIZE;
  _heap_end     = _stack_bottom;
}

ASSERT(_heap_start <= _heap_end,
       "link.ld: code+rodata+data+bss leave no room before the reserved 64 KiB stack region")
ASSERT((_stack_top % 16) == 0, "link.ld: stack top must be 16-byte aligned")
