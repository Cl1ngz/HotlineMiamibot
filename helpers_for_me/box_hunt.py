# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/box_hunt.py - how BIG is a thing? Hunting for its box (left, top, right, bottom) in memory.
#
# The walls and the sofas are in the wall layer, but we only know ONE point of each (its x, y), so
# core/walls.py draws a thin line there - while a sofa is a whole block, and the bot walks into it.
# The game must know every thing's box (it checks who bumps into what). A box is 4 whole numbers close
# to x and y: like  left = x - 16, top = y, right = x, bottom = y + 16.  This looks for such numbers.
#
# For every card close to the crosshair it prints the 4-byte spots (in the card AND in its folder)
# holding a whole number close to the card's x or y, written as "x-16" / "y+8".
#
#   python -m helpers_for_me.box_hunt     aim at a SOFA piece and hold still. Then run it again aiming
#                                         at a plain WALL, then once more aiming at YOURSELF.
#                                         If the same spots show up every time -> that's the box.
import math

from core.enemies import RECORD, find_aim
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, read_u32, table_records, wait

CLOSE = 24  # cards this close to the crosshair
NEAR = 64  # a number this close to x or y is interesting
FOLDER = 0x6D0  # bytes in a folder
BOX = 0x78  # walls: folder +0x78 left, +0x7C top, +0x80 right, +0x84 bottom (found with this script)
KNOWN = range(X_OFF, X_OFF + 0x20)  # x, y and their copies (doubles) - we know those already

mem, regions, static_regions = attach()
find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("aim at the thing (a sofa piece / a wall / yourself) and hold the mouse still", 3)
aim = find_aim(mem)
if aim is None:
    raise SystemExit("no crosshair - are you in a level?")
print(f"crosshair at {aim[0]:.0f}, {aim[1]:.0f}")


def signed(value):
    """A 4-byte number read as a whole number that can be below zero."""
    return value - (1 << 32) if value >= 1 << 31 else value


def close_numbers(start, size, x, y, skip=()):
    """[(offset, 'x-16'), ...]: every 4-byte spot from start to start + size holding a number close to x or y."""
    found = []
    for offset in range(0, size, 4):
        if offset in skip:
            continue
        try:
            value = signed(read_u32(mem, start + offset))
        except OSError:
            break
        if value == 0:
            continue  # 0 is everywhere - it says nothing
        if min(abs(value - x), abs(value - y)) > NEAR:
            continue
        # x and y can be close to each other - name it after the closer one
        if abs(value - x) <= abs(value - y):
            found.append((offset, f"x{value - round(x):+d}"))
        else:
            found.append((offset, f"y{value - round(y):+d}"))
    return found


table = table_records(mem)
shown = 0
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        if not (0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000) or math.dist((x, y), aim) > CLOSE:
            continue
        layer = read_kind(mem, card, 0, 0x14)
        picture = read_kind(mem, card, 1, 0x10)
        folder = read_u32(mem, card)
    except OSError:
        continue
    if layer == 0xAF:
        continue  # the crosshair itself
    where = "table" if card in table else "SHELF"
    print(f"\n{card:#x} at ({x:.1f}, {y:.1f})  layer {layer:#x}  picture {picture:#x}  {where}")
    in_card = close_numbers(card, RECORD, x, y, skip=KNOWN)
    in_folder = close_numbers(folder, FOLDER, x, y)
    print("  card:   " + ("  ".join(f"+{o:#x}={t}" for o, t in in_card) or "nothing"))
    print("  folder: " + ("  ".join(f"+{o:#x}={t}" for o, t in in_folder) or "nothing"))
    try:
        left, top, right, bottom = (signed(read_u32(mem, folder + BOX + 4 * i)) for i in range(4))
        print(f"  box spot (folder +0x78..+0x84): left {left}  top {top}  right {right}  bottom {bottom}")
    except OSError:
        print("  box spot: can't read")
    shown += 1
if not shown:
    print("nothing close to the crosshair")
