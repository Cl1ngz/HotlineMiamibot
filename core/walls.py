# https://github.com/Cl1ngz/HotlineMiamibot
# where the walls are
from .enemies import shelf_cards
from .memory import X_OFF, Y_OFF, read_double, read_kind

# obj_type or kinds to verify if broken
# values tat go uup its the value
TILE = 32
# the box of a thing (found with box_hunt): its FOLDER +0x78 left, +0x7C top, +0x80 right, +0x84 bottom
#   walls: real map numbers (a wall at 192,128 -> 192, 128, 199, 159: 8 thick, 32 long)
#   sofas, you: counted from the thing's x, y (a sofa -> -4, -8, 5, 7; you -> -8, -8, 7, 7)
BOX = 0x78
# nothing in a level is this big - a bigger box is junk (seen after dying on floor 2 + R)
MAX_BOX = 512
# a door that NEVER opens (floor 2): floor layer + this folder picture, a 4 x 32 plank
FLOOR = 0xFFFFFF9C
FAKE_DOOR = 0x20
# the wall layer (walls AND sofas) - the same on every floor so far
WALL = 0x9


def real_walls(mem, records, cards=None):
    """[(xy, box), ...] of every wall and sofa piece - from the whole SHELF, only the ones with a real box.
    Back on floor 1 at the end of a level the TABLE is full of junk wall cards (199 of 215 had no real box),
    while the real ones (115, the same as at the start) sit on the shelf."""
    if cards is None:
        cards = shelf_cards(mem, records)
    found = []
    for card in cards:
        try:
            if read_kind(mem, card, 0, 0x14) != WALL:
                continue
            xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
            found.append(
                (xy, read_box(mem, card, xy))
            )  # read_box raises OSError on a junk box
        except OSError:
            continue
    return found


def wall_boxes(mem, records, rules=None):
    """(left, top, right, bottom) of every wall and sofa. (rules isn't needed any more)"""
    return [box for xy, box in real_walls(mem, records)]


def find_walls(mem, records, rules=None):
    """(x, y) of every wall and sofa piece - for wall_lines (what you can see through) and the radar."""
    return [xy for xy, box in real_walls(mem, records)]


def signed(value):
    """A 4-byte number read as a whole number that can be below zero (0xFFFFFFFC -> -4)."""
    return value - (1 << 32) if value >= 1 << 31 else value


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
    """Boxes of the doors that never open - for the way they're walls."""
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
    # 1 <= : a (0, 0, 0, 0) box would become a 1x1 thing - that's junk too, not a wall
    if not (1 <= right - left <= MAX_BOX and 1 <= bottom - top <= MAX_BOX):
        raise OSError(
            "junk box"
        )  # real_walls and fake_door_boxes skip OSError, like junk memory
    return left, top, right + 1, bottom + 1


# visualisation
#               (x, y-32)
#                 above
# (x-32, y)    [ x, y ]    (x+32, y)
#   left                     right
#               (x, y+32)
#                 below
