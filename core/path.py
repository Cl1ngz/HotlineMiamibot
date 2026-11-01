# https://github.com/Cl1ngz/HotlineMiamibot
# core/path.py - find a way around the walls: the "wave" (BFS) on a grid of cells (a library)
#
# The floor is cut into square cells, CELL x CELL. From your cell the "water" spreads to the cells next to it,
# then to theirs... but never through a wall line (can_see). Every cell remembers where its water came from,
# so when the water reaches the goal we follow those "came from" arrows back to you.
#
#   find_path(start, goal, lines)  ->  [(x, y), ...] points to walk through, start to goal  (None = no way)
from collections import defaultdict, deque

from .walls import can_see

# size of one cell in game units (a wall piece is 32)
CELL = 16
# stop flooding after this many cells - the goal is unreachable or very far
MAX_CELLS = 5000
# right, left, down, up
STEPS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
# size of one chunk for the wall lines(1x wall pice)
CHUNK = 32


def chunks(lines):
    """Sort the wall lines into chuns by their middle point: {(chunk x, chunk y): [lines]}."""
    found = defaultdict(list)
    for line in lines:
        (x1, y1), (x2, y2) = line
        # the middle of the line
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        found[(int(mx // CHUNK), int(my // CHUNK))].append(line)

    return found


def lines_near(found, point):
    """The wall lines from the chunks of point and the 8 chunks around it."""
    bx, by = int(point[0] // CHUNK), int(point[1] // CHUNK)  # the chunk of point
    near = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            near.extend(found.get((bx + dx, by + dy), []))
    return near


def cell_of(xy):
    """Which cell the point (x, y) is in."""
    return (int(xy[0] // CELL), int(xy[1] // CELL))


def middle(cell):
    """The point in the middle of a cell."""
    return (cell[0] * CELL + CELL / 2, cell[1] * CELL + CELL / 2)


def find_path(start, goal, lines):
    """Shortest way from start to goal around the walls, as a list of points. None if there's none."""
    found = chunks(lines)
    start_cell, goal_cell = cell_of(start), cell_of(goal)
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
            if not can_see(middle(here), middle(nxt), lines_near(found, middle(here))):
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
