# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/phantom_diff.py - how is a weapon on the floor different from a frame-0 phantom?
#
# The M16 is frame 0 of the weapon picture - and so are the phantoms (doors have them), so the frame
# alone can't tell them apart. Each run keeps the numbers of every weapon on the floor (the M16 under
# the crosshair + every weapon with frame > 0) and of every phantom (the other frame-0 cards), then
# looks for a spot where ALL weapons have one number and NO phantom has it. Kept in phantom_diff.json,
# so it can come from several floors - the more floors, the surer the sign.
#
#   python -m helpers_for_me.phantom_diff         aim at the M16 on the floor (3 s), keep this floor, compare
#   python -m helpers_for_me.phantom_diff clear   forget everything kept
import json
import math
import os
import sys
import time

from core.enemies import copy_memory, find_aim, shelf_cards
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records, wait
from core.weapons import FLOOR, FRAME, MARK, load_names

FILE = "phantom_diff.json"
CLOSE = 20  # the M16 must be this close to the crosshair
WIDE = 1024  # look this far around the table
WATCH = 4  # read everything this many times, 0.25 s apart: only numbers that never change count
SKIP = range(X_OFF, X_OFF + 0x20)  # X, Y and their copies
SMALL = 0x10000  # below this (or this close below 0) = a flag / kind, bigger = maybe a pointer
SHOW = 15


def small(value):
    return value < SMALL or value > 0xFFFFFFFF - SMALL


def xy(card):
    return read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)


def load():
    try:
        with open(FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"real": [], "phantom": []}


if sys.argv[1:] == ["clear"]:
    if os.path.exists(FILE):
        os.remove(FILE)
    raise SystemExit("forgot everything")

mem, regions, static_regions = attach()
names = load_names()
find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("aim at the M16 lying on the floor and hold the mouse still", 3)
aim = find_aim(mem)
table = table_records(mem)
if aim is None or not table:
    raise SystemExit("no crosshair - are you in a level?")

# every weapon card on the floor, with its frame
cards = {}
for card in shelf_cards(mem, table, WIDE):
    try:
        if read_kind(mem, card, 0, 0x14) == FLOOR and read_kind(mem, card, 1, 0x10) == MARK:
            cards[card] = int(read_double(mem, card + FRAME))
    except OSError:
        continue
zero = sorted((math.dist(xy(card), aim), card) for card, frame in cards.items() if frame == 0)
m16 = zero[0][1] if zero and zero[0][0] < CLOSE else None
real = {card: names.get(frame, {}).get("name", f"frame {frame}") for card, frame in cards.items() if frame}
if m16:
    real[m16] = "M16"
phantoms = [card for _, card in zero if card != m16]

print("on this floor:")
print("  M16 under the crosshair" if m16 else "  no M16 under the crosshair - keeping the other weapons only")
for card, name in real.items():
    print(f"  weapon  {name:14} at ({xy(card)[0]:4.0f},{xy(card)[1]:4.0f})")
for card in phantoms:
    print(f"  phantom                at ({xy(card)[0]:4.0f},{xy(card)[1]:4.0f})   (should be next to a door)")

# the 4-byte numbers of each card (where 0) and its folder (where 1) that stayed the same every read
stable = {}
for _ in range(WATCH):
    for card, (rec, obj) in copy_memory(mem, list(real) + phantoms).items():
        now = {}
        for where, data in ((0, rec), (1, obj)):
            for offset in range(0, len(data) - 3, 4):
                if where == 0 and offset in SKIP:
                    continue
                now[f"{where}:{offset}"] = int.from_bytes(data[offset : offset + 4], "little")
        old = stable.get(card)
        stable[card] = now if old is None else {k: v for k, v in old.items() if now.get(k) == v}
    time.sleep(0.25)

data = load()
data["real"] += [{"name": real[card], "bytes": stable[card]} for card in real if card in stable]
data["phantom"] += [{"bytes": stable[card]} for card in phantoms if card in stable]
with open(FILE, "w") as f:
    json.dump(data, f)
kept = ", ".join(sorted({r["name"] for r in data["real"]}))
print(f"\nkept so far: {len(data['real'])} weapons ({kept}), {len(data['phantom'])} phantoms")
if not data["real"] or not data["phantom"]:
    raise SystemExit("need both weapons and phantoms - run it on a floor that has both")

# spots where every weapon has one number and no phantom has it; best first: the phantoms agree too
found = []
for key, value in data["real"][0]["bytes"].items():
    mine = [r["bytes"].get(key) for r in data["real"]]
    theirs = [p["bytes"].get(key) for p in data["phantom"]]
    if None in mine or None in theirs or len(set(mine)) > 1 or value in theirs:
        continue
    where, offset = (int(part) for part in key.split(":"))
    found.append((len(set(theirs)) > 1, not small(value), where, offset, value, sorted(set(theirs))))
found.sort()
if not found:
    raise SystemExit("no number tells them apart - send me this output")

print("\n  spot            weapons      phantoms")
for not_agree, big, where, offset, value, theirs in found[:SHOW]:
    spot = f"{'card' if where == 0 else 'folder'} {offset:+#x}"
    shown = f"{theirs[0]:#x} (all)" if not not_agree else ", ".join(hex(t) for t in theirs[:4])
    note = "   (big - maybe a pointer)" if big else ""
    print(f"  {spot:14}  {value:#10x}   {shown}{note}")
if len(found) > SHOW:
    print(f"  ... and {len(found) - SHOW} more")
