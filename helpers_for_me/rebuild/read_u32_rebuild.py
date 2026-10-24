# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/rebuild/read_u32_rebuild.py - rebuild read_u32 from memory and test it on the live game
#
#   python -m helpers_for_me.rebuild.read_u32_rebuild        (be in a level)
#
# The expected values come from the real core/memory.py
import os

from core import memory
from core.enemies import find_me_card

TABLE_START = 0xBEB900


def read_u32(mem, address):
    raw_bytes = os.pread(mem, 4, address)
    # print(f"raw bytes at {address:#x}: {raw_bytes}")
    return int.from_bytes(raw_bytes, byteorder="little")


mem, regions, static_regions = memory.attach()
me = find_me_card(mem)
if me is None:
    raise SystemExit("can't find you - are you in a level?")
folder = memory.read_u32(mem, me)

# each test: (what it is, address, what should be there)
tests = [
    ("table slot 0", TABLE_START, memory.read_u32(mem, TABLE_START)),
    ("your folder link (card +0x00)", me, folder),
    ("your layer (card +0x14)", me + 0x14, 0x2C),
    ("your picture (folder +0x10)", folder + 0x10, 0x47),
]
for what, address, expected in tests:
    got = read_u32(mem, address)
    result = "OK  " if got == expected else "FAIL"
    got_text = hex(got) if isinstance(got, int) else repr(got)
    print(
        f"{result} {what:30} at {address:#x} -> {got_text}   (expected {expected:#x})\n"
    )
