# https://github.com/Cl1ngz/HotlineMiamibot
# telling enemies apart from walls, you and everything else
import math
import os
import time
from collections import defaultdict

from memory import (
    X_OFF,
    Y_OFF,
    load_address,
    read_double,
    read_kind,
    save_address,
    table_records,
)

# Size of one table record
# 4bytes (X at +0x50, Y at +0x58)
RECORD = 0xB8
INSTANCE = 0x6D0  # bytes in the bigger object behind the record's first pointer
MAX_ENEMIES = 40  # a floor never has more enemies of one kind than this


def find_me(mem):
    cards = table_records(mem)
    if not cards:
        return None
    found = []
    # 64 cards is jsut a guess resonable number to compute
    # thats why try exept is here cus fricking errors
    for card in range(min(cards) - 64 * RECORD, max(cards) + 64 * RECORD + 1, RECORD):
        try:
            if (
                read_kind(mem, card, 0, 0x14) == 0x2C
                and read_kind(mem, card, 1, 0x10) == 0x47
            ):
                found.append(
                    (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
                )
        except OSError:
            # empty space this card reserve probobly causes it
            continue
    # menu or loading
    if not found:
        return None
    if len(found) == 1:
        return found[0]

    # more that one you
    # closes to the crosshair is the real one i guess
    aims = []
    for card, xy in cards.items():
        try:
            if read_kind(mem, card, 0, 0x14) == 0xAF:
                aims.append(xy)
        except OSError:
            continue
    if not aims:
        return None
    return min(found, key=lambda me: min(math.dist(me, aim) for aim in aims))


# Crosshair card where it was last time checked
aim_last_xy = {}
# croshair card when last time moved
aim_last_move = {}


# card +0x14 = 0xAF  and  folder +0x10 = 0xA5
def find_aim(mem):
    cards = table_records(mem)
    if not cards:
        return None
    aims = {}
    for card in range(min(cards) - 64 * RECORD, max(cards) + 64 * RECORD + 1, RECORD):
        try:
            if (
                read_kind(mem, card, 0, 0x14) == 0xAF
                and read_kind(mem, card, 1, 0x10) == 0xA5
            ):
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
    return aims[best]


# [(kind rule, check), ...] - filled in by load_rules(), used by is_enemy()
alive_checks = []


# flat list addresses.json
# where offse value
def read_flat(name):
    try:
        return load_address(name)
    except (KeyError, ValueError, OSError):
        return []


def load_rules():
    global alive_checks

    # read the alive checks first, so is_enemy() can use them
    flat = read_flat("alive")
    alive_checks = []
    for i in range(0, len(flat) - 5, 6):
        kind = tuple(flat[i : i + 3])
        check = tuple(flat[i + 3 : i + 6])
        alive_checks.append((kind, check))

    # read the enemy rules
    flat = read_flat("enemy")
    rules = []
    for i in range(0, len(flat) - 2, 3):
        rules.append(tuple(flat[i : i + 3]))
    return rules


def save_rules(rules):
    save_address("enemy", [number for rule in rules for number in rule])


def save_alive_checks(checks):
    save_address("alive", [number for kind, check in checks for number in kind + check])


def matches(mem, record, where, offset, value):
    try:
        return read_kind(mem, record, where, offset) == value
    except OSError:
        return False


def is_enemy(mem, record, rules):
    for rule in rules:
        if matches(mem, record, *rule):
            return all(
                matches(mem, record, *check)
                for kind, check in alive_checks
                if kind == rule
            )
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


# Spots where an object first and second share a value that you and the walls don't.
# Returns guesses best first: [[where, offset, value, objects, walking], ...]
def find_rules(copies, first, second, you, movers):
    first = [r for r in first if r in copies]
    second = [r for r in second if r in copies]
    if not first or not second:
        raise SystemExit("couldn't read those objects (did they die?) - run again")

    guesses = []
    for where in range(2):
        for offset in range(0, len(copies[first[0]][where]), 4):
            # skip X and Y on the card - positions aren't kinds
            if where == 0 and X_OFF <= offset < X_OFF + 16:
                continue
            # group the objects by the 4 bytes they have here
            groups = defaultdict(set)
            for record, data in copies.items():
                groups[int.from_bytes(data[where][offset : offset + 4], "little")].add(
                    record
                )
            if len(groups) > 60:
                # different for almost every object: an id or a pointer, not a kind
                continue
                # the biggest group = walls
            walls = max(groups, key=lambda v: len(groups[v]))
            for value, group in groups.items():
                # filter out walls, you and too many enemies
                if value == walls or you in group or len(group) > MAX_ENEMIES:
                    continue
                # final test and save
                if group & set(first) and group & set(second):
                    guesses.append(
                        [
                            where,
                            offset,
                            value,
                            len(group),
                            len(group & movers),
                            frozenset(group),
                        ]
                    )

    # best first: holds the most walkers, then whole numbers (kinds are small), then the smallest group
    guesses.sort(key=lambda g: (-g[4], not 0 < g[2] < 10000, g[3]))
    # different spots that pick out exactly the same objects count as one guess
    seen = set()
    unique = []
    for g in guesses:
        if g[5] not in seen:
            seen.add(g[5])
            unique.append(g[:5])
    return unique
