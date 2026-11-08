# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/far_cards.py - does the bot miss cards on this floor? (a helper, only reads)
#
# The bot, the radar and enemy_tool all look at the cards from 64 places BEFORE the table's first card
# to 64 AFTER its last one (shelf_cards, find_me_card, find_aim_card). Outside, by the dumpster, even the
# crosshair wasn't found (radar: "aim -"), and the enemy that comes there was never seen.
# This looks 4096 places both ways, at one moment, and tells for every card: inside the bot's window or not.
#
#   python -m helpers_for_me.far_cards      the bot must NOT run (it moves the look). Stand where the
#                                           enemy is in sight, mouse on him if you can - 3 s to get ready.
import math
from collections import Counter

from core.enemies import RECORD
from core.hands import LOOK_X, LOOK_Y, follow
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records, wait

WIDE = 4096  # look this many places before the table's first card and after its last one (the bot: 64)
WINDOW = 64  # what the bot looks at around the table
NEAR = 24  # cards this close to the mouse get printed
SHOW = 40  # print at most this many of the cards outside the window

mem, regions, static_regions = attach()
wait("stand where the enemy is in sight (mouse on him if you can) - the bot must not run", 3)
table = table_records(mem)
if not table:
    raise SystemExit("no table - are you in a level?")
first, last = min(table), max(table)
try:
    look = (read_double(mem, follow(mem, LOOK_X)), read_double(mem, follow(mem, LOOK_Y)))
except OSError:
    look = None


def where_is(card):
    """Inside the bot's window, or how far outside it."""
    if card < first - WINDOW * RECORD:
        return f"OUTSIDE: {(first - card) // RECORD - WINDOW} places before the window"
    if card > last + WINDOW * RECORD:
        return f"OUTSIDE: {(card - last) // RECORD - WINDOW} places after the window"
    return "inside"


def line(card, xy, layer, state, picture):
    place = "table" if card in table else "shelf"
    return (
        f"  {card:#x} at ({xy[0]:5.0f},{xy[1]:5.0f})  layer {layer:#6x}  +0x10 {state:#6x}"
        f"  picture {picture:#6x}  {place}  {where_is(card)}"
    )


# every card at a real position, this wide
found = []  # (card, (x, y), layer, +0x10, picture)
for card in range(first - WIDE * RECORD, last + WIDE * RECORD + 1, RECORD):
    try:
        x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        if not (0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000):
            continue  # junk, or a card with no place
        layer = read_kind(mem, card, 0, 0x14)
        state = read_kind(mem, card, 0, 0x10)
        picture = read_kind(mem, card, 1, 0x10)
    except OSError:
        continue  # junk memory between the cards
    found.append((card, (x, y), layer, state, picture))

outside = [f for f in found if where_is(f[0]) != "inside"]
print(f"\ntable: {len(table)} cards   cards at a real position: {len(found)}, {len(outside)} of them OUTSIDE the window")

print("\nthe crosshair card (layer 0xaf, picture 0xa5):")
aims = [f for f in found if f[2] == 0xAF and f[4] == 0xA5]
for f in aims:
    print(line(*f))
if not aims:
    print("  none, even this wide")

if look is not None:
    print(f"\nthe mouse is at {look[0]:.0f},{look[1]:.0f} - cards close to it (closest first):")
    close = sorted((f for f in found if math.dist(f[1], look) < NEAR), key=lambda f: math.dist(f[1], look))
    for f in close:
        print(line(*f))
    if not close:
        print("  none")

print("\noutside the window, by layer (layer 6 = a walking enemy):")
for layer, count in Counter(f[2] for f in outside).most_common():
    print(f"  layer {layer:#6x}: {count}")
print(f"\noutside the window, the first {SHOW}:")
for f in outside[:SHOW]:
    print(line(*f))
