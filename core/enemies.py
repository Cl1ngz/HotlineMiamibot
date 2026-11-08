# https://github.com/Cl1ngz/HotlineMiamibot
# telling enemies apart from walls, you and everything else
import math
import os
import time

from .memory import (
    X_OFF,
    Y_OFF,
    load_address,
    read_bytes,
    read_double,
    read_kind,
    save_address,
    table_records,
)

# Size of one table record
# 4bytes (X at +0x50, Y at +0x58)
RECORD = 0xB8
INSTANCE = 0x6D0  # bytes in the bigger object behind the record's first pointer
AIM_PICTURE = 0xA5  # the crosshair's picture (folder +0x10) - always the same; its layer is NOT (0xAF, outside by the dumpster 0x1)


def find_me_card(mem):
    cards = table_records(mem)
    if not cards:
        return None
    # now ex found = {0x2422de8: (320, 472), 0x2424150: (388, 160)}
    found = {}
    # 64 cards is jsut a guess resonable number to compute
    # thats why try exept is here cus fricking errors
    for card in range(min(cards) - 64 * RECORD, max(cards) + 64 * RECORD + 1, RECORD):
        try:
            if (
                read_kind(mem, card, 0, 0x14) == 0x2C
                and read_kind(mem, card, 1, 0x10) == 0x47
            ):
                found[card] = (
                    read_double(mem, card + X_OFF),
                    read_double(mem, card + Y_OFF),
                )
        except OSError:
            continue
    # menu or loading
    if not found:
        return None
    if len(found) == 1:
        return list(found)[0]

    # more that one you
    # closes to the crosshair is the real one i guess
    aims = []
    for card, xy in cards.items():
        try:
            if read_kind(mem, card, 0, 0x14) == 0xAF:
                aims.append(xy)
        except OSError:
            # empty space this card reserve probobly causes it
            continue
    if not aims:
        return None
    return min(found, key=lambda card: min(math.dist(found[card], aim) for aim in aims))


# My (x, y), or None
def find_me(mem):
    card = find_me_card(mem)
    if card is None:
        return None

    # read X and Y from the card
    return (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))


# Crosshair card where it was last time checked
aim_last_xy = {}
# croshair card when last time moved
aim_last_move = {}


# card +0x14 = 0xAF  and  folder +0x10 = 0xA5
def find_aim_card(mem):
    cards = table_records(mem)
    if not cards:
        return None
    aims = {}
    for card in range(min(cards) - 64 * RECORD, max(cards) + 64 * RECORD + 1, RECORD):
        try:
            # the crosshair: known by its picture - its layer changes from floor to floor
            if read_kind(mem, card, 1, 0x10) == AIM_PICTURE:
                aims[card] = (
                    read_double(mem, card + X_OFF),
                    read_double(mem, card + Y_OFF),
                )
        except OSError:
            continue
    if not aims:
        return None
    now = time.monotonic()
    for card, xy in aims.items():
        # card is not in same place as last time we checked, so it moved
        if aim_last_xy.get(card) != xy:
            # record when it moved
            aim_last_move[card] = now
        # remember where it is now
        aim_last_xy[card] = xy
    # last to move
    best = max(aims, key=lambda card: aim_last_move[card])
    return best


def find_aim(mem):
    """(x, y) of the live crosshair, or None"""
    card = find_aim_card(mem)
    if card is None:
        return None
    # read X and Y from the card
    return (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))


# [(kind rule, check), ...] - filled in by load_rules(), used by is_enemy()
dead_checks = []


# flat list addresses.json
# where offse value
def read_flat(name):
    try:
        return load_address(name)
    except (KeyError, ValueError, OSError):
        return []


def load_rules():
    global dead_checks

    # read the dead checks first, so is_enemy() can use them
    flat = read_flat("dead")
    dead_checks = []
    for i in range(0, len(flat) - 5, 6):
        kind = tuple(flat[i : i + 3])
        check = tuple(flat[i + 3 : i + 6])
        dead_checks.append((kind, check))

    # read the enemy rules
    flat = read_flat("enemy")
    rules = []
    for i in range(0, len(flat) - 2, 3):
        rules.append(tuple(flat[i : i + 3]))
    return rules


def save_rules(rules):
    save_address("enemy", [number for rule in rules for number in rule])


def save_dead_checks(checks):
    save_address("dead", [number for kind, check in checks for number in kind + check])


def matches(mem, record, where, offset, value):
    try:
        return read_kind(mem, record, where, offset) == value
    except OSError:
        return False


def is_enemy(mem, record, rules):
    """Does this card match an enemy rule - and not that rule's death sign?
    The whole card is read in ONE go (0xB8 bytes) and the numbers are taken from those bytes:
    ~3x faster than one read_kind per rule (5 rules + the death signs)."""
    try:
        card = read_bytes(mem, RECORD, record)
    except OSError:
        return False
    if len(card) < RECORD:
        return False

    # a function inside a function: it sees `card`, `mem` and `record` from is_enemy
    def has(where, offset, value):
        if where == 0:
            # the 4-byte number at `offset` inside the card's bytes
            return int.from_bytes(card[offset : offset + 4], "little") == value
        # a pocket in the folder: read it like before
        return matches(mem, record, where, offset, value)

    for rule in rules:
        if has(*rule):
            return not any(has(*check) for kind, check in dead_checks if kind == rule)
    return False


# record: (record bytes, object bytes)} for every object we can read
def copy_memory(mem, records):
    copies = {}
    for record in records:
        try:
            rec = os.pread(mem, RECORD, record)
            obj = os.pread(mem, INSTANCE, int.from_bytes(rec[:4], "little"))
        except OSError:
            continue
        if len(rec) == RECORD and len(obj) == INSTANCE:
            copies[record] = (rec, obj)
    return copies


def shelf_cards(mem, records):
    """Cards on the shelf around the table's cards (also NOT in the table) that stand at a real position."""
    if not records:
        return []
    cards = []
    for card in range(
        min(records) - 64 * RECORD, max(records) + 64 * RECORD + 1, RECORD
    ):
        try:
            x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        except OSError:
            continue  # junk memory past the ends of the shelf
        # the same junk check table_records does
        if 0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000:
            cards.append(card)
    return cards
