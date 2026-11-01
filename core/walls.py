# https://github.com/Cl1ngz/HotlineMiamibot
# where the walls are
from collections import defaultdict

from .memory import read_kind

# obj_type or kinds to verify if broken
# values tat go uup its the value
TILE = 32
# the box of a thing (found with box_hunt): its FOLDER +0x78 left, +0x7C top, +0x80 right, +0x84 bottom
#   walls: real map numbers (a wall at 192,128 -> 192, 128, 199, 159: 8 thick, 32 long)
#   sofas, you: counted from the thing's x, y (a sofa -> -4, -8, 5, 7; you -> -8, -8, 7, 7)
BOX = 0x78
# a door: a card on the floor layer with this folder picture. Its x, y is the HINGE (the end it turns around)
FLOOR = 0xFFFFFF9C
FAKE_DOOR = 0x20


# basicly biggest kind is the wall hope its works
def find_walls(mem, records, rules):
    where, offset, _ = rules[0]
    kinds = defaultdict(list)
    for record, xy in records.items():
        try:
            kinds[read_kind(mem, record, where, offset)].append(xy)
        except OSError:
            pass
    return max(kinds.values(), key=len) if kinds else []


def signed(value):
    """A 4-byte number read as a whole number that can be below zero (0xFFFFFFFC -> -4)."""
    return value - (1 << 32) if value >= 1 << 31 else value


def wall_boxes(mem, records, rules):
    """(left, top, right, bottom) of everything in the wall layer - walls AND sofas.
    right and bottom are the EDGE: a wall on pixels 192..199 gets right = 200 (the +1 from the corners lesson).
    """
    where, offset, _ = rules[0]
    kinds = defaultdict(list)
    for record in records:
        try:
            kinds[read_kind(mem, record, where, offset)].append(record)
        except OSError:
            pass
    if not kinds:
        return []
    boxes = []
    # the wall layer: the biggest kind, like find_walls
    for card in max(kinds.values(), key=len):
        try:
            boxes.append(read_box(mem, card, records[card]))
        except OSError:
            continue
    return boxes


def wall_lines(walls):
    pieces = set(walls)
    lines = []
    for x, y in pieces:
        # is there  wall piece next door  the left or right
        across = (x + TILE, y) in pieces or (x - TILE, y) in pieces
        # or above or below
        down = (x, y + TILE) in pieces or (x, y - TILE) in pieces
        #  piece with no neighbours gets both lines (a pillar)
        if across or not down:
            lines.append(((x, y), (x + TILE, y)))
        if down or not across:
            lines.append(((x, y), (x, y + TILE)))
    return lines


# x * cy - y * cx
# positive = left, negative = right, 0 = on it
def side(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


# does p1-p2 does jesus with q1-q2
def crosses(p1, p2, q1, q2):
    return (
        side(q1, q2, p1) * side(q1, q2, p2) < 0
        and side(p1, p2, q1) * side(p1, p2, q2) < 0
    )


# if no wall the u see
def can_see(a, b, lines):
    return not any(crosses(a, b, q1, q2) for q1, q2 in lines)


def fake_door_boxes(mem, records):
    """(x, y) of every door's hinge. Pushing a door right at its hinge doesn't turn it - you get stuck."""
    boxes = []
    for card, xy in records.items():
        try:
            if (
                read_kind(mem, card, 0, 0x14) == FLOOR
                and read_kind(mem, card, 1, 0x10) == FAKE_DOOR
            ):
                boxes.append(read_box(mem, card, xy))
        except OSError:
            continue
    return boxes


def read_box(mem, card, xy):
    """(left, top, right, bottom) of a card in map numbers. right and bottom are the EDGE (+1)."""
    x, y = xy
    left, top, right, bottom = (
        signed(read_kind(mem, card, 1, BOX + 4 * i)) for i in range(4)
    )
    if abs(left) < abs(left - x):  # closer to 0 than to x -> counted from x, y
        left, right = left + x, right + x
        top, bottom = top + y, bottom + y
    return left, top, right + 1, bottom + 1


# visualisation
#               (x, y-32)
#                 above
# (x-32, y)    [ x, y ]    (x+32, y)
#   left                     right
#               (x, y+32)
#                 below
