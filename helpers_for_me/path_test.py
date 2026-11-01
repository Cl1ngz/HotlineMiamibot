# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/path_test.py - does core/path.py find a way around the walls? Draws it in the terminal.
#
# Start = you, goal = the crosshair (put it somewhere you CAN'T walk to in a straight line - around a corner,
# into the next room). It runs find_path, says how long it took and draws the map:
#   #  wall      *  the way      A  you      B  the crosshair      .  floor
#
#   python -m helpers_for_me.path_test      (be in a level; move the mouse when told, then hold it still)
import math
import time

from core.enemies import find_aim, find_me, load_rules
from core.memory import attach, table_records, wait
from core.path import CELL, cell_of, find_path
from core.walls import find_walls, wall_lines

MARGIN = 3  # cells of map around the way

mem, regions, static_regions = attach()
rules = load_rules()
if not rules:
    raise SystemExit("no enemy rules yet - the walls are found with them")

find_aim(mem)  # warm-up: find_aim has to see the crosshair move once to tell it from a frozen copy
wait("move the mouse to a place AROUND A CORNER from you, then hold it still", 4)
you = find_me(mem)
goal = find_aim(mem)
if you is None or goal is None:
    raise SystemExit("can't find you or the crosshair - are you in a level?")

lines = wall_lines(find_walls(mem, table_records(mem), rules))
start = time.perf_counter()
path = find_path(you, goal, lines)
ms = (time.perf_counter() - start) * 1000

print(f"you {you[0]:.0f},{you[1]:.0f}  ->  crosshair {goal[0]:.0f},{goal[1]:.0f}   ({len(lines)} wall lines)")
if path is None:
    print(f"NO WAY found ({ms:.0f} ms)")
else:
    walked = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
    print(f"way: {len(path)} cells, {walked:.0f} units long (straight line: {math.dist(you, goal):.0f})  in {ms:.0f} ms")

# the map: every cell a wall line goes through is '#'
walls = set()
for (x1, y1), (x2, y2) in lines:
    steps = max(1, int(math.dist((x1, y1), (x2, y2)) / (CELL / 4)))
    for i in range(steps + 1):
        walls.add(cell_of((x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)))
on_way = {cell_of(point) for point in path} if path else set()
corners = [cell_of(you), cell_of(goal)] + list(on_way)
left = min(c[0] for c in corners) - MARGIN
right = max(c[0] for c in corners) + MARGIN
top = min(c[1] for c in corners) - MARGIN
bottom = max(c[1] for c in corners) + MARGIN
for row in range(top, bottom + 1):
    text = ""
    for column in range(left, right + 1):
        cell = (column, row)
        if cell == cell_of(you):
            text += "A"
        elif cell == cell_of(goal):
            text += "B"
        elif cell in on_way:
            text += "*"
        elif cell in walls:
            text += "#"
        else:
            text += "."
    print(text)
