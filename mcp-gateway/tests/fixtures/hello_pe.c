// Minimal Windows PE for run_die / run_file PE detection tests.
// Build with mingw-w64:
//   x86_64-w64-mingw32-gcc -O2 -s -o hello_pe.exe hello_pe.c
// Yields ~30-60 KB PE.

#include <windows.h>
int main(void) {
    MessageBoxA(0, "Hello, MARE!", "MARE", MB_OK);
    return 0;
}
