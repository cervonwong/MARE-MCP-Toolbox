; Tiny relocatable object -- for `run_nm mode="undefined"` tests.
; Build:
;   nasm -felf64 stripped.S -o stripped.o
;   strip --strip-all stripped.o   ; may be a no-op if nasm produces minimal symbols

global ret_zero
extern external_helper

section .text
ret_zero:
    call    external_helper
    xor     rax, rax
    ret
