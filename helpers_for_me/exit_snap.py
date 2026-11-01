# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/exit_snap.py - floor 1 at the END of the level: where does GO! point now, and how does memory show it?
#
# The bot came back down to floor 1 and went straight up again: the stairs card there (+0x10 = 0x51) still has
# +0x90 = 1 from when floor 1 was cleared, so find_stairs keeps saying "go there". At the end GO! points to the
# CAR instead. This compares floor 1 at two moments and prints what's different:
#   save     floor 1 just cleared, GO! points to the stairs (the first time)
#   compare  floor 1 again at the end, GO! points to the car
# The floor is loaded again in between, so cards get new addresses - they're matched by kind and position.
#
#   python -m helpers_for_me.exit_snap save    (floor 1, right when GO! shows the first time)
#   python -m helpers_for_me.exit_snap         (floor 1 at the end - STOP hmbot first, or it walks up again)
import json
import sys

from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, read_u32, table_records

FILE = "exit_snap.json"
EXITS = (0x51, 0x55)  # card +0x10 of the stairs-ish objects we know
SKIP_LAYERS = (0x2C, 0xAF)  # you and the crosshair move all the time - not interesting
SKIP_OFFSETS = range(X_OFF, X_OFF + 0x20)  # x, y and their copies

mem, regions, static_regions = attach()


def snapshot():
    """{key: info} for every table card. key = "layer kind picture x y" (the same thing after a reload)."""
    things = {}
    for card in table_records(mem):
        try:
            layer = read_kind(mem, card, 0, 0x14)
            kind = read_kind(mem, card, 0, 0x10)
            picture = read_kind(mem, card, 1, 0x10)
            x, y = round(read_double(mem, card + X_OFF)), round(read_double(mem, card + Y_OFF))
            numbers = {}
            if kind in EXITS:  # remember every 4-byte spot of the stairs-ish cards
                numbers = {o: read_u32(mem, card + o) for o in range(0, 0xB8, 4) if o not in SKIP_OFFSETS}
        except OSError:
            continue
        if layer in SKIP_LAYERS:
            continue
        things[f"{layer:#x} {kind:#x} {picture:#x} {x} {y}"] = {"card": card, "numbers": numbers}
    return things


def show(key):
    layer, kind, picture, x, y = key.split()
    return f"({x:>4},{y:>4})  layer {layer:>10}  +0x10 {kind:>5}  picture {picture:>5}"


now = snapshot()
if not now:
    raise SystemExit("nothing in the table - menu or loading?")
if len(sys.argv) > 1 and sys.argv[1] == "save":
    with open(FILE, "w") as f:
        json.dump(now, f)
    exits = [key for key in now if int(key.split()[1], 16) in EXITS]
    raise SystemExit(f"saved {len(now)} things ({len(exits)} stairs-ish) to {FILE}")

try:
    with open(FILE) as f:
        before = json.load(f)
except OSError:
    raise SystemExit(f"no {FILE} - run 'python -m helpers_for_me.exit_snap save' first (floor 1, first GO!)")

print("NEW on floor 1 (not there at the first GO!):")
new = [key for key in now if key not in before]
for key in sorted(new, key=lambda k: k.split()[:3]):
    print("  " + show(key))
print("  nothing" if not new else "")
print("GONE from floor 1:")
gone = [key for key in before if key not in now]
for key in sorted(gone, key=lambda k: k.split()[:3]):
    print("  " + show(key))
print("  nothing" if not gone else "")
print("stairs-ish cards (+0x10 0x51 / 0x55) - which 4-byte spots changed (first GO! -> now):")
for key, info in now.items():
    if not info["numbers"] or key not in before:
        continue
    old = {int(o): v for o, v in before[key]["numbers"].items()}
    changed = [f"+{o:#x}: {old[o]:#x} -> {v:#x}" for o, v in info["numbers"].items() if old.get(o) != v]
    print(f"  {show(key)}   " + (", ".join(changed) if changed else "(nothing changed)"))
