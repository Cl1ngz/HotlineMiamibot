# https://github.com/Cl1ngz/HotlineMiamibot
# core/path.py - find a way around the walls: the "wave" (BFS) on a grid of cells (a library)
#
# The floor is cut into square cells, CELL x CELL. From your cell the "water" spreads to the cells next to it,
# then to theirs... but never into a BLOCKED cell. Every cell remembers where its water came from,
# so when the water reaches the goal we follow those "came from" arrows back to you.
#
# Blocked = your middle can't stand there. Every wall and sofa box is made HALF bigger on every side
# (HALF = half of your size), so the boxes already "contain" your body and you can be a single point.
# One set lookup per cell - the chunks idea (only look at what's near) taken all the way.
#
#   blocked_cells(boxes)              ->  {(cell x, cell y), ...}   (boxes from walls.wall_boxes)
#   find_path(start, goal, blocked)   ->  [(x, y), ...] points to walk through, start to goal  (None = no way)
import math
from collections import deque

# size of one cell in game units (a wall piece is 32)
CELL = 16
# stop flooding after this many cells - the goal is unreachable or very far
MAX_CELLS = 5000
# right, left, down, up
STEPS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
# you are 16 x 16 (box_hunt: -8..7), so your middle must stay this far from every box
HALF = 8


def cell_of(xy):
    """Which cell the point (x, y) is in."""
    return (int(xy[0] // CELL), int(xy[1] // CELL))


def middle(cell):
    """The point in the middle of a cell."""
    return (cell[0] * CELL + CELL / 2, cell[1] * CELL + CELL / 2)


def blocked_cells(boxes):
    """Every cell your MIDDLE can't stand in: its middle is inside a box made HALF bigger on every side.
    Then you can be treated as a point - the boxes already got your size."""
    blocked = set()
    for left, top, right, bottom in boxes:
        left -= HALF
        top -= HALF
        right += HALF
        bottom += HALF
        for cx in range(int(left // CELL), int(right // CELL) + 1):
            for cy in range(int(top // CELL), int(bottom // CELL) + 1):
                mx, my = middle((cx, cy))
                if left < mx < right and top < my < bottom:
                    blocked.add((cx, cy))

    return blocked


def find_path(start, goal, blocked):
    """Shortest way from start to goal around the blocked cells, as a list of points. None if there's none."""
    start_cell, goal_cell = cell_of(start), cell_of(goal)
    if start_cell in blocked:
        # you stand right by a wall / a door: your cell's MIDDLE is in a blocked zone, and from there the water
        # could leak to the OTHER side of a thin thing. Start from the free cell around you closest to YOU.
        around = [
            (start_cell[0] + dx, start_cell[1] + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        ]
        free = [cell for cell in around if cell not in blocked]
        if free:
            start_cell = min(free, key=lambda c: math.dist(middle(c), start))
    # cell -> the cell its water came from (the arrow)
    came_from = {start_cell: None}
    # flooded cells whose neighbours we haven't tried yet, oldest first
    wave = deque([start_cell])
    while wave and len(came_from) < MAX_CELLS:
        here = wave.popleft()
        if here == goal_cell:
            break
        for dx, dy in STEPS:
            nxt = (here[0] + dx, here[1] + dy)
            if nxt in came_from:
                continue
            if nxt in blocked and nxt != goal_cell:
                continue
            came_from[nxt] = here
            wave.append(nxt)

    if goal_cell not in came_from:
        return None
    # follow the arrows back: goal -> ... -> start, then turn the list around
    path = []
    cell = goal_cell
    while cell is not None:
        path.append(middle(cell))
        cell = came_from[cell]

    path.reverse()
    return path
