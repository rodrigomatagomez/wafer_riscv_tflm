/* Directed test 009: a small compiled C program covering loops, functions,
 * the stack (recursion), and arrays, per prompt Section 6.
 */
#include "mmio.h"

static int fib(int n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

static int sum_array(const int *arr, int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += arr[i];
    }
    return total;
}

static void bubble_sort(int *arr, int n) {
    for (int i = 0; i < n - 1; i++) {
        for (int j = 0; j < n - 1 - i; j++) {
            if (arr[j] > arr[j + 1]) {
                int tmp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = tmp;
            }
        }
    }
}

static void fail_and_halt(void) {
    MMIO_TX = 0;
    __asm__ volatile("ebreak");
    while (1) {}
}

int main(void) {
    if (fib(10) != 55) fail_and_halt();

    int arr[8] = {8, 3, 7, 1, 9, 2, 6, 4};
    int total = sum_array(arr, 8);
    if (total != (8 + 3 + 7 + 1 + 9 + 2 + 6 + 4)) fail_and_halt();

    bubble_sort(arr, 8);
    for (int i = 0; i < 7; i++) {
        if (arr[i] > arr[i + 1]) fail_and_halt();
    }
    if (arr[0] != 1 || arr[7] != 9) fail_and_halt();

    /* recursion depth / stack exercise */
    if (fib(15) != 610) fail_and_halt();

    MMIO_TX = 1;
    __asm__ volatile("ebreak");
    while (1) {}
}
