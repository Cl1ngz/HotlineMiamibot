# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/find_calls.py - WHERE in the game's code is a Windows function called, and what happens next?
#
# The game calls a Windows function through its slot in the import table: the instruction is
#   call dword ptr [SLOT]                    (bytes FF 15 + the slot's address)
# or it first loads the address into a register and calls that:
#   mov esi, dword ptr [SLOT] ... call esi   (bytes 8B 35 / 8B 3D / 8B 1D + the slot's address)
# This finds the slot of one function (e.g. GetFocus), searches the game's code for those bytes and shows
# the instructions right after every hit - there we see what the game does with the answer.
# It only READS - nothing is changed.
#
#   pip install capstone                            (once - it turns bytes into instructions)
#   python -m helpers_for_me.find_calls GetFocus
import os
import sys

import capstone

from core.memory import attach, find_game, find_game_file

AFTER = 48  # bytes of code to show from every hit on

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.find_calls GetFocus")
wanted = sys.argv[1]

mem, regions, static_regions = attach()
pid = find_game()[0]
exe = os.readlink(f"/proc/{pid}/exe")
wine = "wine" in os.path.basename(exe) or "preloader" in os.path.basename(exe)
base, path = find_game_file(pid, exe, wine)


def u32(address):
    return int.from_bytes(os.pread(mem, 4, address), "little")


def text(address):
    return os.pread(mem, 128, address).split(b"\0")[0].decode("ascii", "replace")


# 1. find the function's slot in the import table (like imports.py)
optional = base + u32(base + 0x3C) + 24
descriptor = base + u32(optional + 96 + 8)
slot = None
while slot is None:
    names_rva, _, _, dll_rva, iat_rva = (u32(descriptor + 4 * i) for i in range(5))
    if dll_rva == 0:
        break
    i = 0
    while True:
        entry = u32(base + (names_rva or iat_rva) + 4 * i)
        if entry == 0:
            break
        if not entry & 0x80000000 and text(base + entry + 2) == wanted:
            slot = base + iat_rva + 4 * i
            break
        i += 1
    descriptor += 20
if slot is None:
    raise SystemExit(f"{wanted} isn't in the game's import table")
print(f"{wanted}: the game keeps its address at {slot:#x}")

# 2. the game's code: the r-x part of the game file (from maps)
code = []
with open(f"/proc/{pid}/maps") as f:
    for line in f:
        parts = line.split()
        start, end = (int(x, 16) for x in parts[0].split("-"))
        if "x" in parts[1] and base <= start < base + 0x1000000:
            code.append((start, end))

# 3. search the code for "call [slot]" and "mov reg, [slot]"
needle = slot.to_bytes(4, "little")
patterns = {b"\xff\x15": "call [slot]", b"\x8b\x35": "mov esi, [slot]", b"\x8b\x3d": "mov edi, [slot]",
            b"\x8b\x1d": "mov ebx, [slot]", b"\xa1": "mov eax, [slot]"}
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
hits = 0
for start, end in code:
    data = os.pread(mem, end - start, start)
    for prefix, meaning in patterns.items():
        at = data.find(prefix + needle)
        while at != -1:
            hits += 1
            address = start + at
            print(f"\n--- hit {hits}: {meaning} at {address:#x} ---")
            # start decoding exactly at the hit (x86 instructions have different lengths -
            # starting anywhere else could cut an instruction in half and read nonsense)
            for ins in md.disasm(data[at : at + AFTER], address):
                mark = "   <== the hit" if ins.address == address else ""
                print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}{mark}")
            at = data.find(prefix + needle, at + 1)
print(f"\n{hits} place(s) use {wanted}")
