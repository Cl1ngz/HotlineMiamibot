# https://github.com/Cl1ngz/HotlineMiamibot
# core/arrow.py - the red arrow: where it is and what it points at (helpers_for_me/arrow_bob + arrow_live)
#
# The game doesn't keep "the arrow points at X" anywhere - it just DRAWS the arrow every frame. To draw, it writes
# a list of corners for the graphics card, 36 bytes = 9 floats per corner:
#     x, y, z, u, v, r, g, b, a          (y is stored NEGATIVE: -113 means 113 down)
# u, v = where the little picture sits in the big picture sheet. The arrow is always the same 16x16 picture,
# but in different scenes it sits in a different place of the sheet - so PAIRS lists every place we found it in.
# An arrow = 4 corners in a row with the u's left, left, right, right - a 16x16 square, turned any way
# (over the TV it points down, at the dumpster up). The thing it points at is BELOW px further along its tip.
# The lists can still hold OLD arrows from earlier frames - a live arrow bobs, an old one never moves.
import math
import os

import numpy as np

# the arrow's u's (left side, right side) as 4-byte numbers - one pair for every place in the picture sheet
# we found it in (helpers_for_me/arrow_bob)
PAIRS = [
    (
        0x3DD80000,
        0x3DE80000,
    ),  # 0.10546875 / 0.11328125 - the apartment (the TV, the round thing)
    (
        0x3CB00000,
        0x3CF00000,
    ),  # 0.021484375 / 0.029296875 - the metro, outside (the dumpster)
]
CORNER = 9  # floats per corner
SIZE = 16  # the arrow is 16x16
BELOW = 27  # what it points at is this far from its middle, along the tip
BOB = 10  # a live arrow moves at most this much between two looks (any direction)
BLOCK = 1 << 20  # once found, the 1 MB block around it is watched
CHUNK = (
    4 << 20
)  # the search through the whole memory: this much per frame (it never stops the bot for long)
LOOK_EVERY = (
    0.1  # seconds between two looks at the known blocks (the bob needs a moment)
)
GONE_AFTER = 0.6  # no live arrow for this long = there's no arrow


def read_words(mem, at, size):
    """size bytes of the game's memory at `at`, as 4-byte numbers (empty if they can't be read)."""
    try:
        data = os.pread(mem, size, at)
    except OSError:
        return np.zeros(0, dtype="<u4")
    return np.frombuffer(data[: len(data) // 4 * 4], dtype="<u4")


def arrows(words, base):
    """Every arrow in these 4-byte numbers (they start at address `base`).
    -> [(address, x, y of its middle, tip_x, tip_y)]   tip = which way it points (a step of length 1)
    The arrow can be turned (over the TV it points down, at the dumpster up): so no "left side = smaller x" -
    just 4 corners that make a 16x16 square, in any direction."""
    floats = words.view("<f4")  # the same bytes, read as floats
    found = []
    for left, right in PAIRS:
        hits = np.nonzero(words == left)[0]  # every u of a left corner
        hits = hits[
            (hits >= 3) & (hits + 3 * CORNER + 2 < len(words))
        ]  # (room for the whole arrow around it)
        # the next corners: left again, then right, right
        pattern = (
            (words[hits + CORNER] == left)
            & (words[hits + 2 * CORNER] == right)
            & (words[hits + 3 * CORNER] == right)
        )
        for h in hits[pattern].tolist():
            # a corner = x, y, z, u, v... and it starts 3 floats before its u. y is stored NEGATIVE -> turn it around
            corners = []
            for k in range(4):
                at = h - 3 + k * CORNER
                corners.append(
                    (float(floats[at]), -float(floats[at + 1]), float(floats[at + 4]))
                )
            if not all(math.isfinite(n) for corner in corners for n in corner):
                continue
            (x0, y0, v0), (x1, y1, v1), (x2, y2, v2), (x3, y3, v3) = corners
            # a real 16x16 square: every side SIZE long (left 0-1, top/bottom 0-2 and 1-3, right 2-3)
            sides = (
                math.dist((x0, y0), (x1, y1)),
                math.dist((x0, y0), (x2, y2)),
                math.dist((x1, y1), (x3, y3)),
                math.dist((x2, y2), (x3, y3)),
            )
            if not all(abs(side - SIZE) < 1 for side in sides):
                continue
            # the middle = halfway between all 4 corners
            x, y = (x0 + x1 + x2 + x3) / 4, (y0 + y1 + y2 + y3) / 4
            # the tip = the edge with the smaller v (over the TV: v 0.449 at the bottom, 0.457 at the top)
            low = min(v0, v1)
            tip = [(cx, cy) for cx, cy, v in corners if v == low]
            tx = sum(cx for cx, cy in tip) / len(tip) - x
            ty = sum(cy for cx, cy in tip) / len(tip) - y
            length = math.hypot(tx, ty)
            if length == 0:
                continue
            found.append((base + (h - 3) * 4, x, y, tx / length, ty / length))
    return found


class ArrowWatch:
    """Finds the red arrow and follows it - a little work every frame, so it never stops the bot for long.
    watch = ArrowWatch(mem, regions) once, then watch.update(now) every frame."""

    def __init__(self, mem, regions):
        self.mem = mem
        # the whole memory in CHUNK pieces - the search goes through them one per frame
        self.pieces = [
            (at, min(CHUNK, end - at))
            for start, end in regions
            for at in range(start, end, CHUNK)
        ]
        self.next_piece = 0
        self.blocks = set()  # the 1 MB blocks where an arrow was ever found
        self.last = {}  # {address: (x, y, tip_x, tip_y)} of the arrows in the last look
        self.last_at = -math.inf  # when that look was
        self.seen_live = -math.inf  # when a live arrow was seen last
        self.xy = None  # the live arrow's middle
        self.tip = (
            0,
            1,
        )  # which way the live arrow points (a step of length 1; (0, 1) = down)

    def search_all(self):
        """The whole memory at once (~0.5 s). Once at the start: the bot must know where the lists are
        BEFORE it walks anywhere - a piece per frame needs over a second to get through it all.
        """
        for at, size in self.pieces:
            for address, *_ in arrows(read_words(self.mem, at, size), at):
                self.blocks.add(address - address % BLOCK)

    def update(self, now):
        """(x, y) of what the arrow points at, or None (no arrow)."""
        if now - self.last_at >= LOOK_EVERY:
            found = {}
            for block in self.blocks:
                for address, x, y, tx, ty in arrows(
                    read_words(self.mem, block, BLOCK + 256), block
                ):
                    found[address] = (x, y, tx, ty)
            for address, (x, y, tx, ty) in found.items():
                # live = not exactly the same as in the last look, AND in the last look there was an arrow a
                # LITTLE away from this one (it bobbed - a turned arrow bobs sideways, so: the distance)
                if self.last.get(address) != (x, y, tx, ty) and any(
                    0 < math.dist((x, y), (lx, ly)) <= BOB
                    for lx, ly, _, _ in self.last.values()
                ):
                    self.xy = (x, y)
                    self.tip = (tx, ty)
                    self.seen_live = now
            self.last, self.last_at = found, now
        if now - self.seen_live > GONE_AFTER:
            self.xy = None
            # no live arrow in the known blocks: search one more piece of the whole memory for new ones
            at, size = self.pieces[self.next_piece]
            for address, *_ in arrows(read_words(self.mem, at, size), at):
                self.blocks.add(address - address % BLOCK)
            self.next_piece = (self.next_piece + 1) % len(self.pieces)
        if self.xy is None:
            return None
        # what it points at: BELOW further along the tip
        return self.xy[0] + self.tip[0] * BELOW, self.xy[1] + self.tip[1] * BELOW
