# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/walls_check.py - where are the walls right now: in the table, or only on the shelf?
#
# core/walls.py takes "the layer most TABLE cards have" as the walls. Back down on floor 1 at the end of the level
# that gave only 9 boxes - as if the walls had left the table (like the stairs card did). This counts:
#   - the most common layers in the table
#   - wall-layer cards (layer 9) in the table / only on the shelf, and how many of them have a real box
#   - the same further away from the table (in case the walls live outside the usual +-64 cards)
#
#   python -m helpers_for_me.walls_check     floor 1 at the START, then floor 1 again at the END (hmbot stopped)
from collections import Counter

from core.enemies import RECORD, load_rules
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records
from core.walls import read_box, wall_boxes

WALL = 0x9  # the wall layer every floor had so far
LAYER = 0x14

mem, regions, static_regions = attach()
rules = load_rules()
table = table_records(mem)
if not table:
    raise SystemExit("the table is empty - menu or loading?")

layers = Counter()
for card in table:
    try:
        layers[read_kind(mem, card, 0, LAYER)] += 1
    except OSError:
        continue
print(f"table: {len(table)} cards. Most common layers:")
for layer, count in layers.most_common(5):
    print(f"  layer {layer:#10x}: {count}")


def count_walls(spread):
    """(in table, only on the shelf, with a real box) for wall-layer cards up to `spread` cards around the table."""
    in_table = shelf_only = boxed = 0
    for card in range(min(table) - spread * RECORD, max(table) + spread * RECORD + 1, RECORD):
        try:
            xy = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
            if not (0.01 < abs(xy[0]) < 100000 and 0.01 < abs(xy[1]) < 100000):
                continue
            if read_kind(mem, card, 0, LAYER) != WALL:
                continue
        except OSError:
            continue
        if card in table:
            in_table += 1
        else:
            shelf_only += 1
        try:
            read_box(mem, card, xy)  # raises OSError on junk (MAX_BOX)
            boxed += 1
        except OSError:
            pass
    return in_table, shelf_only, boxed


for spread in (64, 1024):
    in_table, shelf_only, boxed = count_walls(spread)
    print(
        f"layer {WALL:#x} within {spread:4} cards of the table: {in_table} in the table, "
        f"{shelf_only} only on the shelf, {boxed} with a real box"
    )
print(f"wall_boxes (what the bot uses now): {len(wall_boxes(mem, table, rules))} boxes")
