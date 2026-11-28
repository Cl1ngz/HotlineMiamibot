# https://github.com/Cl1ngz/HotlineMiamibot
# core/danger.py - the danger map: the cells a gunman can see (he shoots you there), and where to hide
# line_rows(lines) -> the wall lines for numpy, seen_cells(xy, rows, blocked) -> {cells he sees},
# cover(you, fire, blocked) -> the closest cell nobody sees, corner(xy, fire, blocked) -> where to wait for him
import math
from collections import deque

import numpy as np

from .path import CELL, STEPS, cell_of, middle

# a gunman shoots you this far (the logs: deaths 35-200 away; lock-on sees 250 too)
SEES = 250
# cover further than this many steps (16 each) isn't worth it - close he shoots in ~0.3 s, and from far away
# running 10 steps back still beats running 200 at him (the logs: a bat at a shotgun 220 away, dead)
COVER_STEPS = 10
CORNER_STEPS = 400  # look this many cells around him for a corner (a room or two)


def line_rows(lines):
    """The wall lines [((x1, y1), (x2, y2)), ...] as a numpy table, one row (x1, y1, x2, y2) a line -
    seen_cells() tests all of them at once. Once per wall read (they never move)."""
    return np.array([(a[0], a[1], b[0], b[1]) for a, b in lines], dtype=float).reshape(
        -1, 4
    )


def seen_cells(xy, rows, blocked):
    """{cells} the man at xy sees: closer than SEES and no wall line between - can_see() for every cell around
    him at once. numpy fills a cells x lines table in one go (python loops: ~100x slower, a frame lost).
    """
    gx, gy = xy
    cx, cy = cell_of(xy)
    r = int(SEES // CELL) + 1
    cells = [
        (x, y)
        for x in range(cx - r, cx + r + 1)
        for y in range(cy - r, cy + r + 1)
        if (x, y) not in blocked and math.dist(middle((x, y)), xy) < SEES
    ]
    if not cells:
        return set()
    # only the lines close enough to cut a look (a line is 32-34 long, so one end is within SEES + 34)
    near = rows[np.hypot(rows[:, 0] - gx, rows[:, 1] - gy) < SEES + 40]
    if len(near) == 0:
        return set(cells)
    points = np.array([middle(cell) for cell in cells], dtype=float)
    px, py = (
        points[:, :1],
        points[:, 1:],
    )  # a column each (N x 1) - against a row of lines (L) = N x L
    x1, y1, x2, y2 = near.T
    # crosses() from core/walls.py, for every cell and line at once: the look him -> cell and the line
    # cross when him and the cell are on two sides of the line, and both ends of the line on two sides of the look
    him = (x2 - x1) * (gy - y1) - (y2 - y1) * (gx - x1)  # side of the line he's on (L)
    cell = (x2 - x1) * (py - y1) - (y2 - y1) * (
        px - x1
    )  # side of the line each cell is on (N x L)
    end1 = (px - gx) * (y1 - gy) - (py - gy) * (
        x1 - gx
    )  # side of the look each end is on (N x L)
    end2 = (px - gx) * (y2 - gy) - (py - gy) * (x2 - gx)
    cut = (him * cell < 0) & (end1 * end2 < 0)
    free = ~cut.any(axis=1)  # no line cuts the look at this cell
    return {c for c, ok in zip(cells, free) if ok}


def cover(you, fire, blocked):
    """The closest cell (by walking) no gunman sees, as a point - None: you're out of sight already,
    or no cover within COVER_STEPS. Breadth-first: ring after ring of cells around you.
    """
    start = cell_of(you)
    if start not in fire:
        return None
    seen = {start}
    todo = deque([(start, 0)])
    while todo:
        here, steps = todo.popleft()
        if here not in fire and here not in blocked:
            return middle(here)
        if steps == COVER_STEPS:
            continue
        for dx, dy in STEPS:
            nxt = (here[0] + dx, here[1] + dy)
            if nxt not in seen and nxt not in blocked:
                seen.add(nxt)
                todo.append((nxt, steps + 1))
    return None


def corner(xy, fire, blocked):
    """Where to wait for the gunman at xy: the closest cell (by walking from HIM) no gunman sees - round the
    corner of his room, by its door. None: they see everything within CORNER_STEPS cells of him.
    """
    start = cell_of(xy)
    seen = {start}
    todo = deque([start])
    while todo and len(seen) < CORNER_STEPS:
        here = todo.popleft()
        if here not in fire and here not in blocked:
            return middle(here)
        for dx, dy in STEPS:
            nxt = (here[0] + dx, here[1] + dy)
            # his own cell can be blocked (he stands by a wall) - the rest must be free floor
            if nxt not in seen and nxt not in blocked:
                seen.add(nxt)
                todo.append(nxt)
    return None
