# https://github.com/Cl1ngz/HotlineMiamibot
# telling enemies apart from walls, you and everything else
import math
import os
from collections import defaultdict

from memory import X_OFF, load_address, read_kind, save_address, table_records

RECORD = 0xB8  # bytes in a table record (X at +0x50, Y at +0x58)
INSTANCE = 0x6D0  # bytes in the bigger object behind the record's first pointer
MAX_ENEMIES = 40  # a floor never has more enemies of one kind than this


def find_me(mem):
    found = []
    for record, (x, y) in table_records(mem).items():
        if read_kind(mem, record, 0, 0x14) == 0x2C:
            found.append((x, y))
    if len(found) == 1:
        return found[0]
    else:
        return None


def find_aim(mem, me):
    found = []
    for record, (x, y) in table_records(mem).items():
        if read_kind(mem, record, 0, 0x14) == 0xAF:
            found.append((x, y))
    if len(found) == 0:
        return None
    if len(found) == 1 or me is None:
        return found[0]
    closest = min(found, key=lambda pos: math.dist(pos, me))
    return closest


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
