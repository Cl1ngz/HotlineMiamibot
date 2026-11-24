# https://github.com/Cl1ngz/HotlineMiamibot
# core/path.py - the way around walls: the floor cut into 16x16 cells, A* walks through the free ones
# blocked_cells(boxes) -> cells you can't stand in, find_path(start, goal, blocked) -> points to walk through
import heapq
import math

CELL = 16  # one cell is 16x16, half a wall piece
# cells moved by half a cell, so a doorway's middle is a cell's middle and the way goes through the middle
# of the door - at its edge you push by the hinge and the door doesn't open
SHIFT = CELL / 2
MAX_CELLS = 5000  # tried this many cells and still no goal = give up (can't get there, or a huge floor)
STEPS = [(1, 0), (-1, 0), (0, 1), (0, -1)]  # right, left, down, up
HALF = 8  # you're 16x16, so your middle stays 8 away from every box


def cell_of(xy):
    """Which cell the point (x, y) is in."""
    return (int((xy[0] + SHIFT) // CELL), int((xy[1] + SHIFT) // CELL))


def middle(cell):
    """The point in the middle of a cell."""
    return (cell[0] * CELL, cell[1] * CELL)


def blocked_cells(boxes):
    """Cells your middle can't stand in. Every box gets HALF bigger on each side,
    so the bot can be one point - the box already counts your body."""
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
    """Steps to the goal if there were no walls - never more than the real way."""
    return abs(cell[0] - goal_cell[0]) + abs(cell[1] - goal_cell[1])


def find_path(start, goal, blocked, max_cells=MAX_CELLS):
    """The shortest way from start to goal around blocked cells, as points to walk through.
    A*: the cells that look closest to the goal go first, so on open floor it goes almost straight there.
    Never None: can't get to the goal -> the way to the cell closest to it."""
    start_cell, goal_cell = cell_of(start), cell_of(goal)
    if start_cell in blocked:
        # you stand right by a wall or a door: starting in a blocked cell the way could go through
        # to the other side of a thin thing - start from the free cell next to you that's closest to you
        around = [
            (start_cell[0] + dx, start_cell[1] + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        ]
        free = [cell for cell in around if cell not in blocked]
        if free:
            start_cell = min(free, key=lambda c: math.dist(middle(c), start))
    came_from = {start_cell: None}  # cell -> the cell we came from
    steps_to = {start_cell: 0}  # cell -> fewest steps from the start so far
    # cells to try as (steps + guess, steps, cell) - heapq gives the smallest first
    todo = [(guess(start_cell, goal_cell), 0, start_cell)]
    best = start_cell  # closest cell to the goal so far - the way goes there if the goal can't be reached
    tried = 0
    while todo and tried < max_cells:
        _, steps, here = heapq.heappop(todo)
        if here == goal_cell:
            break
        if steps > steps_to[here]:
            continue  # an old longer way here, a shorter one was tried already
        tried += 1
        if guess(here, goal_cell) < guess(best, goal_cell):
            best = here  # the closest to the goal so far
        for dx, dy in STEPS:
            nxt = (here[0] + dx, here[1] + dy)
            # the goal can be in a blocked cell (a weapon by a wall) - go there anyway
            if nxt in blocked and nxt != goal_cell:
                continue
            if nxt in steps_to and steps_to[nxt] <= steps + 1:
                continue  # we know a way there that's as short already
            steps_to[nxt] = steps + 1
            came_from[nxt] = here
            heapq.heappush(todo, (steps + 1 + guess(nxt, goal_cell), steps + 1, nxt))

    # goal reached -> the way to it, else -> the way to the closest cell
    end = goal_cell if goal_cell in came_from else best
    # follow the arrows back from the end, then turn the list around:
    #   way:        S (you) -> A -> B -> G (goal)
    #   came_from:  A: S   B: A   G: B   S: None
    #   the loop:   G -> B -> A -> S -> None (stop)   path = [G, B, A, S]   goal to you
    #   reverse():  path = [S, A, B, G]   you to goal
    path = []
    cell = end
    while cell is not None:
        path.append(middle(cell))
        cell = came_from[cell]

    path.reverse()
    return path


def walk_steps(start, xy, blocked, most):
    """Steps (CELL each) to walk to xy, or None: more than `most`, no way there, or the way comes at xy from
    the wrong side of a wall (its last free cell is more than a cell away - xy's own cell can sit in a wall)."""
    way = find_path(start, xy, blocked, 20 * most)
    if cell_of(way[-1]) != cell_of(xy) or len(way) - 1 > most:
        return None
    free = [point for point in way if cell_of(point) not in blocked]
    if not free or math.dist(free[-1], xy) > CELL:
        return None
    return len(way) - 1
