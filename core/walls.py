# https://github.com/Cl1ngz/HotlineMiamibot
# where the walls are
import struct

from .enemies import shelf_cards
from .memory import X_OFF, Y_OFF, read_bytes, read_double, read_kind, read_u32

# wall pieces are 32 long, the next piece sits 32 further
TILE = 32
# a thing's box: 4 numbers in its FOLDER from +0x78 - left, top, right, bottom (found with box_hunt)
# walls keep real map numbers: a wall at 192,128 -> 192, 128, 199, 159
# sofas and you keep them counted from your own x, y: a sofa -> -4, -8, 5, 7
BOX = 0x78
MAX_BOX = (
    512  # nothing in a level is this big - a bigger box is junk (seen after dying + R)
)
WALL = 0x9  # card +0x14 for walls AND sofas, the same on every floor so far
# a door is a thin long plank (4 x 32 everywhere so far): thin 2-12, long 24-40
DOOR_THIN = (2, 12)
DOOR_LONG = (24, 40)
DOOR_NEAR = 12  # you bumped this close to a door's box = you pushed that door
# glass panes (folder +0x10): a box like a door's (a plank 32 long, 8 thick), but they never open - you can't walk
# through, you and the gunmen see and shoot through. helpers_for_me/door_kinds on level 4: 0x1b standing (|),
# 0x7e lying (-); the doors there are 0x20 and 0x67
WINDOWS = (0x1B, 0x7E)


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


def signed(value):
    """read_u32 can't give minus numbers: -4 comes out as 4294967292 (0xFFFFFFFC). This turns it back into -4.
    Sofas' and your boxes need it: they're counted from your middle (-4 = 4 to the left).
    """
    return value - (1 << 32) if value >= 1 << 31 else value


# visualisation
#               (x, y-32)
#                 above
# (x-32, y)    [ x, y ]    (x+32, y)
#   left                     right
#               (x, y+32)
#                 below


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
# which side of the line a-b c is on: + one side, - the other, 0 = on the line
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


def door_boxes(mem, cards):
    """Boxes of every door on the floor - a thin plank that isn't a wall piece or glass. Real doors AND fake
    ones: which one never opens, only pushing it tells (hmbot remembers those in doors.json, core/scenes.py).
    """
    return plank_boxes(mem, cards, glass=False)


def window_boxes(mem, cards):
    """Boxes of every glass pane on the floor (WINDOWS)."""
    return plank_boxes(mem, cards, glass=True)


def pane_lines(boxes):
    """A line along the middle of each glass pane, 1 longer at both ends (so two panes in a row overlap - a look
    through the point where they meet would go between them). For the gunmen: they don't see you through glass,
    you do (see.py keeps these out of eyes.lines)."""
    lines = []
    for left, top, right, bottom in boxes:
        if right - left >= bottom - top:  # lying (-)
            y = (top + bottom) / 2
            lines.append(((left - 1, y), (right + 1, y)))
        else:  # standing (|)
            x = (left + right) / 2
            lines.append(((x, top - 1), (x, bottom + 1)))
    return lines


def plank_boxes(mem, cards, glass):
    """Boxes of the cards that aren't wall pieces: the glass panes (glass=True) or the doors (False)."""
    boxes = set()
    for card in cards:
        try:
            if read_kind(mem, card, 0, 0x14) == WALL:
                continue
            xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
            box = read_box(mem, card, xy)
            window = read_kind(mem, card, 1, 0x10) in WINDOWS
        except OSError:
            continue
        # glass: every pane, whatever its shape. A door: a plank that isn't glass
        wanted = window if glass else not window and looks_like_door(box)
        if wanted:
            boxes.add(box)  # a set: the table and the shelf can both have the same door
    return sorted(boxes)


def looks_like_door(box):
    """A thin long plank (DOOR_THIN x DOOR_LONG) - what a door's box looks like."""
    thin, long = sorted((box[2] - box[0], box[3] - box[1]))
    return DOOR_THIN[0] <= thin <= DOOR_THIN[1] and DOOR_LONG[0] <= long <= DOOR_LONG[1]


def box_cards(mem, cards):
    """The cards that are walls (and sofas), doors or glass. The slow search: every card WIDE around the table
    (~2000) needs its box read, ~15 ms. Once a floor (see.py) - the rereads look only at these.
    """
    found = []
    for card in cards:
        try:
            wall = read_kind(mem, card, 0, 0x14) == WALL
            xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
            box = read_box(mem, card, xy)
            window = read_kind(mem, card, 1, 0x10) in WINDOWS
        except OSError:
            continue
        if wall or window or looks_like_door(box):
            found.append(card)
    return found


def read_box(mem, card, xy):
    """(left, top, right, bottom) of a card in map numbers. right and bottom are the EDGE (+1)."""
    x, y = xy
    # the 4 numbers in one read: "<4i" = four 4-byte numbers that can be minus (signed() does that for one).
    # It runs for every card WIDE around the table (~2000) - four read_kind's, each finding the folder
    # again, cost ~10 ms there
    data = read_bytes(mem, 16, read_u32(mem, card) + BOX)
    if len(data) < 16:
        raise OSError("can't read the box")
    left, top, right, bottom = struct.unpack("<4i", data)
    if abs(left) < abs(left - x):  # closer to 0 than to x -> counted from x, y
        left, right = left + x, right + x
        top, bottom = top + y, bottom + y
    # 1 <= : a (0, 0, 0, 0) box would become a 1x1 thing - that's junk too, not a wall
    if not (1 <= right - left <= MAX_BOX and 1 <= bottom - top <= MAX_BOX):
        raise OSError(
            "junk box"
        )  # real_walls and door_boxes skip OSError, like junk memory
    return left, top, right + 1, bottom + 1


def crosses_box(a, b, box):
    """Does the straight line from a to b go through the box (left, top, right, bottom)?
    (the "slab" test: where the line enters and leaves the box's x range, the same for y - do they overlap?)
    """
    t_in, t_out = (
        0.0,
        1.0,
    )  # the part of the line inside the box so far: 0 = at a, 1 = at b
    for start, step, low, high in (
        (a[0], b[0] - a[0], box[0], box[2]),
        (a[1], b[1] - a[1], box[1], box[3]),
    ):
        if step == 0:
            if not low <= start <= high:
                return False  # parallel to this side and outside it
            continue
        enter, leave = sorted(((low - start) / step, (high - start) / step))
        t_in, t_out = max(t_in, enter), min(t_out, leave)
        if t_in > t_out:
            return False
    return True


def door_at(you, doors):
    """The door you stand at (its box), or None: you're within DOOR_NEAR of its box."""
    for left, top, right, bottom in doors:
        if (
            left - DOOR_NEAR < you[0] < right + DOOR_NEAR
            and top - DOOR_NEAR < you[1] < bottom + DOOR_NEAR
        ):
            return (left, top, right, bottom)
    return None
