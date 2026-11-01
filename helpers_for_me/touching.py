# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/touching.py - what is your character touching right now? (who stops you?)
#
# Your box (16 x 16 around your x, y) made a little bigger, against the box of every card near you
# (folder +0x78..+0x84, the box_hunt find). Every box that overlaps yours is printed - one of them stops you.
#
#   python -m helpers_for_me.touching     (stand where the bot got stuck - right after walk_test's STUCK,
#                                          don't move - and run it. Then once more while YOU hold the key.)
import math

from core.enemies import RECORD, find_me_card
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, read_u32, table_records

BOX = 0x78  # folder +0x78 left, +0x7C top, +0x80 right, +0x84 bottom
NEAR = 48  # look at cards this close to you
EXTRA = 3  # make your box this much bigger - "touching" counts too

mem, regions, static_regions = attach()


def signed(value):
    return value - (1 << 32) if value >= 1 << 31 else value


def box_of(card, x, y):
    """(left, top, right, bottom) with right/bottom as the EDGE (+1), in map numbers. None = no sane box."""
    folder = read_u32(mem, card)
    left, top, right, bottom = (signed(read_u32(mem, folder + BOX + 4 * i)) for i in range(4))
    if abs(left) < abs(left - x):  # counted from x, y (sofas, you)
        left, right, top, bottom = left + x, right + x, top + y, bottom + y
    if not (0 <= right - left < 200 and 0 <= bottom - top < 200) or (left, top, right, bottom) == (0, 0, 0, 0):
        return None
    return left, top, right + 1, bottom + 1


me = find_me_card(mem)
if me is None:
    raise SystemExit("can't find you - are you in a level?")
you = (read_double(mem, me + X_OFF), read_double(mem, me + Y_OFF))
mine = box_of(me, *you)
print(f"you at ({you[0]:.1f}, {you[1]:.1f})  your box {mine}")
if mine is None:
    raise SystemExit("can't read your box")
left, top, right, bottom = mine[0] - EXTRA, mine[1] - EXTRA, mine[2] + EXTRA, mine[3] + EXTRA

table = table_records(mem)
found = 0
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    if card == me:
        continue
    try:
        x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        if not (0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000) or math.dist((x, y), you) > NEAR:
            continue
        box = box_of(card, x, y)
        layer = read_kind(mem, card, 0, 0x14)
        picture = read_kind(mem, card, 1, 0x10)
    except OSError:
        continue
    if box is None:
        continue
    # two boxes overlap when each one starts before the other one ends - on both axes
    if box[0] < right and left < box[2] and box[1] < bottom and top < box[3]:
        where = "table" if card in table else "SHELF"
        size = f"{box[2] - box[0]}x{box[3] - box[1]}"
        print(f"  TOUCHING {card:#x} at ({x:.1f}, {y:.1f})  layer {layer:#x}  picture {picture:#x}  box {box} ({size})  {where}")
        found += 1
if not found:
    print("  touching nothing")
