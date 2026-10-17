# https://github.com/Cl1ngz/HotlineMiamibot
# weapons.py - weapons lying on the floor
#
# A weapon on the floor = a card on the floor layer (-100) with picture 0x15.
# The frame number at card +0x98 says which weapon it is (names: weapon_names.json, made by name_weapon.py).
import json

from .enemies import RECORD
from .memory import X_OFF, Y_OFF, read_double, read_kind, table_records

# layer -100: things lying on the floor
FLOOR = 0xFFFFFF9C
# the picture every weapon on the floor has
MARK = 0x15
# where the frame number (= which weapon) sits in the card
FRAME = 0x98
NAMES_FILE = "weapon_names.json"


def load_names():
    """{frame number: {"name": ..., "kind": ...}} - empty if nothing was saved yet."""
    try:
        with open(NAMES_FILE) as f:
            return {int(frame): info for frame, info in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def find_weapons(mem):
    """[(x, y, frame), ...] for every weapon lying on the floor."""
    cards = table_records(mem)
    if not cards:
        return []
    found = []
    for card in range(min(cards) - 64 * RECORD, max(cards) + 64 * RECORD + 1, RECORD):
        try:
            # the weapon signature: layer FLOOR and picture MARK
            if (
                read_kind(mem, card, 0, 0x14) == FLOOR
                and read_kind(mem, card, 1, 0x10) == MARK
            ):
                x = read_double(mem, card + X_OFF)
                y = read_double(mem, card + Y_OFF)
                frame = read_double(mem, card + FRAME)
                found.append((x, y, int(frame)))
        except OSError:
            continue
    return found
