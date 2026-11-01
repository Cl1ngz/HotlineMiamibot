# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/arrow_hunt.py - the game draws an arrow over WHAT TO DO NEXT (GO! over the stairs, the red arrow
# over the briefcase, later the car). Somewhere it keeps "the arrow is over this one". Let's find that.
#
# What we know: when floor 1 got clear, the stairs card (+0x10 = 0x51) changed  +0x48: 1 -> 0  and  +0x90: 0 -> 1.
# Maybe +0x90 = 1 means "the arrow is over me" for EVERY kind of goal. This lists:
#   1. every card (not walls, not you, not the crosshair) with +0x48 or +0x90 not 0, from the whole shelf
#   2. with "aim": every card close to the crosshair, with the same numbers - aim at the briefcase / the arrow
#
#   python -m helpers_for_me.arrow_hunt          the list
#   python -m helpers_for_me.arrow_hunt aim      the list + what's under the crosshair (3 s to aim)
# Run it at 3 moments: floor 1 clear (GO! on the stairs) / the briefcase lying with its red arrow /
# back down after taking the briefcase ("run to the car").
import math
import sys
from collections import Counter

from core.enemies import RECORD, find_aim
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, read_u32, table_records, wait

FLAGS = (0x48, 0x90)  # the two spots that flipped on the stairs
SKIP = (0x2C, 0xAF)  # you, the crosshair
CLOSE = 24

mem, regions, static_regions = attach()
AIM = len(sys.argv) > 1 and sys.argv[1] == "aim"
aim = None
if AIM:
    find_aim(mem)  # warm-up
    wait("aim at the briefcase / the thing the arrow points at, hold still", 3)
    aim = find_aim(mem)

table = table_records(mem)
if not table:
    raise SystemExit("nothing in the table - menu or loading?")
layers = Counter()
for card in table:
    try:
        layers[read_kind(mem, card, 0, 0x14)] += 1
    except OSError:
        continue
wall_layer = layers.most_common(1)[0][0]

flagged, near = [], []
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        if not (0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000):
            continue
        layer = read_kind(mem, card, 0, 0x14)
        if layer in SKIP or layer == wall_layer:
            continue
        kind = read_kind(mem, card, 0, 0x10)
        picture = read_kind(mem, card, 1, 0x10)
        flags = [read_u32(mem, card + offset) for offset in FLAGS]
    except OSError:
        continue
    line = (
        f"  {card:#x} at ({x:5.0f},{y:5.0f})  layer {layer:#10x}  +0x10 {kind:#6x}  picture {picture:#6x}"
        f"  +0x48 {flags[0]:#x}  +0x90 {flags[1]:#x}  {'table' if card in table else 'SHELF'}"
    )
    if any(flags) and max(flags) < 0x100:  # big numbers there are something else (links, junk)
        flagged.append(line)
    if aim is not None and math.dist((x, y), aim) < CLOSE:
        near.append(line)

print(f"cards with +0x48 or +0x90 set (walls layer {wall_layer:#x}, you and the crosshair skipped):")
print("\n".join(flagged) if flagged else "  none")
if AIM:
    print(f"\nclose to the crosshair {aim[0]:.0f},{aim[1]:.0f}:" if aim else "\nno crosshair found")
    print("\n".join(near) if near else "  nothing")
