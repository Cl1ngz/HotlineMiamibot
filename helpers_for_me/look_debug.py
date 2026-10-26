# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/look_debug.py - why does find_look return None?
#
# find_look gives None when the fast way (KNOWN) fails AND the slow way finds 0 pairs or more than 1.
# This shows both: what lies at KNOWN right now, and EVERY pair the slow way finds.
#
#   python -m helpers_for_me.look_debug        (be in a level; move the mouse, then LET GO when told)
import numpy as np

from core.enemies import find_aim, find_aim_card
from core.look import GAP, KNOWN, is_look
from core.memory import X_OFF, Y_OFF, attach, read_double, take_snapshot, wait

mem, regions, static_regions = attach()
find_aim(mem)  # warm-up
wait("move the mouse a little, then LET GO of it", 3)
card = find_aim_card(mem)
if card is None:
    raise SystemExit("no crosshair - are you in a level?")
aim = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
print(f"crosshair card {card:#x} at {aim[0]!r}, {aim[1]!r}")


def peek(address):
    try:
        return repr(read_double(mem, address))
    except OSError:
        return "???"


print(f"\nKNOWN {KNOWN:#x}:  x = {peek(KNOWN)}   y (KNOWN - GAP) = {peek(KNOWN - GAP)}   is_look: {is_look(mem, KNOWN, aim)}")

pairs = []
for start, data in take_snapshot(mem, regions).items():
    for shift in (0, 4):
        count = (len(data) - shift) // 8
        values = np.frombuffer(data[shift : shift + count * 8], dtype="<d")
        for i in np.flatnonzero(values == aim[0]):
            address = start + shift + int(i) * 8
            if is_look(mem, address, aim):
                pairs.append(address)
print(f"\nthe slow way finds {len(pairs)} pair(s):")
for address in pairs:
    print(f"  x at {address:#x}, y at {address - GAP:#x}")
