# Phase 7 Test Fixtures (D-34)

Small public-domain binaries for `run_file`, `run_die`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`, `run_ropper`, `run_capstone_disasm`. Source for each binary lives alongside it so contributors can regenerate when test expectations change.

## hello_elf -- static x86_64 ELF Hello-World

Canonical source: `hello_elf.S` (NASM intel syntax).

Canonical build (when `nasm` + `ld` available):
```bash
nasm -felf64 hello_elf.S -o /tmp/hello_elf.o
ld -static -nostdlib -o hello_elf /tmp/hello_elf.o
rm /tmp/hello_elf.o
```

Fallback used during Phase 7 Wave 0 commit (host had no `nasm`): same syscall sequence emitted via gcc inline asm, then `strip --strip-unneeded`:
```bash
cat > /tmp/hello_elf_c.c <<'C'
__asm__(
"    .global _start\n"
"_start:\n"
"    mov $1, %rax\n"
"    mov $1, %rdi\n"
"    lea msg(%rip), %rsi\n"
"    mov $13, %rdx\n"
"    syscall\n"
"    mov $60, %rax\n"
"    xor %rdi, %rdi\n"
"    syscall\n"
".section .rodata\n"
"msg:\n"
"    .ascii \"Hello, MARE!\\n\"\n"
);
C
gcc -nostdlib -static -no-pie -o hello_elf /tmp/hello_elf_c.c
strip --strip-unneeded hello_elf
rm /tmp/hello_elf_c.c
```

Expected size: ~8-9 KB. Used by run_file (ELF detection), run_readelf (-h header parse), run_objdump (--disassemble), run_rabin2 (info), run_ropper (gadget search).

## hello_pe.exe -- minimal Windows PE32+

Canonical source: `hello_pe.c` (mingw-w64 cross).

Canonical build:
```bash
x86_64-w64-mingw32-gcc -O2 -s -o hello_pe.exe hello_pe.c
```

Expected size: ~30-60 KB. Used by run_die (packer/protector detection), run_file (PE32+ identification).

Fallback used during Phase 7 Wave 0 commit (host had no `mingw-w64`): hand-crafted DOS+PE header stub (~408 bytes). Sufficient for `file`/`die` to identify as PE x86-64 but NOT a complete executable. Regenerate with a proper mingw cross when possible:
```bash
python3 - <<'PY'
import struct
with open("hello_pe.exe", "wb") as f:
    dos = bytearray(64)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 60, 0x80)
    f.write(bytes(dos))
    f.write(b"\x00" * (0x80 - 64))
    f.write(b"PE\x00\x00")
    f.write(struct.pack("<HHIIIHH", 0x8664, 0, 0, 0, 0, 0xF0, 0x22))
    f.write(b"\x00" * 256)
PY
```

## stripped.o -- tiny ELF relocatable object

Canonical source: `stripped.S` (NASM).

Canonical build:
```bash
nasm -felf64 stripped.S -o stripped.o
```

Fallback used during Phase 7 Wave 0 commit: equivalent C source compiled with `gcc -c`, retains `external_helper` as undefined symbol so `run_nm mode="undefined"` returns at least one symbol:
```bash
cat > /tmp/stripped_c.c <<'C'
extern int external_helper(void);
int ret_zero(void) {
    external_helper();
    return 0;
}
C
gcc -c -o stripped.o /tmp/stripped_c.c
rm /tmp/stripped_c.c
```

Expected size: <20 KB. Used by run_nm (mode="undefined" -- has `external_helper` as undefined symbol).

## Total budget

All three binaries combined: < 200 KB. CI does not pre-build them; they're committed binaries.
