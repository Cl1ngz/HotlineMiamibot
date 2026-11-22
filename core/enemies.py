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
RECORD = 0xB8
INSTANCE = 0x6D0  # bytes in the bigger object behind the record's first pointer
AIM_PICTURE = 0xA5  # the crosshair's picture (folder +0x10) - always the same; its layer is NOT (0xAF, outside by the dumpster 0x1)

# 64 cards around the table: a guess, big enough so far (helpers_for_me/far_cards.py checks it)
AROUND = 64


def shelf_range(cards):
    """every card spot on the shelf: AROUND cards before the table's first card to AROUND after its last"""
    return range(min(cards) - AROUND * RECORD, max(cards) + AROUND * RECORD + 1, RECORD)


# where you were the last time find_me_card found you: picks the right card when several look like you
me_last_xy = None


def find_me_card(mem):
    """Your card (layer 0x2C, picture 0x47), or None: the menu, loading, sitting on an enemy.
    Several cards can look like you (a leftover from the floor you just left): the empty ones (card +0x4 = 0,
    like the ghost enemies) go first, then the one closest to the crosshair - or, with no crosshair, to where
    you were last time. With at least one card that looks like you, the answer is never None."""
    global me_last_xy
    cards = table_records(mem)
    if not cards:
        return None
    found = {}
    for card in shelf_range(cards):
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
    if not found:
        return None
    if len(found) > 1:
        # a leftover copy is empty inside, like the ghost enemies (only if that leaves somebody)
        alive = {
            card: xy for card, xy in found.items() if read_kind(mem, card, 0, 0x4) != 0
        }
        found = alive or found
    if len(found) == 1:
        me = next(iter(found))
    else:
        # still several: the one closest to the crosshair (known by its picture - its layer changes per floor),
        # with no crosshair the one closest to where you were last time
        aim = find_aim_card(mem)
        if aim is not None:
            point = (read_double(mem, aim + X_OFF), read_double(mem, aim + Y_OFF))
        else:
            point = me_last_xy
        if point is None:
            me = next(iter(found))
        else:
            me = min(found, key=lambda card: math.dist(found[card], point))
    me_last_xy = found[me]
    return me


# Crosshair card where it was last time checked
aim_last_xy = {}
# croshair card when last time moved
aim_last_move = {}


# folder +0x10 = 0xA5
def find_aim_card(mem):
    cards = table_records(mem)
    if not cards:
        return None
    aims = {}
    for card in shelf_range(cards):
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
    for card in shelf_range(records):
        try:
            x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        except OSError:
            continue  # junk memory past the ends of the shelf
        # the same junk check table_records does
        if 0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000:
            cards.append(card)
    return cards
