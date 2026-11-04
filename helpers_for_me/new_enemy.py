# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/new_enemy.py - teach the bot ONE new kind of enemy (like the green guy), the way we did it by hand
#
# Aim at the new enemy while he's ALIVE. This shows 3 possible rules for him:
#   layer (card +0x14), +0x10 (card +0x10), picture (folder +0x10)
# and for each one: does it stay the same while he moves, and how many OTHER things on the floor have it too.
# A good rule stays the same and nothing else has it (0 others) - otherwise the bot beats up the furniture.
# Then "save N" adds rule N to addresses.json, with the usual death sign (+0xB4 = 1).
#
#   python -m helpers_for_me.new_enemy          aim at him (3 s), then it watches him for 2 s
#   python -m helpers_for_me.new_enemy save 1   save rule #1 from the last look (no aiming needed)
import json
import math
import sys
import time
from collections import Counter

import core.enemies
from core.enemies import RECORD, find_aim, find_me_card, is_enemy, load_rules, save_dead_checks, save_rules
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records, wait

LAST_FILE = "new_enemy.json"
DEAD = (0, 0xB4, 1)  # the death sign every enemy rule gets
SKIP = (0x2C, 0xAF)  # you, the crosshair
CLOSE = 20  # the enemy must be this close to the crosshair
PARTNER = 4  # cards this close to him are his own pieces (shadow, legs, gun) - not "other things"
FIELDS = [(0, 0x14, "layer"), (0, 0x10, "+0x10"), (1, 0x10, "picture")]

rules = load_rules()  # also loads the dead checks into core.enemies.dead_checks

if len(sys.argv) > 2 and sys.argv[1] == "save":
    try:
        with open(LAST_FILE) as f:
            candidates = json.load(f)
    except OSError:
        raise SystemExit("no last look - run python -m helpers_for_me.new_enemy first")
    pick = int(sys.argv[2])
    if not 0 <= pick < len(candidates):
        raise SystemExit(f"pick 0 to {len(candidates) - 1}")
    rule = tuple(candidates[pick])
    if rule in rules:
        raise SystemExit(f"that rule is already saved: {rule}")
    rules.append(rule)
    save_rules(rules)
    checks = core.enemies.dead_checks
    checks.append((rule, DEAD))
    save_dead_checks(checks)
    where, offset, value = rule
    print(f"saved: ({where}, {offset:#x}, {value:#x}) + death sign +0xB4 = 1.  {len(rules)} rules now.")
    print("check it: python -m tools.radar - only the new enemy should turn orange, no furniture")
    raise SystemExit

mem, regions, static_regions = attach()
find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("aim at the NEW enemy (alive) and keep the crosshair on him", 3)
aim = find_aim(mem)
me = find_me_card(mem)
table = table_records(mem)
if aim is None or not table:
    raise SystemExit("no crosshair / no table - are you in a level?")
wall_layer = Counter(read_kind(mem, card, 0, 0x14) for card in table).most_common(1)[0][0]


def shelf():
    """{card: (x, y)} of every card on the shelf that stands at a real position."""
    cards = {}
    for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
        try:
            xy = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        except OSError:
            continue
        if 0.01 < abs(xy[0]) < 100000 and 0.01 < abs(xy[1]) < 100000:
            cards[card] = xy
    return cards


cards = shelf()
near = []
for card, xy in cards.items():
    try:
        layer = read_kind(mem, card, 0, 0x14)
    except OSError:
        continue
    if card != me and layer not in SKIP and layer != wall_layer and math.dist(xy, aim) < CLOSE:
        near.append((math.dist(xy, aim), card in table, card))
if not near:
    raise SystemExit("nothing (but walls) under the crosshair - aim right at him")


def describe(card):
    """One line: where it is, its 3 numbers, the death sign, which rule makes it an enemy."""
    x, y = cards[card]
    try:
        layer, state, picture = (read_kind(mem, card, where, offset) for where, offset, _ in FIELDS)
        done = read_kind(mem, card, 0, 0xB4)
    except OSError:
        return f"  {card:#x} at ({x:4.0f},{y:4.0f})  can't read"
    rule = next((r for r in rules if read_kind(mem, card, *r[:2]) == r[2]), None)
    enemy = "ENEMY" if is_enemy(mem, card, rules) else "no"
    how = f"rule ({rule[0]}, {rule[1]:#x}, {rule[2]:#x})" if rule else "no rule"
    return (
        f"  {card:#x} at ({x:4.0f},{y:4.0f})  layer {layer:#10x}  +0x10 {state:#6x}  picture {picture:#6x}"
        f"  +0xB4 {done}  {'table' if card in table else 'SHELF'}  enemy={enemy} ({how})"
    )


print(f"crosshair at {aim[0]:.0f},{aim[1]:.0f} - everything close to it (closest first):")
for _, _, card in sorted(near):
    print(describe(card))
# the closest one; a card from the table wins a tie (the real thing, not a drawn copy)
him = min(near, key=lambda n: (round(n[0]), not n[1]))[2]
if is_enemy(mem, him, rules):
    raise SystemExit(
        f"\nthe closest one, {him:#x}, is already an enemy - nothing to add."
        "\n(SHELF enemies are never on the radar - it only draws the table. hmbot does see them.)"
    )

# watch him for 2 s: a rule that changes while he moves is no good
values = [set() for _ in FIELDS]
for _ in range(8):
    for i, (where, offset, _) in enumerate(FIELDS):
        try:
            values[i].add(read_kind(mem, him, where, offset))
        except OSError:
            pass
    time.sleep(0.25)

xy = cards[him]
print(f"\n{him:#x} at ({xy[0]:.0f}, {xy[1]:.0f}) {'in table' if him in table else 'NOT in table'}:")
print("  #  rule             value   stays the same?   other things with it")
candidates = []
for i, (where, offset, name) in enumerate(FIELDS):
    seen = values[i]
    if not seen:
        continue
    value = min(seen)
    others = 0
    for card, other_xy in cards.items():
        if card == him or math.dist(other_xy, xy) < PARTNER:
            continue
        try:
            others += read_kind(mem, card, where, offset) == value
        except OSError:
            continue
    stays = "yes" if len(seen) == 1 else f"NO ({', '.join(hex(v) for v in sorted(seen))})"
    good = "   <- good" if len(seen) == 1 and others == 0 else ""
    print(f"  {len(candidates)}  {name:8} {where} {offset:#5x}  {value:#8x}   {stays:16}  {others}{good}")
    candidates.append((where, offset, value))
with open(LAST_FILE, "w") as f:
    json.dump(candidates, f)
print("\nsave the good one: python -m helpers_for_me.new_enemy save N")
