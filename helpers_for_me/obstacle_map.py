# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/obstacle_map.py - what ELSE besides the walls is around you? (sofas, doors, tables...)
#
# core/path.py only knows the walls. This draws a map around you where every other thing gets a letter,
# one letter per kind (layer + picture), and also the way find_path finds to the crosshair:
#   @  you     +  the crosshair     #  wall     *  the way     .  floor
#   a b c ...  other things (the legend under the map says which layer/picture each letter is)
#   A B C ...  the SAME thing, but the way goes right over it  <- what the bot walks into
# One character = 8 game units (a wall piece is 32 = 4 characters).
#
#   python -m helpers_for_me.obstacle_map         things from the table, 160 around you
#   python -m helpers_for_me.obstacle_map 250     ...250 around you
#   python -m helpers_for_me.obstacle_map 160 all also cards that are NOT in the table (blood, bits - lots!)
#   python -m helpers_for_me.obstacle_map walls   ALSO the wall layer gets letters, one per picture
#                                                 (are sofas a different picture inside the wall layer?)
#   (the words can be mixed: obstacle_map 200 all walls)
import math
import sys
from collections import Counter, defaultdict

from core.enemies import RECORD, find_aim, find_me_card, load_rules
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records, wait
from core.path import blocked_cells, find_path
from core.walls import fake_door_boxes, wall_boxes, wall_lines

numbers = [float(word) for word in sys.argv[1:] if word.replace(".", "").isdigit()]
RANGE = numbers[0] if numbers else 160
ALL = "all" in sys.argv[1:]  # the whole shelf, not only the table
WALLS = "walls" in sys.argv[1:]  # letters for the wall layer too
CHAR = 8  # game units per character
LAYER = 0x14
AIM_LAYER = 0xAF
LETTERS = "abcdefghijklmnopqrstuvwxyz"

mem, regions, static_regions = attach()
rules = load_rules()
if not rules:
    raise SystemExit("no enemy rules yet")

find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("put the crosshair where the bot wanted to go (or anywhere), then hold the mouse still", 4)
me = find_me_card(mem)
goal = find_aim(mem)
if me is None:
    raise SystemExit("can't find you - are you in a level?")
you = (read_double(mem, me + X_OFF), read_double(mem, me + Y_OFF))
records = table_records(mem)

# the walls: the layer most table cards have (like core.walls.find_walls)
layers = {}
for card in records:
    try:
        layers[card] = read_kind(mem, card, 0, LAYER)
    except OSError:
        continue
wall_layer = Counter(layers.values()).most_common(1)[0][0]
lines = wall_lines([records[card] for card, layer in layers.items() if layer == wall_layer])
blocked = blocked_cells(wall_boxes(mem, records, rules) + fake_door_boxes(mem, records))
path = find_path(you, goal, blocked) if goal else None


def spot(xy):
    """Which character of the map a point falls in."""
    return math.floor(xy[0] / CHAR), math.floor(xy[1] / CHAR)


# every other thing near you, grouped by kind = (layer, picture)
things = defaultdict(list)  # kind -> [(card, (x, y), in table), ...]
cards = range(min(records) - 64 * RECORD, max(records) + 64 * RECORD + 1, RECORD) if ALL else records
for card in cards:
    if card == me:
        continue
    try:
        xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
        if not (0.01 < abs(xy[0]) < 100000 and 0.01 < abs(xy[1]) < 100000):
            continue  # junk
        if math.dist(xy, you) > RANGE:
            continue
        layer = read_kind(mem, card, 0, LAYER)
        if layer == AIM_LAYER or (layer == wall_layer and not WALLS):
            continue
        picture = read_kind(mem, card, 1, 0x10)
    except OSError:
        continue
    things[(layer, picture)].append((card, xy, card in records))

# the most common kind gets "a"
kinds = sorted(things, key=lambda kind: -len(things[kind]))[: len(LETTERS)]
letter = {kind: LETTERS[i] for i, kind in enumerate(kinds)}

# draw
walls = set()
for (x1, y1), (x2, y2) in lines:
    steps = max(1, int(math.dist((x1, y1), (x2, y2)) / (CHAR / 2)))
    for i in range(steps + 1):
        walls.add(spot((x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)))
on_way = set()
if path:
    for a, b in zip(path, path[1:]):  # every character the way passes, not only the cell middles
        steps = max(1, int(math.dist(a, b) / (CHAR / 2)))
        for i in range(steps + 1):
            on_way.add(spot((a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)))
at = {}  # character -> letter of the thing there
for kind in kinds:
    for card, xy, _ in things[kind]:
        at.setdefault(spot(xy), letter[kind])
over = Counter()  # letter -> how many of its characters the way goes over

print(f"you {you[0]:.0f},{you[1]:.0f}", end="")
print(f"   crosshair {goal[0]:.0f},{goal[1]:.0f}" if goal else "   (no crosshair)", end="")
print("   way: " + ("NONE" if goal and path is None else f"{len(path)} cells" if path else "-"))
centre = spot(you)
reach = math.ceil(RANGE / CHAR)
for row in range(centre[1] - reach, centre[1] + reach + 1):
    text = ""
    for column in range(centre[0] - reach, centre[0] + reach + 1):
        here = (column, row)
        if here == centre:
            text += "@"
        elif goal and here == spot(goal):
            text += "+"
        elif here in at:
            if here in on_way:
                over[at[here]] += 1
                text += at[here].upper()
            else:
                text += at[here]
        elif here in on_way:
            text += "*"
        elif here in walls:
            text += "#"
        else:
            text += "."
    print(text)

print(f"\nwall layer {wall_layer:#x} ({len(lines)} lines).  Legend (layer, picture):")
for kind in kinds:
    layer, picture = kind
    found = things[kind]
    in_table = sum(1 for _, _, t in found if t)
    card, xy, _ = min(found, key=lambda f: math.dist(f[1], you))
    way = f"   <- the way goes over it {over[letter[kind]]}x" if over[letter[kind]] else ""
    print(
        f"  {letter[kind]}  layer {layer:#10x}  picture {picture:#6x}   {len(found):3} of them"
        f" ({in_table} in table)   nearest {card:#x} at ({xy[0]:4.0f},{xy[1]:4.0f}){way}"
    )
if len(things) > len(kinds):
    print(f"  ... and {len(things) - len(kinds)} more kinds (rare ones) not drawn")
