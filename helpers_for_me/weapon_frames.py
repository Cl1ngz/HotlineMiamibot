# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/weapon_frames.py - which weapon is it?
#
# Every weapon lying on the floor has the same picture (0x15), yet they look different on screen.
# A common GameMaker trick: ONE picture with many frames (bat, pipe, knife...), and the object keeps
# the number of its frame. If so, that number sits somewhere in the card and differs between weapons.
# This shows every spot in the card where the weapons hold DIFFERENT small whole numbers.
#
#   python -m helpers_for_me.weapon_frames
#   Weapons are listed left to right (by X) - write down which weapon is which, then look for a row
#   where the same weapon always has the same number and different weapons have different ones.
import os
import struct

from enemies import RECORD
from memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records

FLOOR = 0xFFFFFF9C  # layer -100: things lying on the floor
MARK = 0x15  # the picture every weapon on the floor has
POSITION = range(X_OFF, X_OFF + 0x20)  # X, Y and the two X copies - skip those, we know them

mem, regions, static_regions = attach()
table = table_records(mem)
if not table:
    raise SystemExit("no table - are you in a level?")

# every weapon card on the shelf
weapons = []
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        if read_kind(mem, card, 0, 0x14) == FLOOR and read_kind(mem, card, 1, 0x10) == MARK:
            weapons.append(card)
    except OSError:
        continue  # junk memory past the ends of the shelf
if len(weapons) < 2:
    raise SystemExit("need at least 2 weapons on the floor to compare")
weapons.sort(key=lambda card: read_double(mem, card + X_OFF))  # left to right
raw = {card: os.pread(mem, RECORD, card) for card in weapons}  # the whole card, once

# header: where each weapon lies
print("weapons left to right:")
for n, card in enumerate(weapons, 1):
    x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
    print(f"  #{n}  at {x:6.1f}, {y:6.1f}   (card {hex(card)})")
print("\n" + " " * 16 + "".join(f"{'#' + str(n):>7}" for n in range(1, len(weapons) + 1)))

# 4-byte whole numbers (like the layer at +0x14)
for offset in range(0, RECORD - 3, 4):
    if offset in POSITION:
        continue
    values = [int.from_bytes(raw[card][offset : offset + 4], "little") for card in weapons]
    if len(set(values)) > 1 and all(v < 1000 for v in values):
        print(f"  4 bytes {offset:#6x}" + "".join(f"{v:7}" for v in values))

# 8-byte doubles that are whole numbers (GameMaker keeps frame numbers as doubles)
for offset in range(0, RECORD - 7, 4):
    if offset in POSITION:
        continue
    values = [struct.unpack("<d", raw[card][offset : offset + 8])[0] for card in weapons]
    if len(set(values)) > 1 and all(0 <= v < 1000 and v.is_integer() for v in values):
        print(f"  double  {offset:#6x}" + "".join(f"{v:7.0f}" for v in values))
