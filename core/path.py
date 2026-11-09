# https://github.com/Cl1ngz/HotlineMiamibot
# core/path.py - find a way around the walls: A* on a grid of cells (a library)
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
#   find_path(start, goal, blocked)   ->  [(x, y), ...] points to walk through, start to goal
#                                         (no way to the goal -> the way to the cell closest to it)
import heapq
import math

# size of one cell in game units (a wall piece is 32)
CELL = 16
# the cells are shifted by half a cell: their middles sit at 0, 16, 32, 48... A doorway in a wall of 32-pieces
# is e.g. 416-448 - its middle 432 is now a cell's middle (before: the line BETWEEN two cells), so the way goes
# through the MIDDLE of a door. At its edge you push next to the hinge, and the door doesn't swing open
SHIFT = CELL / 2
# stop after trying this many cells - the goal is unreachable (or the floor is huge)
MAX_CELLS = 5000
# right, left, down, up
STEPS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
# you are 16 x 16 (box_hunt: -8..7), so your middle must stay this far from every box
HALF = 8


def cell_of(xy):
    """Which cell the point (x, y) is in."""
    return (int((xy[0] + SHIFT) // CELL), int((xy[1] + SHIFT) // CELL))


def middle(cell):
    """The point in the middle of a cell."""
    return (cell[0] * CELL, cell[1] * CELL)


def blocked_cells(boxes):
    """Every cell your MIDDLE can't stand in: its middle is inside a box made HALF bigger on every side.
    Then you can be treated as a point - the boxes already got your size."""
    blocked = set()
    for left, top, right, bottom in boxes:
        left -= HALF
        top -= HALF
        right += HALF
        bottom += HALF
        for cx in range(int((left + SHIFT) // CELL), int((right + SHIFT) // CELL) + 1):
            for cy in range(
                int((top + SHIFT) // CELL), int((bottom + SHIFT) // CELL) + 1
            ):
                mx, my = middle((cx, cy))
                if left < mx < right and top < my < bottom:
                    blocked.add((cx, cy))

    return blocked


def guess(cell, goal_cell):
    """How many steps from cell to the goal if there were no walls at all (never more than the real way)."""
    return abs(cell[0] - goal_cell[0]) + abs(cell[1] - goal_cell[1])


def find_path(start, goal, blocked):
    """Shortest way from start to goal around the blocked cells, as a list of points.
    A* ("A star"): like the water, but the cells that look closest to the goal are tried first - so on a big
    open floor (the metro, outside) it goes almost straight there instead of flooding everything around.
    Never None: when the goal can't be reached (inside a box, walled in, too far) it's the way to the
    cell closest to the goal - walk there and you're as close as it gets.
    """
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
    came_from = {start_cell: None}  # cell -> the cell we came from (the arrow back)
    steps_to = {
        start_cell: 0
    }  # cell -> steps from the start, the shortest way found so far
    # cells to try: (steps so far + the guess to the goal, steps so far, cell) - heapq gives the smallest first
    todo = [(guess(start_cell, goal_cell), 0, start_cell)]
    # the cell closest to the goal reached so far: if the goal can't be reached, the way goes there instead
    best = start_cell
    tried = 0
    while todo and tried < MAX_CELLS:
        _, steps, here = heapq.heappop(todo)
        if here == goal_cell:
            break
        if steps > steps_to[here]:
            continue  # an old, longer way to this cell - a shorter one was tried already
        tried += 1
        if guess(here, goal_cell) < guess(best, goal_cell):
            best = here  # the closest to the goal so far
        for dx, dy in STEPS:
            nxt = (here[0] + dx, here[1] + dy)
            if nxt in blocked and nxt != goal_cell:
                continue
            if nxt in steps_to and steps_to[nxt] <= steps + 1:
                continue  # we know a way there that's as short already
            steps_to[nxt] = steps + 1
            came_from[nxt] = here
            heapq.heappush(todo, (steps + 1 + guess(nxt, goal_cell), steps + 1, nxt))

    # the goal reached -> the way to it; not reached (inside a box, walled in, too far) -> to the closest cell
    end = goal_cell if goal_cell in came_from else best
    # follow the arrows back: end -> ... -> start, then turn the list around
    path = []
    cell = end
    while cell is not None:
        path.append(middle(cell))
        cell = came_from[cell]

    path.reverse()
    return path
