# https://github.com/Cl1ngz/HotlineMiamibot
# tools/enemy_tool.py - everything about "who is an enemy", in one place (the rules live in addresses.json)
#
# A rule = (where, offset, value): where 0 = the card, 1 = its folder. Every rule also gets death signs
# ("dead" checks): a card that matches the rule AND a death sign is a body, not an enemy.
#
#   python -m tools.enemy_tool                 list the rules and their death signs
#   python -m tools.enemy_tool look            aim at a NEW enemy (alive): shows 3 possible rules for him
#   python -m tools.enemy_tool save N          save rule N from the last look (+ the usual death sign +0xB4 = 1)
#   python -m tools.enemy_tool remove N        remove rule N (and its death signs) - a rule that grabbed furniture
#   python -m tools.enemy_tool dead            aim at a BODY that still counts as an enemy: shows death signs
#   python -m tools.enemy_tool dead save N     save death sign N from the last dead look
#
# After every change check with python -m tools.radar: only enemies orange, no furniture, no bodies.
import json
import math
import sys
import time
from collections import Counter

import core.enemies
from core.enemies import (
    AIM_PICTURE,
    RECORD,
    copy_memory,
    find_aim,
    find_me_card,
    is_enemy,
    load_rules,
    save_dead_checks,
    save_rules,
)
from core.hands import LOOK_X, LOOK_Y, follow
from core.memory import (
    X_OFF,
    Y_OFF,
    attach,
    read_double,
    read_kind,
    table_records,
    wait,
)

LAST_FILE = "enemy_tool.json"  # the last look's guesses (so "save N" needs no aiming)
DEATH = (
    0,
    0xB4,
    1,
)  # the death sign every new rule gets: card +0xB4 = 1 (a body or a shell)
SKIP = (0x2C, 0xAF)  # layers of you and the crosshair
CLOSE = 20  # the thing must be this close to the crosshair
PARTNER = 4  # cards this close to him are his own pieces (shadow, legs, gun) - not "other things"
FIELDS = [(0, 0x14, "layer"), (0, 0x10, "+0x10"), (1, 0x10, "picture")]
WATCH = 8  # look this many times, 0.25 s apart: a number that changes while he moves is no good


def name(where, offset):
    """'layer' / '+0x10' / 'picture' for the spots we know, else 'card +0x..' / 'folder +0x..'."""
    for w, o, label in FIELDS:
        if (w, o) == (where, offset):
            return label
    if (where, offset) == (0, 0xB4):
        return "+0xB4"
    return f"{'card' if where == 0 else 'folder'} {offset:+#x}"


def show_rule(rule):
    where, offset, value = rule
    return f"{name(where, offset):12} = {value:#x}"


def save_last(mode, guesses, kind=None):
    with open(LAST_FILE, "w") as f:
        json.dump({"mode": mode, "guesses": guesses, "kind": kind}, f)


def load_last(mode):
    try:
        with open(LAST_FILE) as f:
            last = json.load(f)
    except OSError:
        raise SystemExit(f"no last look - run python -m tools.enemy_tool {mode} first")
    if last["mode"] != mode:
        raise SystemExit(
            f"the last look was '{last['mode']}', not '{mode}' - run '{mode}' again"
        )
    return last


def pick(guesses, word):
    try:
        number = int(word)
    except ValueError:
        raise SystemExit("give the number from the list, e.g. save 1")
    if not 0 <= number < len(guesses):
        raise SystemExit(f"pick 0 to {len(guesses) - 1}")
    return number


rules = load_rules()  # also loads the death signs into core.enemies.dead_checks
args = sys.argv[1:]

# --- list (no words) ---
if not args:
    print(f"{len(rules)} enemy rules:")
    for i, rule in enumerate(rules):
        print(f"  {i}  {show_rule(rule)}")
        for kind, check in core.enemies.dead_checks:
            if kind == rule:
                print(f"       dead when {show_rule(check)}")
    print("\nnew enemy: python -m tools.enemy_tool look")
    raise SystemExit

# --- save N / dead save N / remove N: no game needed ---
if args[0] == "save" and len(args) == 2:
    last = load_last("look")
    rule = tuple(last["guesses"][pick(last["guesses"], args[1])])
    if rule in rules:
        raise SystemExit(f"that rule is already saved: {show_rule(rule)}")
    rules.append(rule)
    save_rules(rules)
    checks = core.enemies.dead_checks
    checks.append((rule, DEATH))
    save_dead_checks(checks)
    print(
        f"saved rule {len(rules) - 1}: {show_rule(rule)}, dead when {show_rule(DEATH)}"
    )
    print("check it: python -m tools.radar - only enemies orange, no furniture")
    raise SystemExit

if args[:2] == ["dead", "save"] and len(args) == 3:
    last = load_last("dead")
    where, offset, _, body = last["guesses"][pick(last["guesses"], args[2])]
    kind = tuple(last["kind"])
    check = (where, offset, body)
    checks = core.enemies.dead_checks
    if (kind, check) in checks:
        raise SystemExit("that death sign is already saved")
    checks.append((kind, check))
    save_dead_checks(checks)
    print(f"saved: {show_rule(kind)} is dead when {show_rule(check)}")
    print(
        "check it: the body should stop being orange on the radar, the living enemies should stay orange"
    )
    raise SystemExit

if args[0] == "remove" and len(args) == 2:
    number = pick(rules, args[1])
    rule = rules.pop(number)
    save_rules(rules)
    save_dead_checks(
        [(kind, check) for kind, check in core.enemies.dead_checks if kind != rule]
    )
    print(
        f"removed rule {number}: {show_rule(rule)} (and its death signs). {len(rules)} rules left."
    )
    raise SystemExit

if args not in (["look"], ["dead"]):
    raise SystemExit(
        "usage: python -m tools.enemy_tool [look | save N | remove N | dead | dead save N]"
    )

# --- look / dead: aim at something in the game ---
mem, regions, static_regions = attach()
find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
what = (
    "the NEW enemy (alive)"
    if args[0] == "look"
    else "the BODY that still counts as an enemy"
)
wait(f"aim at {what} and keep the crosshair on it", 3)
aim = find_aim(mem)
if aim is None:
    # no crosshair card on this floor (outside, by the dumpster): the game's own "where the mouse is" is the same point
    aim = (read_double(mem, follow(mem, LOOK_X)), read_double(mem, follow(mem, LOOK_Y)))
me = find_me_card(mem)
table = table_records(mem)
if aim is None or not table:
    raise SystemExit("no crosshair / no table - are you in a level?")
wall_layer = Counter(read_kind(mem, card, 0, 0x14) for card in table).most_common(1)[0][
    0
]

# every card on the shelf at a real position (the table misses some live ones - you, enemies that come later)
cards = {}
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        xy = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
    except OSError:
        continue
    if 0.01 < abs(xy[0]) < 100000 and 0.01 < abs(xy[1]) < 100000:
        cards[card] = xy


def describe(card):
    """One line: where it is, its 3 numbers, the death sign, which rule makes it an enemy."""
    x, y = cards[card]
    try:
        layer, state, picture = (
            read_kind(mem, card, where, offset) for where, offset, _ in FIELDS
        )
        done = read_kind(mem, card, 0, 0xB4)
    except OSError:
        return f"  {card:#x} at ({x:4.0f},{y:4.0f})  can't read"
    rule = next((r for r in rules if core.enemies.matches(mem, card, *r)), None)
    enemy = "ENEMY" if is_enemy(mem, card, rules) else "no"
    how = f"rule {rules.index(rule)}" if rule else "no rule"
    return (
        f"  {card:#x} at ({x:4.0f},{y:4.0f})  layer {layer:#10x}  +0x10 {state:#6x}  picture {picture:#6x}"
        f"  +0xB4 {done}  {'table' if card in table else 'SHELF'}  enemy={enemy} ({how})"
    )


near = []
for card, xy in cards.items():
    try:
        layer = read_kind(mem, card, 0, 0x14)
        picture = read_kind(mem, card, 1, 0x10)
    except OSError:
        continue
    if picture == AIM_PICTURE:
        continue  # the crosshair itself, whatever its layer
    if (
        card != me
        and layer not in SKIP
        and layer != wall_layer
        and math.dist(xy, aim) < CLOSE
    ):
        near.append((math.dist(xy, aim), card in table, card))
if not near:
    raise SystemExit("nothing (but walls) under the crosshair - aim right at it")
print(
    f"crosshair at {aim[0]:.0f},{aim[1]:.0f} - everything close to it (closest first):"
)
for _, _, card in sorted(near):
    print(describe(card))

if args[0] == "look":
    # the closest one; a card from the table wins a tie (the real thing, not a drawn copy)
    him = min(near, key=lambda n: (round(n[0]), not n[1]))[2]
    if is_enemy(mem, him, rules):
        raise SystemExit(
            f"\nthe closest one, {him:#x}, is already an enemy - nothing to add."
            "\n(SHELF enemies show on the radar only with the shelf fix in tools/radar.py)"
        )
    seen = [set() for _ in FIELDS]
    for _ in range(WATCH):
        for i, (where, offset, _) in enumerate(FIELDS):
            try:
                seen[i].add(read_kind(mem, him, where, offset))
            except OSError:
                pass
        time.sleep(0.25)
    print(f"\n{him:#x} - possible rules:")
    print("  #  rule                    stays the same?   other things with it")
    guesses = []
    for i, (where, offset, label) in enumerate(FIELDS):
        if not seen[i]:
            continue
        value = min(seen[i])
        others = 0
        for card, xy in cards.items():
            if card == him or math.dist(xy, cards[him]) < PARTNER:
                continue
            others += core.enemies.matches(mem, card, where, offset, value)
        stays = (
            "yes"
            if len(seen[i]) == 1
            else f"NO ({', '.join(hex(v) for v in sorted(seen[i]))})"
        )
        good = "   <- good" if len(seen[i]) == 1 and others == 0 else ""
        print(
            f"  {len(guesses)}  {label:8} = {value:#10x}   {stays:16}  {others}{good}"
        )
        guesses.append([where, offset, value])
    save_last("look", guesses)
    print(
        "\n(more enemies of the same new kind on the floor count as 'others' too - that's fine)"
    )
    print("save the good one: python -m tools.enemy_tool save N")
    raise SystemExit

# --- dead: a body that is still orange ---
bodies = [card for _, _, card in sorted(near) if is_enemy(mem, card, rules)]
if not bodies:
    raise SystemExit(
        "\nnothing under the crosshair counts as an enemy - this body is fine already"
    )
body = bodies[0]
kind = next(
    rule for rule in rules if core.enemies.matches(mem, body, *rule)
)  # the rule that made it orange
living = [
    c
    for c in cards
    if c != body and core.enemies.matches(mem, c, *kind) and is_enemy(mem, c, rules)
]
if len(living) < 2:
    raise SystemExit(
        "\nneed at least 2 LIVING enemies of that kind on the floor to compare the body with"
    )
print(
    f"\ncomparing the body {body:#x} with {len(living)} living enemies of rule {rules.index(kind)} for 2 s..."
)
agree = None  # {(where, offset, value every living enemy has): the body's value}
for _ in range(WATCH):  # a number that changes while they walk around is no good
    copies = copy_memory(mem, [body] + living)
    if body not in copies:
        raise SystemExit("lost the body - try again")
    found = {}
    for where in (0, 1):
        for offset in range(0, len(copies[body][where]), 4):
            theirs = {
                int.from_bytes(d[where][offset : offset + 4], "little")
                for c, d in copies.items()
                if c != body
            }
            mine = int.from_bytes(copies[body][where][offset : offset + 4], "little")
            if (
                len(theirs) == 1 and mine not in theirs
            ):  # all the living agree, the body doesn't
                found[(where, offset, theirs.pop())] = mine
    agree = (
        found
        if agree is None
        else {k: v for k, v in found.items() if k in agree and agree[k] == v}
    )
    time.sleep(0.25)
guesses = [
    [where, offset, value, mine] for (where, offset, value), mine in agree.items()
]
guesses.sort(
    key=lambda g: (not (0 <= g[2] < 10000 and 0 <= g[3] < 10000), g[0], g[1])
)  # small numbers first
if not guesses:
    raise SystemExit(
        "nothing sets the body apart from the living - are you sure it's dead?"
    )
print("  #  spot             living have    body has")
for i, (where, offset, value, mine) in enumerate(guesses[:15]):
    print(f"  {i:2} {name(where, offset):14} {value:#12x} {mine:#11x}")
save_last("dead", guesses[:15], list(kind))
print(
    "\nsave the best one (small numbers are usually it): python -m tools.enemy_tool dead save N"
)
