; Minimal static ELF64 "hello" -- for run_file / run_readelf / run_objdump / run_nm / run_rabin2 / run_ropper tests.
; Build:
;   nasm -felf64 hello_elf.S -o hello_elf.o
;   ld -static -nostdlib -o hello_elf hello_elf.o
; Yields ~8 KB static ELF.

global _start
section .text
_start:
    mov     rax, 1          ; sys_write
    mov     rdi, 1          ; stdout
    lea     rsi, [rel msg]
    mov     rdx, msglen
    syscall

    mov     rax, 60         ; sys_exit
    xor     rdi, rdi
    syscall

section .rodata
msg:    db "Hello, MARE!", 10
msglen  equ $ - msg
