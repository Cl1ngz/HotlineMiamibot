# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/unknown_obstacles.py - what does the bot walk into? (a helper, only reads)
#
# The bot's map knows only the wall layer (walls, sofas) and the doors. This lists every OTHER thing near
# you that has a box (folder +0x78, like the walls) covering floor the map thinks is free - a train, a
# railing, a counter... grouped by kind (layer, +0x10, picture). The kind with the most "free cells it
# covers" is the one to add to the walls - then the way goes around it and the bumps stop.
#
#   python -m helpers_for_me.unknown_obstacles        stand where the bot got stuck, the bot must NOT run
#   python -m helpers_for_me.unknown_obstacles 300    things up to 300 away (default 200)
import math
import sys
from collections import defaultdict

from core.enemies import find_me_card, is_enemy, load_rules, shelf_cards
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records
from core.path import blocked_cells
from core.walls import BOX, WALL, door_boxes, read_box, real_walls, signed

RANGE = float(sys.argv[1]) if len(sys.argv) > 1 else 200
WIDE = 1024  # cards this far around the table (at the end of a level things sit far from it)
# you, the crosshair (the wall layer: only the pieces the map threw away)
SKIP = {0x2C, 0xAF}
# a weapon lying around: layer -100, +0x10 7 - not in the way
FLOOR, WEAPON = 0xFFFFFF9C, 7
# a box bigger than this is junk (the walls allow 512 - a train may be longer)
BIGGEST = 4096
CLOSE = 40  # the last list: every card this close to you


def box_of(card, xy):
    """(left, top, right, bottom) from the folder, like core/walls.read_box but for big things too - or None."""
    x, y = xy
    left, top, right, bottom = (
        signed(read_kind(mem, card, 1, BOX + 4 * i)) for i in range(4)
    )
    if abs(left) < abs(left - x):  # counted from x, y
        left, right, top, bottom = left + x, right + x, top + y, bottom + y
    if not (1 <= right - left <= BIGGEST and 1 <= bottom - top <= BIGGEST):
        return None
    return left, top, right + 1, bottom + 1


mem, regions, static_regions = attach()
rules = load_rules()
records = table_records(mem)
if not records:
    raise SystemExit("no table - are you in a level?")
me = find_me_card(mem)
if me is None:
    raise SystemExit("can't find you - stand in the level (not in the menu)")
you = (read_double(mem, me + X_OFF), read_double(mem, me + Y_OFF))
cards = shelf_cards(mem, records, WIDE)
walls = real_walls(mem, records, cards)
known = blocked_cells([box for xy, box in walls] + list(door_boxes(mem, cards)))
print(
    f"you at ({you[0]:.0f}, {you[1]:.0f}), {len(walls)} wall pieces, {len(known)} blocked cells on the map"
)

kinds = defaultdict(
    list
)  # (layer, +0x10, picture) -> [(card, xy, box, free cells it covers)]
for card in cards:
    try:
        layer = read_kind(mem, card, 0, 0x14)
        state = read_kind(mem, card, 0, 0x10)
        if layer in SKIP or (layer == FLOOR and state == WEAPON):
            continue
        if layer == WALL:
            try:
                read_box(
                    mem,
                    card,
                    (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)),
                )
                continue  # a wall piece the map has
            except OSError:
                pass  # its box looked like junk to the map (too big?) - is it really?
        xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
        if math.dist(xy, you) > RANGE or is_enemy(mem, card, rules):
            continue
        box = box_of(card, xy)
        picture = read_kind(mem, card, 1, 0x10)
    except OSError:
        continue
    if box is None:
        continue
    free = blocked_cells([box]) - known  # floor the map thinks you can walk on
    if free:
        kinds[(layer, state, picture)].append((card, xy, box, len(free)))

if not kinds:
    print(f"\nnothing with a box on free floor within {RANGE:.0f} of you")
print(
    f"\nthings with a box on 'free' floor within {RANGE:.0f} of you, the biggest kinds first:"
)
for (layer, state, picture), things in sorted(
    kinds.items(), key=lambda k: -sum(t[3] for t in k[1])
):
    print(
        f"\nlayer {layer:#x}  +0x10 {state:#x}  picture {picture:#x}:  {len(things)} thing(s), "
        f"{sum(t[3] for t in things)} free cells covered"
    )
    for card, (x, y), (left, top, right, bottom), cells in sorted(
        things, key=lambda t: -t[3]
    )[:8]:
        print(
            f"  {card:#x} at ({x:4.0f},{y:4.0f})  box {left:.0f},{top:.0f} - {right:.0f},{bottom:.0f}"
            f"  ({right - left:.0f} x {bottom - top:.0f})  {cells} cells"
        )

# no box at all, right next to you: the edge you're pushing into may be one of these
print(
    f"\neverything within {CLOSE} of you (any box or none), but you and the crosshair:"
)
for card in cards:
    try:
        layer = read_kind(mem, card, 0, 0x14)
        xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
        if layer in SKIP or math.dist(xy, you) > CLOSE:
            continue
        state = read_kind(mem, card, 0, 0x10)
        picture = read_kind(mem, card, 1, 0x10)
        box = box_of(card, xy)
    except OSError:
        continue
    print(
        f"  {card:#x} at ({xy[0]:4.0f},{xy[1]:4.0f})  layer {layer:#x}  +0x10 {state:#x}  picture {picture:#x}"
        f"  box {'none' if box is None else ','.join(f'{v:.0f}' for v in box)}"
    )
