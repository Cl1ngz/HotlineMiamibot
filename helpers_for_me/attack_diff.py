# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/attack_diff.py - what in YOUR card and folder is different while you swing?
#
# attack_watch showed: while you swing, the picture stays 0x47 but the frame runs 0, 0.5, 1 ... 6.5, then back to 0.
# At rest the frame stands still. So something tells the frame to move ("turn the pages this fast") - and maybe
# other numbers say "I'm attacking". This copies your whole card (0xB8) and folder (0x6D0) every 5 ms while you
# swing with pauses, splits the copies into "swinging" (frame moving) and "resting" (frame standing still),
# and prints every spot whose values while swinging NEVER appear while resting.
#
#   python -m helpers_for_me.attack_diff
#   be in a level with a MELEE weapon, STAND STILL, swing at the air a few times WITH PAUSES between swings
import os
import struct
import time
from collections import Counter

from core.enemies import INSTANCE, RECORD, find_me_card
from core.memory import attach, read_u32, wait

WATCH_TIME = 6  # seconds
FRAME = 0x98  # the frame on the card
CALM = 6  # a copy counts as "resting" only if the frame is 0 in this many copies before AND after it (~30 ms)

mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level (and not attacking right now)?")
folder = read_u32(mem, card)
print(f"your card {card:#x}, your folder {folder:#x}")

wait("STAND STILL with a melee weapon. Swing at the air a few times - WITH PAUSES between swings", 3)
copies = []  # (frame, card bytes, folder bytes)
start = time.monotonic()
while time.monotonic() - start < WATCH_TIME:
    try:
        card_bytes = os.pread(mem, RECORD, card)
        folder_bytes = os.pread(mem, INSTANCE, folder)
    except OSError:
        continue
    copies.append((struct.unpack_from("<d", card_bytes, FRAME)[0], card_bytes, folder_bytes))
    time.sleep(0.005)

# sort the copies:
#   swinging = the frame is different ~30 ms before AND ~30 ms after (it's moving, we're inside a swing)
#   resting  = the frame stands still the whole time around it (whatever number it stands on)
# the moments where a swing starts or ends are neither - they're left out
frames = [frame for frame, _, _ in copies]
swing, rest = [], []
for i in range(CALM, len(copies) - CALM):
    nearby = frames[i - CALM : i + CALM + 1]
    if frames[i - CALM] != frames[i] != frames[i + CALM]:
        swing.append(copies[i][1:])
    elif len(set(nearby)) == 1:
        rest.append(copies[i][1:])
print(f"{len(swing)} copies while swinging, {len(rest)} while resting")
if not swing or not rest:
    common = Counter(frames).most_common(5)
    print("the frames seen most: " + ", ".join(f"{frame:.2f} ({count}x)" for frame, count in common))
    raise SystemExit("need both - swing a few times, with pauses in between")


def show(value, kind):
    return f"{value:#x}" if kind == "u32" else f"{value:.3f}"


def is_junk_double(value):
    # NaN, huge, or a tiny "almost zero" - that's two halves of other numbers read as one double
    return not abs(value) < 1e6 or (value != 0 and abs(value) < 1e-6)


found = []  # (where, offset, kind, resting values, swinging values)
for where in (0, 1):
    size = RECORD if where == 0 else INSTANCE
    for kind, fmt in (("u32", "<I"), ("double", "<d")):
        width = struct.calcsize(fmt)
        for offset in range(0, size - width + 1, 4):
            if where == 0 and offset < FRAME + 8 and offset + width > FRAME:
                continue  # that's (a part of) the frame itself - we know it moves
            swing_values = {struct.unpack_from(fmt, copy[where], offset)[0] for copy in swing}
            rest_values = {struct.unpack_from(fmt, copy[where], offset)[0] for copy in rest}
            if kind == "double" and any(is_junk_double(v) for v in swing_values | rest_values):
                continue
            if swing_values.isdisjoint(rest_values) and len(rest_values) <= 3:
                found.append((where, offset, kind, rest_values, swing_values))

# a double found at X also shows up as its two 4-byte halves (X and X+4) - show only the double
doubles = {(where, offset) for where, offset, kind, _, _ in found if kind == "double"}
found = [f for f in found if f[2] == "double" or not ({(f[0], f[1]), (f[0], f[1] - 4)} & doubles)]

print("\nspots that are different while swinging:")
for where, offset, kind, rest_values, swing_values in found:
    name = "card" if where == 0 else "folder"
    at_rest = ", ".join(show(v, kind) for v in sorted(rest_values))
    swinging = ", ".join(show(v, kind) for v in sorted(swing_values)[:6])
    more = " ..." if len(swing_values) > 6 else ""
    print(f"  {name:6} +{offset:#05x} {kind:6}  resting: {at_rest:20}  swinging: {swinging}{more}")
if not found:
    print("  nothing - everything that changes while swinging also happens at rest")
print("\nWhich of these could be 'how fast the frames turn'? Which could mean 'I'm attacking'?")
