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
    for card in range(...):  # the same shelf walk as find_me_card
        try:
            if ...:  # the weapon signature: layer FLOOR and picture MARK
                found.append(...)  # (x, y, frame) - frame as a whole number: int(...)
        except OSError:
            continue
    return found
