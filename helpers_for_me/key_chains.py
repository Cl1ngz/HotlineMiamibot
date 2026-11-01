# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/key_chains.py - which saved chains STILL lead to DirectInput's keyboard row? (e.g. after a restart)
#
# find_path saved every chain from the fixed locker 0xBB0D68 to the keyboard row in chains_<target>.json.
# This follows every chain NOW and tests where it ends, the same way key_write did:
#   1. do the 256 bytes there look like a keyboard row (only 0x00 / 0x80)?
#   2. write 0x80 into W for 1 second (row + 0x11) - do you walk UP?
# A chain that walks after you restarted the game is one hands.py can trust.
#
#   python -m helpers_for_me.key_chains chains_1823b7d.json
#   be in a level with free space ABOVE you, nobody around. Stay in the terminal.
import json
import os
import sys
import time

from core.enemies import find_me
from core.memory import attach, open_rw, read_u32, wait

W = 0x11  # DirectInput's number for W
ROW = 256
HOLD = 1.0
MOVED = 5

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.key_chains chains_1823b7d.json")
with open(sys.argv[1]) as f:
    saved = json.load(f)

mem, regions, static_regions = attach()
mem_rw = open_rw()


def follow(chain):
    """Where this chain ends right now (None if a link on the way can't be read)."""
    *offsets, last = chain
    try:
        here = read_u32(mem, saved["start"])
        for offset in offsets:
            here = read_u32(mem, here + offset)
        return here + last
    except OSError:
        return None


def text(chain):
    *offsets, last = chain
    return "[0xbb0d68]" + "".join(f" -> +{offset:#x}" for offset in offsets) + f"  then +{last:#x}"


def walks(row):
    """Hold W in this row for HOLD seconds. True if you moved."""
    before = find_me(mem)
    if before is None:
        raise SystemExit("can't find you - are you in a level?")
    end = time.monotonic() + HOLD
    while time.monotonic() < end:
        os.pwrite(mem_rw, b"\x80", row + W)
        time.sleep(0.005)
    os.pwrite(mem_rw, b"\x00", row + W)
    time.sleep(0.3)
    after = find_me(mem)
    return after is not None and (abs(after[0] - before[0]) > MOVED or abs(after[1] - before[1]) > MOVED)


wait("hands OFF the keyboard and mouse - your character may walk UP a few times", 4)
tested = {}  # row address -> result, so two chains to the same place walk only once
for chain in saved["chains"]:
    row = follow(chain)
    if row is None:
        print(f"broken (a link can't be read)    {text(chain)}")
        continue
    if row not in tested:
        try:
            data = os.pread(mem, ROW, row)
        except OSError:
            data = b""
        if len(data) != ROW or any(value not in (0x00, 0x80) for value in data):
            tested[row] = "NOT a keyboard row"
        else:
            tested[row] = "WALKED!" if walks(row) else "a row, but you didn't move"
            time.sleep(0.5)
    print(f"{row:#x}  {tested[row]:26}  {text(chain)}")
