# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/under_aim.py - what's under the crosshair?
# Every card close to the crosshair, with its layer and picture number, and whether the table knows it.
#
#   python -m helpers_for_me.under_aim      (a pop-up and a 3 s countdown give you time to aim)
import math

from enemies import RECORD, find_aim
from memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records, wait

CLOSE = 20  # game units around the crosshair

mem, regions, static_regions = attach()
find_aim(
    mem
)  # first look - find_aim needs to see the crosshair move to tell it from a frozen copy
wait("aim at the thing you want to check and hold the mouse still", 3)
aim = find_aim(
    mem
)  # second look: you moved the mouse, so now it knows the live crosshair
if aim is None:
    raise SystemExit("no crosshair - are you in a level?")
print(f"crosshair at {aim[0]:.0f}, {aim[1]:.0f}")

# walk the whole shelf (not just the table) - things can live on the shelf without being in the table
table = table_records(mem)
found = 0
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
        if math.dist(xy, aim) >= CLOSE:
            continue
        layer = read_kind(mem, card, 0, 0x14)
        picture = read_kind(mem, card, 1, 0x10)
        frame = read_double(mem, card + 0x98)  # weapon number? (testing)
    except OSError:
        continue  # junk memory past the ends of the shelf
    in_table = "in table" if card in table else "NOT in table"
    print(
        f"  {hex(card)}  at {xy[0]:6.1f}, {xy[1]:6.1f}  layer {layer:#10x}  picture {picture:#6x}   frame {frame:g}  {in_table}"
    )
    found += 1
if not found:
    print("  nothing close to the crosshair")
