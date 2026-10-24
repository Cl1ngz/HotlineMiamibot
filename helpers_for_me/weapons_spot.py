# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/weapons.py - every weapon lying on the floor (testing a guess)
#
# Every weapon we looked at with under_aim was TWO cards at the very same spot, both on the
# floor layer (-100): one with picture 0x15 (all of them had it) and one with a picture of its own.
# Guess: picture 0x15 on the floor layer = "a weapon lies here", the other picture = which weapon.
#
#   python -m helpers_for_me.weapons      count the spots it prints vs the weapons you see on the floor
from collections import defaultdict

from enemies import RECORD
from memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records

FLOOR = 0xFFFFFF9C  # layer -100: things lying on the floor (furniture, bodies... and weapons?)
MARK = 0x15  # the picture every weapon had

mem, regions, static_regions = attach()
table = table_records(mem)
if not table:
    raise SystemExit("no table - are you in a level?")

# every card on the floor layer, grouped by where it lies (weapons were two cards on one spot)
spots = defaultdict(list)  # (x, y) -> [(card, picture), ...]
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        if read_kind(mem, card, 0, 0x14) != FLOOR:
            continue
        picture = read_kind(mem, card, 1, 0x10)
        xy = (round(read_double(mem, card + X_OFF), 1), round(read_double(mem, card + Y_OFF), 1))
    except OSError:
        continue  # junk memory past the ends of the shelf
    spots[xy].append((card, picture))

floor_cards = sum(len(things) for things in spots.values())
weapons = {xy: things for xy, things in spots.items() if any(picture == MARK for _, picture in things)}
print(f"{floor_cards} cards on the floor layer, {len(weapons)} spots with picture {MARK:#x}:")
for (x, y), things in sorted(weapons.items()):
    others = [f"{picture:#x}" for _, picture in things if picture != MARK]
    print(f"  at {x:6.1f}, {y:6.1f}   other picture(s) on this spot: {', '.join(others) or 'none'}")
