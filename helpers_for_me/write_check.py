# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/write_check.py - did the write really land? (the write_aim mystery)
#
# In write_aim the X read right after the write was still the old one - even though the game had no time
# to put it back. This looks closer: what pwrite answers, what both doors read, and which part of maps
# the crosshair card sits in.
#
#   python -m helpers_for_me.write_check        (be in a level, let go of the mouse when the pop-up says so)
import os
import struct

from core.enemies import find_aim, find_aim_card
from core.memory import X_OFF, attach, find_game, wait

mem, regions, static_regions = attach()
pid = find_game()[0]
mem_rw = os.open(f"/proc/{pid}/mem", os.O_RDWR)

find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("move the mouse a little, then LET GO of it", 3)
card = find_aim_card(mem)
if card is None:
    raise SystemExit("no crosshair - are you in a level?")
address = card + X_OFF
print(f"pid {pid}, crosshair X at {address:#x}")

# which line of maps holds this address, and what is allowed there (r w x)
with open(f"/proc/{pid}/maps") as f:
    for line in f:
        start, end = (int(part, 16) for part in line.split()[0].split("-"))
        if start <= address < end:
            print(f"maps: {line.strip()}")


def show(label):
    """X through both doors: the read-only one from attach() and our read-write one."""
    through_ro = struct.unpack("<d", os.pread(mem, 8, address))[0]
    through_rw = struct.unpack("<d", os.pread(mem_rw, 8, address))[0]
    print(f"  {label:24} read-only door: {through_ro:8.1f}   read-write door: {through_rw:8.1f}")


show("before")
old = struct.unpack("<d", os.pread(mem_rw, 8, address))[0]
written = os.pwrite(mem_rw, struct.pack("<d", old + 60), address)
print(f"  pwrite says it wrote {written} bytes (wanted {old + 60:.1f})")
show("right after the write")
for i in range(1, 6):
    show(f"again ({i})")
