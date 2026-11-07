# https://github.com/Cl1ngz/HotlineMiamibot
# weapons.py - weapons lying on the floor
#
# A weapon on the floor = a card on the floor layer (-100) with picture 0x15.
# The frame number at card +0x98 says which weapon it is (names: weapon_names.json, made by tools/weapon_tool.py).
# A goal (the briefcase...) = a card on the floor layer with its own picture (GOAL).
import json

from .enemies import shelf_cards
from .memory import X_OFF, Y_OFF, read_double, read_kind, table_records

# layer -100: things lying on the floor
FLOOR = 0xFFFFFF9C
# the picture every weapon on the floor has
MARK = 0x15
# where the frame number (= which weapon) sits in the card
FRAME = 0x98
NAMES_FILE = "weapon_names.json"
# the picture of a goal to take for the level: the briefcase (there are 4-5 such things - more to find)
GOAL = 0xCB


def load_names():
    """{frame number: {"name": ..., "kind": ...}} - empty if nothing was saved yet."""
    try:
        with open(NAMES_FILE) as f:
            return {int(frame): info for frame, info in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def find_weapons(mem, cards=None):
    """[(x, y, frame), ...] for every weapon lying on the floor."""
    if cards is None:
        cards = shelf_cards(mem, table_records(mem))
    found = []
    for card in cards:
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


def find_goals(mem, cards=None):
    """[(x, y), ...] for every goal (the briefcase...) lying on the floor."""
    if cards is None:
        cards = shelf_cards(mem, table_records(mem))
    found = []
    for card in cards:
        try:
            # the goal signature: layer FLOOR and picture GOAL
            if (
                read_kind(mem, card, 0, 0x14) == FLOOR
                and read_kind(mem, card, 1, 0x10) == GOAL
            ):
                x = read_double(mem, card + X_OFF)
                y = read_double(mem, card + Y_OFF)
                found.append((x, y))
        except OSError:
            continue
    return found
