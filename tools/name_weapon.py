# https://github.com/Cl1ngz/HotlineMiamibot
# teach the bot the name of a weapon
#
# A weapon lying on the floor = a card on the floor layer (-100) with picture 0x15.
# Its frame number (the double at card +0x98) says WHICH weapon it is: Lead Pipe 3, Baseball Bat 4, Knife 5...
# Aim at a weapon on the floor and give it a name and a kind - it's saved to weapon_names.json.
#
#   python -m helpers_for_me.name_weapon "Lead Pipe" melee
#   python -m helpers_for_me.name_weapon "Shotgun" gun
#   python -m helpers_for_me.name_weapon "Glass Bottle" throw
#   python -m helpers_for_me.name_weapon                     (no name: just show what's known)
import json
import math
import sys

from core.enemies import RECORD, find_aim
from core.memory import (
    X_OFF,
    Y_OFF,
    attach,
    read_double,
    read_kind,
    table_records,
    wait,
)
from core.weapons import load_names

# layer -100: things lying on the floor
FLOOR = 0xFFFFFF9C
# the picture every weapon on the floor has
MARK = 0x15
# where the frame number (= which weapon) sits in the card
FRAME = 0x98
# game units around the crosshair
CLOSE = 20
KINDS = ("melee", "gun", "throw")
NAMES_FILE = "weapon_names.json"


def show(names):
    print(f"\n{len(names)} weapons known:")
    for frame, info in sorted(names.items()):
        print(f"  frame {frame:3}  {info['name']:16} {info['kind']}")


names = load_names()
if len(sys.argv) < 2:
    show(names)
    raise SystemExit
if len(sys.argv) < 3 or sys.argv[2] not in KINDS:
    raise SystemExit(
        f'usage: python -m helpers_for_me.name_weapon "Lead Pipe" melee   (kind: {", ".join(KINDS)})'
    )
name, kind = sys.argv[1], sys.argv[2]

mem, regions, static_regions = attach()
find_aim(
    mem
)  # first look - find_aim needs to see the crosshair move to tell it from a frozen copy
wait(f"aim at the {name} lying on the floor and hold the mouse still", 3)
aim = find_aim(mem)  # second look: now it knows the live crosshair
if aim is None:
    raise SystemExit("no crosshair - are you in a level?")

# the weapon card closest to the crosshair (walk the whole shelf - weapons are often not in the table)
table = table_records(mem)
best, best_distance = None, CLOSE
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        if (
            read_kind(mem, card, 0, 0x14) != FLOOR
            or read_kind(mem, card, 1, 0x10) != MARK
        ):
            continue
        distance = math.dist(
            (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)), aim
        )
    except OSError:
        continue  # junk memory past the ends of the shelf
    if distance < best_distance:
        best, best_distance = card, distance
if best is None:
    raise SystemExit(
        "no weapon under the crosshair - aim right at it (it has to lie still on the floor)"
    )

frame = int(read_double(mem, best + FRAME))
old = names.get(frame)
if old and old["name"] != name:
    print(f"careful: frame {frame} was saved as {old['name']} - now it's {name}")
names[frame] = {"name": name, "kind": kind}
with open(NAMES_FILE, "w") as f:
    json.dump({str(frame): info for frame, info in sorted(names.items())}, f, indent=2)
print(f"saved: frame {frame} = {name} ({kind})")
show(names)
