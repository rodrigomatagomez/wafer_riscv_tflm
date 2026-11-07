/* Minimal newlib syscall stubs for bare-metal rv32im_core. Linking against
 * the toolchain's bundled newlib (rather than -nostdlib) is what lets TFLM's
 * C++ code use memcpy/memset/malloc/new etc. without reimplementing them;
 * these stubs are the small set of OS-level hooks newlib calls into. There
 * is no real OS here, so most either are no-ops or route through MMIO.
 */
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "../startup/mmio.h"

extern char _heap_start;
extern char _heap_end;
static char *heap_ptr = &_heap_start;

void *_sbrk(ptrdiff_t incr) {
    char *prev = heap_ptr;
    if (heap_ptr + incr > &_heap_end) {
        errno = ENOMEM;
        return (void *)-1;
    }
    heap_ptr += incr;
    return prev;
}

int _write(int fd, const char *buf, int len) {
    if (fd != 1 && fd != 2) {
        errno = EBADF;
        return -1;
    }
    for (int i = 0; i < len; i++) {
        mmio_putc(buf[i]);
    }
    return len;
}

int _read(int fd, char *buf, int len) {
    (void)fd; (void)buf; (void)len;
    return 0; /* EOF: no input device in this environment */
}

int _close(int fd) { (void)fd; return -1; }

int _fstat(int fd, struct stat *st) {
    (void)fd;
    st->st_mode = S_IFCHR;
    return 0;
}

int _isatty(int fd) { return (fd == 1 || fd == 2) ? 1 : 0; }

off_t _lseek(int fd, off_t offset, int whence) {
    (void)fd; (void)offset; (void)whence;
    return (off_t)-1;
}

int _kill(int pid, int sig) { (void)pid; (void)sig; errno = EINVAL; return -1; }

int _getpid(void) { return 1; }

void _exit(int status) {
    (void)status;
    __asm__ volatile("ebreak");
    while (1) {}
}
