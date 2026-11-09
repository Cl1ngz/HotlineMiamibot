# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/door_check.py - which doors does the bot think are walls? (a helper, only reads)
#
# core/walls.py blocks a door (fake_door_boxes) when it's on the floor layer with the folder picture 0x20 -
# a door that never opened on floor 2. On the ground floor by the car it looks mixed up: the bottom door can't
# be opened, but the way goes through it - and the way never goes through the real door by the small stairs.
# This prints, for THIS floor:
#   1. every door-like thing (a thin plank: 2-12 thick, 24-40 long) - with FAKE where the bot treats it as a wall
#   2. a small map of the bot's cells around the crosshair: # = blocked, . = free, + = the crosshair
#
#   python -m helpers_for_me.door_check      the bot NOT running, on that floor, the crosshair ON the real door
from core.enemies import find_aim
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, wait
from core.path import blocked_cells, cell_of
from core.shelf import Shelf
from core.walls import fake_door_boxes, read_box, real_walls

AROUND = 6  # the map: this many cells to every side of the crosshair

mem, regions, static_regions = attach()
find_aim(mem)  # warm-up: find_aim has to see the crosshair once
wait("put the crosshair on the door that DOES open, and keep it there", 3)
aim = find_aim(mem)
shelf = Shelf(mem)
records = shelf.records
if not records:
    raise SystemExit("no table - are you on a floor?")
walls = real_walls(shelf, records, shelf.cards)
fakes = fake_door_boxes(shelf, records)
print(f"walls {len(walls)}, fake doors {len(fakes)}, the crosshair at {aim}")

# 1. every thin plank on the floor
print("\ndoor-like things (a thin plank):")
for card in shelf.cards:
    try:
        xy = (read_double(shelf, card + X_OFF), read_double(shelf, card + Y_OFF))
        box = read_box(shelf, card, xy)
        layer = read_kind(shelf, card, 0, 0x14)
        state = read_kind(shelf, card, 0, 0x10)
        picture = read_kind(shelf, card, 1, 0x10)
    except OSError:
        continue
    width, height = box[2] - box[0], box[3] - box[1]
    thin, long = min(width, height), max(width, height)
    if not (2 <= thin <= 12 and 24 <= long <= 40) or layer == 0x9:
        continue  # not a plank, or a wall piece
    fake = "  <- FAKE: the bot treats it as a WALL" if box in fakes else ""
    place = "table" if card in records else "shelf"
    print(
        f"  {card:#x} at ({xy[0]:4.0f},{xy[1]:4.0f})  box {box}  layer {layer:#x}  +0x10 {state:#x}"
        f"  picture {picture:#x}  {place}{fake}"
    )

# 2. the bot's cells around the crosshair
if aim is None:
    raise SystemExit("\nno crosshair - no map around it")
blocked = blocked_cells([box for xy, box in walls] + fakes)
cx, cy = cell_of(aim)
print(f"\nthe bot's cells around the crosshair ({2 * AROUND + 1} x {2 * AROUND + 1}, # blocked, . free, + crosshair):")
for y in range(cy - AROUND, cy + AROUND + 1):
    row = ""
    for x in range(cx - AROUND, cx + AROUND + 1):
        row += "+" if (x, y) == (cx, cy) else "#" if (x, y) in blocked else "."
    print("  " + row)
print("\nsend me all of this")
