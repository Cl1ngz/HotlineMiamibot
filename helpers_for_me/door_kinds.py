# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/door_kinds.py - which "doors" are windows? (a helper, only reads)
#
# A window's box looks like a door's (a thin plank 32 long), so the bot walks into the glass, pushes it twice
# and saves it as a FAKE door (doors.json). This lists everything with a door's box on this floor, with its
# layer and its picture, the fake ones marked. If the fake ones share a layer or a picture the real doors
# don't have, that's how the bot can tell a window before it bumps into it.
#
#   python -m helpers_for_me.door_kinds      the bot must NOT run - stand on the floor with the windows
from collections import Counter

from core.enemies import shelf_cards
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records
from core.scenes import load_doors, scene_id
from core.walls import WALL, looks_like_door, read_box, real_walls

WIDE = 1024  # cards this far around the table, like see.py

mem, regions, static_regions = attach()
records = table_records(mem)
if not records:
    raise SystemExit("no table - are you in a level?")
cards = shelf_cards(mem, records, WIDE)
walls = real_walls(mem, records, cards)
scene = scene_id(walls)
fake = {tuple(box) for box in load_doors().get(scene, [])}
print(
    f"floor {scene}: {len(walls)} walls, {len(fake)} fake doors saved for it in doors.json\n"
)

found = (
    {}
)  # box -> (layer, card +0x10, picture, card +0x4) - a set of boxes: the table and the shelf repeat
for card in cards:
    try:
        layer = read_kind(mem, card, 0, 0x14)
        if layer == WALL:
            continue
        xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
        box = read_box(mem, card, xy)
        if not looks_like_door(box):
            continue
        found[box] = (
            layer,
            read_kind(mem, card, 0, 0x10),
            read_kind(mem, card, 1, 0x10),
            read_kind(mem, card, 0, 0x4),
        )
    except OSError:
        continue

print("         box (left, top, right, bottom)   layer       +0x10   picture   +0x4")
for box, (layer, ten, picture, four) in sorted(found.items()):
    mark = "FAKE" if box in fake else "    "
    print(f"  {mark}  {str(box):32} {layer:#10x} {ten:#8x} {picture:#9x} {four:#6x}")

# the same layer / picture for the fake ones and the rest?
print("\nlayer, picture -> fake / the rest")
kinds = Counter()
for box, (layer, ten, picture, four) in found.items():
    kinds[(layer, picture, box in fake)] += 1
for layer, picture in sorted({(k[0], k[1]) for k in kinds}):
    print(
        f"  layer {layer:#x}, picture {picture:#x}:  {kinds[(layer, picture, True)]} fake,"
        f" {kinds[(layer, picture, False)]} the rest"
    )
missing = fake - set(found)
if missing:
    print(
        f"\nfake doors in doors.json not found now (opened? another floor?): {sorted(missing)}"
    )
