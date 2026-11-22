# https://github.com/Cl1ngz/HotlineMiamibot
# core/arrow.py - the red arrow: the game only draws it, so we look for its 4 corners in the drawing lists
# old arrows stay in memory and never move, the live one bobs - update() gives what the live one points at
import math
import os

import numpy as np

# u = where the arrow's picture sits in the big picture sheet (a float kept as a 4-byte number).
# It's in a different place in different scenes - one (left u, right u) pair per place found (helpers_for_me/arrow_bob)
PAIRS = [
    (0x3DD80000, 0x3DE80000),  # the apartment (the TV, the round thing)
    (0x3CB00000, 0x3CF00000),  # the metro, outside (the dumpster)
]
# one corner in a drawing list: 9 floats - x, y, z, u, v, r, g, b, a (y is stored minus: -113 = 113 down)
CORNER = 9
SIZE = 16  # the arrow is a 16x16 square
BELOW = 27  # the thing it points at is this far from its middle, toward the tip
BOB = 10  # a live arrow moves at most this much between two looks
BLOCK = 1 << 20  # found an arrow -> watch the 1 MB around it
CHUNK = 4 << 20  # searching all memory: 4 MB a frame, so the bot never stops for long
LOOK_EVERY = 0.1  # seconds between looks at the known blocks (the bob needs a moment)
GONE_AFTER = 0.6  # no live arrow this long = no arrow


def read_words(mem, at, size):
    """size bytes of the game's memory at `at`, as 4-byte numbers (empty if they can't be read)."""
    try:
        data = os.pread(mem, size, at)
    except OSError:
        return np.zeros(0, dtype="<u4")
    return np.frombuffer(data[: len(data) // 4 * 4], dtype="<u4")


def arrows(words, base):
    """Every arrow in these words (they start at address `base`) -> [(address, x, y, tip_x, tip_y)]
    x, y = its middle, tip = which way it points (length 1). Turned any way: over the TV down, at the dumpster up."""
    floats = words.view("<f4")  # the same bytes as floats
    found = []
    for left, right in PAIRS:
        # every left u, with room for the whole arrow around it
        hits = np.nonzero(words == left)[0]
        hits = hits[(hits >= 3) & (hits + 3 * CORNER + 2 < len(words))]
        # the next 3 corners must be: left, right, right
        pattern = (
            (words[hits + CORNER] == left)
            & (words[hits + 2 * CORNER] == right)
            & (words[hits + 3 * CORNER] == right)
        )
        for h in hits[pattern].tolist():
            # a corner starts 3 floats before its u; y is stored minus -> flip it
            corners = []
            for k in range(4):
                at = h - 3 + k * CORNER
                corners.append(
                    (float(floats[at]), -float(floats[at + 1]), float(floats[at + 4]))
                )
            if not all(math.isfinite(n) for corner in corners for n in corner):
                continue
            (x0, y0, v0), (x1, y1, v1), (x2, y2, v2), (x3, y3, v3) = corners
            # a real 16x16 square: all 4 sides 16 long
            sides = (
                math.dist((x0, y0), (x1, y1)),
                math.dist((x0, y0), (x2, y2)),
                math.dist((x1, y1), (x3, y3)),
                math.dist((x2, y2), (x3, y3)),
            )
            if not all(abs(side - SIZE) < 1 for side in sides):
                continue
            # the middle = the average of the 4 corners
            x, y = (x0 + x1 + x2 + x3) / 4, (y0 + y1 + y2 + y3) / 4
            # the tip = the side with the smaller v (over the TV: 0.449 at the bottom, so it points down)
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
    """Finds the red arrow and follows it, a little work every frame.
    watch = ArrowWatch(mem, regions) once, then watch.update(now) every frame."""

    def __init__(self, mem, regions):
        self.mem = mem
        # all memory cut into CHUNK pieces - one is searched per frame
        self.pieces = [
            (at, min(CHUNK, end - at))
            for start, end in regions
            for at in range(start, end, CHUNK)
        ]
        self.next_piece = 0
        self.blocks = set()  # the 1 MB blocks where an arrow was ever found
        self.last = {}  # {address: (x, y, tip_x, tip_y)} from the last look
        self.last_at = -math.inf  # when that look was
        self.seen_live = -math.inf  # when a live arrow was seen last
        self.xy = None  # the live arrow's middle
        self.tip = (0, 1)  # which way it points, (0, 1) = down

    def search_all(self):
        """All memory at once (~0.5 s), at the start: the bot has to know where the lists are before it walks -
        a piece per frame takes over a second to go through it all."""
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
                # live = changed since the last look, and the last look had an arrow a little away from it
                # (it bobbed; a turned arrow bobs sideways, so: the distance)
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
            # no live arrow in the known blocks: search the next piece of memory for new ones
            at, size = self.pieces[self.next_piece]
            for address, *_ in arrows(read_words(self.mem, at, size), at):
                self.blocks.add(address - address % BLOCK)
            self.next_piece = (self.next_piece + 1) % len(self.pieces)
        if self.xy is None:
            return None
        # what it points at: BELOW further along the tip
        return self.xy[0] + self.tip[0] * BELOW, self.xy[1] + self.tip[1] * BELOW
