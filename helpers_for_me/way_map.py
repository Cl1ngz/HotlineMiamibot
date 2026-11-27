# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/way_map.py - why does the bot go THAT way? (a helper, only reads)
#
# Draws the bot's map around you - the same blocked cells walk() uses - and the way find_path finds
# from you to the car (or, with no car ready, to the crosshair). One character = one 16 x 16 cell:
#   @  you     G  the goal     *  the way     #  wall (the bot knows it)     .  free floor
#   o  a wall-layer card the map does NOT know (no box) - if the way goes through o's, that's the hole
#
#   python -m helpers_for_me.way_map         the bot must NOT run (stand where it got stuck)
import sys

from core.enemies import find_aim_card, find_me_card, shelf_cards
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records
from core.path import blocked_cells, cell_of, find_path
from core.scenes import load_doors, scene_id
from core.stairs import find_car
from core.walls import WALL, door_boxes, read_box, real_walls

WIDE = 1024  # cards this far around the table (at the end of a level things sit far from it)
MARGIN = 6  # cells drawn around you and the goal

mem, regions, static_regions = attach()
records = table_records(mem)
if not records:
    raise SystemExit("no table - are you in a level?")
me = find_me_card(mem)
if me is None:
    raise SystemExit("can't find you")
you = (read_double(mem, me + X_OFF), read_double(mem, me + Y_OFF))
cards = shelf_cards(mem, records, WIDE)

# the bot's map: the same boxes see.py blocks (walls + sofas + the fake doors of this floor)
walls = real_walls(mem, records, cards)
fake = load_doors().get(scene_id(walls), [])
blocked = blocked_cells([box for xy, box in walls] + [tuple(box) for box in fake])
doors = set(blocked_cells(list(door_boxes(mem, cards))))

goal = find_car(mem, records, cards)
what = "the car"
if goal is None:
    aim = find_aim_card(mem)
    if aim is None:
        raise SystemExit("no car and no crosshair - aim somewhere and run again")
    goal, what = (
        read_double(mem, aim + X_OFF),
        read_double(mem, aim + Y_OFF),
    ), "the crosshair"
path = find_path(you, goal, blocked)
way = {cell_of(point) for point in path}

# wall-layer cards the map doesn't have (their box looks like junk)
unknown = set()
for card in cards:
    try:
        if read_kind(mem, card, 0, 0x14) != WALL:
            continue
        xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
        try:
            read_box(mem, card, xy)
        except OSError:
            unknown.add(cell_of(xy))
    except OSError:
        continue

ends = [cell_of(you), cell_of(goal)] + list(way)
x0, x1 = min(c[0] for c in ends) - MARGIN, max(c[0] for c in ends) + MARGIN
y0, y1 = min(c[1] for c in ends) - MARGIN, max(c[1] for c in ends) + MARGIN
print(
    f"you ({you[0]:.0f},{you[1]:.0f}) -> {what} ({goal[0]:.0f},{goal[1]:.0f}), the way: {len(path)} points"
)
print(
    f"cells x {x0}..{x1} (map x {x0 * 16}..{x1 * 16}), y {y0}..{y1} (map y {y0 * 16}..{y1 * 16})"
)
for cy in range(y0, y1 + 1):
    row = []
    for cx in range(x0, x1 + 1):
        cell = (cx, cy)
        if cell == cell_of(you):
            row.append("@")
        elif cell == cell_of(goal):
            row.append("G")
        elif cell in way:
            row.append("*")
        elif cell in blocked:
            row.append("#")
        elif cell in doors:
            row.append("D")
        elif cell in unknown:
            row.append("o")
        else:
            row.append(".")
    print(f"{cy * 16:5d} " + "".join(row))
print("the way:", " ".join(f"({x:.0f},{y:.0f})" for x, y in path[:40]), file=sys.stdout)
