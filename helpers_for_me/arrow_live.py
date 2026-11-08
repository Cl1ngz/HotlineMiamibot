# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/arrow_live.py - does the bot see the red arrow RIGHT NOW? (the same arrows() the bot uses)
#
# It uses core/arrow.py's arrows() - so what it says is exactly what the bot sees. Every time the arrow moves
# you get a line: where it is, which way it points, what it points at. When it sees NO arrow, the status line
# says at which step the search stops - that tells what's different about an arrow the bot can't see:
#   u-left    corners with an arrow's left u (any pair in core/arrow.py PAIRS) in the known blocks
#   4 corners ...of them followed by left, right, right - the arrow's 4 corners in a row
#   squares   ...of them a real 16x16 square (turned any way) = arrows
#   live      ...of them bobbing (an old arrow in the list never moves)
# 0 blocks / u-left 0 while you SEE an arrow -> a different little picture (other u): run helpers_for_me/arrow_bob
# there. 4 corners > 0 but squares 0 -> its corners are laid out differently: send me the printout.
#
#   python -m helpers_for_me.arrow_live      Ctrl+C = end
import math
import struct
import time

import numpy as np

from core.arrow import BELOW, BLOCK, BOB, CORNER, PAIRS, arrows, read_words
from core.enemies import find_me_card
from core.memory import X_OFF, attach
from core.shelf import Shelf

CHUNK = 16 << 20  # the full search reads 16 MB at a time
FULL_EVERY = 5.0  # no live arrow -> search the whole memory again, at most this often
GAP = 0.12  # two looks this far apart: a live arrow moves (it bobs)
MOVED = 10  # a new line when the arrow moves more than this
GONE_AFTER = 0.6  # no live arrow for this long = "gone"


def corner_rows(words):
    """Where an arrow's 4 corners lie in a row (left, left, right, right u's of any known pair) - turned or not,
    a square or not. -> (how many left u's, the rows)"""
    u_left, rows = 0, []
    for left, right in PAIRS:
        hits = np.nonzero(words == left)[0]
        hits = hits[(hits >= 3) & (hits + 3 * CORNER + 2 < len(words))]
        pattern = (
            (words[hits + CORNER] == left) & (words[hits + 2 * CORNER] == right) & (words[hits + 3 * CORNER] == right)
        )
        u_left += len(hits)
        rows += hits[pattern].tolist()
    return u_left, rows


def full_search():
    """The 1 MB blocks that hold the arrow's 4 corners in a row - even if they aren't a proper square
    (so the status line can show where the search stops)."""
    blocks = set()
    for start, end in regions:
        for at in range(start, end, CHUNK):
            words = read_words(mem, at, min(CHUNK, end - at))
            for h in corner_rows(words)[1]:
                address = at + (h - 3) * 4
                blocks.add(address - address % BLOCK)
    return blocks


def steps(blocks):
    """How far the search gets in the known blocks: (u-left, 4 corners, squares)."""
    u_left = corners = squares = 0
    for block in blocks:
        words = read_words(mem, block, BLOCK + 256)
        hits, rows = corner_rows(words)
        u_left += hits
        corners += len(rows)
        squares += len(arrows(words, block))
    return u_left, corners, squares


def look(blocks):
    """{address: (x, y, tip_x, tip_y)} of every arrow in the known blocks right now."""
    found = {}
    for block in blocks:
        for address, x, y, tx, ty in arrows(read_words(mem, block, BLOCK + 256), block):
            found[address] = (x, y, tx, ty)
    return found


def you():
    shelf = Shelf(mem)
    me = find_me_card(shelf) if shelf.records else None
    if me is None:
        return None
    return struct.unpack("<2d", shelf.read(16, me + X_OFF))


def direction(tx, ty):
    """Which way the tip points, in words."""
    names = {(0, 1): "down", (0, -1): "up", (1, 0): "right", (-1, 0): "left"}
    return names.get((round(tx), round(ty)), f"({tx:+.2f},{ty:+.2f})")


mem, regions, static_regions = attach()
print(f"{len(regions)} memory regions, {sum(e - s for s, e in regions) / 1e6:.0f} MB - looking for the arrow...")
start = time.monotonic()
blocks, next_full = set(), 0.0
shown, last_live = None, -math.inf
try:
    while True:
        now = time.monotonic()
        first = look(blocks)
        time.sleep(GAP)
        second = look(blocks)
        # live = not the very same as in the first look, and an arrow from the first look was a little away (bob)
        live = [
            arrow
            for address, arrow in second.items()
            if first.get(address) != arrow
            and any(0 < math.dist(arrow[:2], other[:2]) <= BOB for other in first.values())
        ]
        if live:
            last_live = now
            x, y, tx, ty = live[0]
            if shown is None or math.dist(shown, (x, y)) > MOVED:
                print(
                    f"\nt={now - start:7.1f}s  ARROW at ({x:4.0f},{y:4.0f}) pointing {direction(tx, ty)}"
                    f" -> at ~({x + tx * BELOW:4.0f},{y + ty * BELOW:4.0f})   ({len(live)} live, {len(second)} in all)"
                )
                shown = (x, y)
        elif shown is not None and now - last_live > GONE_AFTER:
            print(f"\nt={now - start:7.1f}s  the arrow is GONE")
            shown = None
        if not live and now >= next_full:
            blocks |= full_search()  # new lists after a new scene? (a few seconds)
            next_full = time.monotonic() + FULL_EVERY
        me = you()
        where = f"you ({me[0]:4.0f},{me[1]:4.0f})" if me else "you ?        "
        if live:
            state = f"arrow ({shown[0]:4.0f},{shown[1]:4.0f})"
        else:
            u_left, corners, squares = steps(blocks)
            state = f"NO arrow: {len(blocks)} blocks  u-left {u_left}  4 corners {corners}  squares {squares}  live 0"
        print(f"   t={now - start:7.1f}s  {where}  {state}      ", end="\r", flush=True)
except KeyboardInterrupt:
    print()
