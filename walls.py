# https://github.com/Cl1ngz/HotlineMiamibot
# where the walls are
from collections import defaultdict

from memory import read_kind

# obj_type or kinds to verify if broken
# values tat go uup its the value
TILE = 32


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


# visualisation
#               (x, y-32)
#                 above
# (x-32, y)    [ x, y ]    (x+32, y)
#   left                     right
#               (x, y+32)
#                 below
