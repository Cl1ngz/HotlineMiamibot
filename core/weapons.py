# https://github.com/Cl1ngz/HotlineMiamibot
# core/weapons.py - weapons and goals (the briefcase) lying on the floor, and which weapon to go for
# floor layer -100 + picture 0x15 = weapon, its frame at +0x98 = which one (weapon_names.json, tools/weapon_tool.py)
import json
import math

from .memory import X_OFF, Y_OFF, read_double, read_kind
from .walls import can_see

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


def find_weapons(mem, cards):
    """[(x, y, frame), ...] for every weapon lying on the floor."""
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


def find_goals(mem, cards):
    """[(x, y), ...] for every goal (the briefcase...) lying on the floor."""
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


def held_rank(hand, names):
    """Rank of the weapon in your hand (card +0xA0 at rest), or None: not a weapon we know (mid-swing, a gun...)."""
    for info in names.values():
        if "hand" in info and int(info["hand"], 16) == hand:
            return info.get("rank", 0)
    return None


def choose_weapon(weapons, you, enemy_far, lines):
    """The weapon to go for, (x, y), or None.
    Only weapons you can see, and only if the nearest one is closer than the enemy (enemy_far = math.inf: no enemy).
    """
    seen = [xy for xy in weapons if can_see(you, xy, lines)]
    if not seen:
        return None
    nearest = min(seen, key=lambda xy: math.dist(xy, you))
    if math.dist(nearest, you) > enemy_far:
        return None
    return nearest
