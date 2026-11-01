# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/key_write.py - is one of the "SPACE held" bytes DirectInput's keyboard? Test it by WALKING.
#
# DirectInput keeps the whole keyboard as one row of 256 bytes - one byte per key, 0x80 = held, 0 = not.
# Every key has a fixed number (its place in the row): SPACE = 0x39, W = 0x11, A = 0x1E, S = 0x1F, D = 0x20, R = 0x13.
# So if find_key found SPACE at address X, the row starts at X - 0x39, and W sits at (X - 0x39) + 0x11.
# Space does nothing when nobody lies near you - but W walks. So for every address you give:
#   1. check the 256 bytes around it really look like a keyboard row (only 0x00 / 0x80 in it)
#   2. write 0x80 into its W for 1 second (you should walk UP), then 0 again
#   3. check by itself whether you moved
#
#   python -m helpers_for_me.key_write 0x1823bb6 0x733fc64 0xd3bf3408     (the places from find_key 0x80)
#   be in a level with free space ABOVE you, nobody around. Stay in the TERMINAL: we want it to work in the background.
import os
import sys
import time

from core.enemies import find_me
from core.memory import attach, open_rw, wait

SPACE = 0x39  # DirectInput's number for the space bar
W = 0x11  # ... and for W
ROW = 256  # keys in DirectInput's keyboard row
HOLD = 1.0  # seconds of "W held"
HELD, RELEASED = b"\x80", b"\x00"
MOVED = 5  # game units - less than this is "didn't move"

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.key_write 0x1823bb6 0x733fc64 ...   (from find_key 0x80)")
spaces = [int(text, 16) for text in sys.argv[1:]]

mem, regions, static_regions = attach()
mem_rw = open_rw()
wait("hands OFF the keyboard and mouse - watch your character, it should walk UP", 4)

for space in spaces:
    start = space - SPACE  # where the row would start, if this really is DirectInput's keyboard
    w = start + W
    try:
        row = os.pread(mem, ROW, start)
    except OSError:
        print(f"{space:#x}: can't read the 256 bytes around it - skipped")
        continue
    odd = [value for value in row if value not in (0x00, 0x80)]
    if odd:
        # a keyboard row has nothing but 0x00 and 0x80 in it - writing into something else could crash the game
        print(f"{space:#x}: NOT a keyboard row ({len(odd)} bytes are neither 0x00 nor 0x80, e.g. {odd[0]:#x}) - skipped")
        continue
    before = find_me(mem)
    if before is None:
        raise SystemExit("can't find you - are you in a level?")
    end = time.monotonic() + HOLD
    while time.monotonic() < end:
        os.pwrite(mem_rw, HELD, w)  # keep writing: the game might put the real "not held" back
        time.sleep(0.005)
    os.pwrite(mem_rw, RELEASED, w)
    time.sleep(0.3)
    after = find_me(mem)
    if after is None:
        print(f"{space:#x}: W at {w:#x} -> lost you (dead? new floor?)")
        continue
    dx, dy = after[0] - before[0], after[1] - before[1]
    walked = "WALKED!" if abs(dx) > MOVED or abs(dy) > MOVED else "didn't move"
    print(f"{space:#x}: W at {w:#x} -> {walked}  you went from ({before[0]:.0f}, {before[1]:.0f}) to ({after[0]:.0f}, {after[1]:.0f})")
    time.sleep(0.5)
