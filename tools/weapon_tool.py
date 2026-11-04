# https://github.com/Cl1ngz/HotlineMiamibot
# tools/weapon_tool.py - everything about weapon names, in one place (they live in weapon_names.json)
#
# A weapon lying on the floor = a card on the floor layer (-100) with folder picture 0x15. The frame number
# (the double at card +0x98) says WHICH weapon it is. hmbot only picks up weapons whose kind is "melee".
#
#   python -m tools.weapon_tool                        the known weapons + every weapon on the floor right now
#   python -m tools.weapon_tool name "Lead Pipe" melee aim at a weapon on the floor (3 s), save its name and kind
#   python -m tools.weapon_tool forget 7               forget the name of frame 7 (a wrong name)
#
# kinds: melee (walk up and hit - hmbot uses these), gun (shoots - hmbot can't aim it yet), throw
import json
import math
import sys

from core.enemies import RECORD, find_aim, find_me
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records, wait
from core.weapons import FLOOR, FRAME, MARK, NAMES_FILE, load_names

CLOSE = 20  # the weapon must be this close to the crosshair
KINDS = ("melee", "gun", "throw")

names = load_names()  # {frame: {"name": ..., "kind": ...}}
args = sys.argv[1:]


def save(names):
    with open(NAMES_FILE, "w") as f:
        json.dump({str(frame): info for frame, info in sorted(names.items())}, f, indent=2)


def show_known():
    print(f"{len(names)} weapons known:")
    for frame, info in sorted(names.items()):
        print(f"  frame {frame:3}  {info['name']:16} {info['kind']}")


def floor_weapons(mem):
    """{card: (x, y, frame)} of every weapon lying on the floor (the whole shelf - weapons are often not in the table)."""
    table = table_records(mem)
    if not table:
        return {}
    found = {}
    for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
        try:
            if read_kind(mem, card, 0, 0x14) != FLOOR or read_kind(mem, card, 1, 0x10) != MARK:
                continue
            x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
            found[card] = (x, y, int(read_double(mem, card + FRAME)))
        except OSError:
            continue  # junk memory past the ends of the shelf
    return found


# --- forget N: no game needed ---
if args and args[0] == "forget":
    if len(args) != 2 or not args[1].isdigit():
        raise SystemExit("usage: python -m tools.weapon_tool forget 7   (the frame number from the list)")
    frame = int(args[1])
    if frame not in names:
        raise SystemExit(f"frame {frame} has no name")
    info = names.pop(frame)
    save(names)
    print(f"forgot frame {frame} ({info['name']})")
    show_known()
    raise SystemExit

# --- name "..." kind: aim at the weapon ---
if args and args[0] == "name":
    if len(args) != 3 or args[2] not in KINDS:
        raise SystemExit(f'usage: python -m tools.weapon_tool name "Lead Pipe" melee   (kind: {", ".join(KINDS)})')
    weapon, kind = args[1], args[2]
    mem, regions, static_regions = attach()
    find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
    wait(f"aim at the {weapon} lying on the floor and hold the mouse still", 3)
    aim = find_aim(mem)
    if aim is None:
        raise SystemExit("no crosshair - are you in a level?")
    near = [(math.dist(w[:2], aim), w[2]) for w in floor_weapons(mem).values() if math.dist(w[:2], aim) < CLOSE]
    if not near:
        raise SystemExit("no weapon under the crosshair - aim right at it (it has to lie still on the floor)")
    frame = min(near)[1]
    if frame == 0:
        raise SystemExit("that's a frame-0 phantom (doors have them too), not a weapon - aim at the weapon itself")
    old = names.get(frame)
    if old and old["name"] != weapon:
        print(f"careful: frame {frame} was saved as {old['name']} - now it's {weapon}")
    names[frame] = {"name": weapon, "kind": kind}
    save(names)
    print(f"saved: frame {frame} = {weapon} ({kind})")
    show_known()
    raise SystemExit

if args:
    raise SystemExit('usage: python -m tools.weapon_tool [name "Lead Pipe" melee | forget 7]')

# --- list ---
show_known()
mem, regions, static_regions = attach()
you = find_me(mem)
weapons = floor_weapons(mem)
print(f"\non the floor now ({len(weapons)}):" if weapons else "\nno weapons on the floor (or not in a level)")
for card, (x, y, frame) in sorted(weapons.items(), key=lambda cw: math.dist(cw[1][:2], you) if you else 0):
    label = "phantom (frame 0)" if frame == 0 else names.get(frame, {}).get("name", f"UNKNOWN frame {frame}")
    far = f"far {math.dist((x, y), you):4.0f}" if you else ""
    print(f"  {label:20} at ({x:4.0f},{y:4.0f})  {far}")
if any(frame not in names and frame != 0 for _, _, frame in weapons.values()):
    print('\nname the UNKNOWN ones: python -m tools.weapon_tool name "Shotgun" gun   (aim at it)')
