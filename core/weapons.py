# https://github.com/Cl1ngz/HotlineMiamibot
# core/weapons.py - weapons and goals (the briefcase) lying on the floor, and which weapon to go for
# floor layer -100 + picture 0x15 = weapon, its frame at +0x98 = which one (weapon_names.json, tools/weapon_tool.py)
import json
import math

from .memory import X_OFF, Y_OFF, read_bytes, read_double, read_kind, read_u32
from .walls import can_see

# layer -100: things lying on the floor
FLOOR = 0xFFFFFF9C
# the picture every weapon on the floor has
MARK = 0x15
# card +0x10 of every weapon (enemies have 6 there) - the frame-0 phantoms by the doors have 21 or 23
WEAPON = 7
# where the frame number (= which weapon) sits in the card
FRAME = 0x98
NAMES_FILE = "weapon_names.json"
# the picture of a goal to take for the level: the briefcase (there are 4-5 such things - more to find)
GOAL = 0xCB
# your ammo: a 4-byte whole number on the heap, reached by links from fixed places in the game file
# (helpers_for_me/ammo_chains - they lasted a new floor, a death and a game restart). The first one that reads wins.
AMMO_CHAINS = [
    (0xB99178, [0x330, 0x78, 0x167], 0x8),
    (0xB9F06C, [0x115, 0x10, 0x167], 0x8),
    (0xBA1D08, [0x112, 0x9D, 0x167], 0x8),
]
AMMO_MOST = 250  # more than this = junk


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
            # the weapon signature: layer FLOOR, picture MARK and WEAPON at +0x10
            if (
                read_kind(mem, card, 0, 0x14) == FLOOR
                and read_kind(mem, card, 1, 0x10) == MARK
                and read_kind(mem, card, 0, 0x10) == WEAPON
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


def pictures(info, key):
    """The hand picture(s) of a weapon_names.json entry as numbers - "fire" can be one or a list."""
    value = info.get(key, [])
    return [int(v, 16) for v in (value if isinstance(value, list) else [value])]


def held_rank(hand, names):
    """Rank of the weapon in your hand (card +0xA0 at rest), or None: not a weapon we know (mid-swing, a gun...)."""
    for info in names.values():
        if hand in pictures(info, "hand"):
            return info.get("rank", 0)
    return None


def gun_frame(hand, names):
    """Which gun your hand shows, at rest or shooting ("hand" / "fire" in weapon_names.json): its frame, or None."""
    for frame, info in names.items():
        if info.get("kind") == "gun" and hand in pictures(info, "hand") + pictures(
            info, "fire"
        ):
            return frame
    return None


def enemy_gun(picture, names):
    """Does an enemy with this picture (his card +0xA0) carry a gun? ("enemy" of a gun in weapon_names.json)"""
    return any(
        picture in pictures(info, "enemy")
        for info in names.values()
        if info.get("kind") == "gun"
    )


def held_gun(hand, names):
    """Does your hand show a gun - at rest or shooting?"""
    return gun_frame(hand, names) is not None


def read_ammo(mem):
    """Ammo of the gun in your hand, or None (no chain can be read now). Ask only when you hold a gun."""
    for start, offsets, last in AMMO_CHAINS:
        try:
            here = read_u32(mem, start)
            for offset in offsets:
                here = read_u32(mem, here + offset)
            ammo = int.from_bytes(
                read_bytes(mem, 4, here + last), "little", signed=True
            )
        except OSError:
            continue
        if 0 <= ammo <= AMMO_MOST:
            return ammo
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
