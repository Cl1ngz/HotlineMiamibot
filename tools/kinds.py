# https://github.com/Cl1ngz/HotlineMiamibot
# kinds.py - list every kind of object on the floor (using the kind number of the first enemy rule)
# get a table of every kind of object
import time
from collections import defaultdict

from core.enemies import find_aim_card, find_me_card, is_enemy, load_rules
from core.memory import attach, read_kind, table_records, wait

rules = load_rules()
if not rules:
    raise SystemExit("no enemy rules yet - run python obj_kinds.py first")
where, offset, _ = rules[0]  # the spot where the first rule found the kind number

mem, regions, static_regions = attach()
you = find_me_card(mem)
aim = find_aim_card(mem)
if you is None or aim is None:
    raise SystemExit("can't find you or the crosshair - are you in a level? ")

wait("Stand still and DON'T touch the mouse - watching for 3 seconds", 5)
first = table_records(mem)
moving = set()
for _ in range(30):
    time.sleep(0.1)
    now = table_records(mem)
    moving |= {r for r in now if r in first and now[r] != first[r]}

kinds = defaultdict(list)
for record in now:
    try:
        kinds[read_kind(mem, record, where, offset)].append(record)
    except OSError:
        pass

print("      kind  objects  moving  enemies  where some of them are")
for value, records in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
    labels = []
    if you in records:
        labels.append("<- YOU")
    if aim in records:
        labels.append("<- CROSSHAIR")
    # & in both
    walking = len(set(records) & moving)

    # True counts as 1
    enemies = sum(is_enemy(mem, r, rules) for r in records)
    examples = " ".join(f"({now[r][0]:.0f},{now[r][1]:.0f})" for r in records[:3])
    print(
        f"{hex(value):>10} {len(records):8} {walking:7} {enemies:8}  {examples:36} {' '.join(labels)}"
    )

# runers = r,r,r,r
# thingg that move by
runners = [
    r
    for r in moving
    if r in now and r not in (you, aim) and not is_enemy(mem, r, rules)
]
if runners:
    print(
        f"\n{len(runners)} things move by themselves but aren't enemies yet - dogs? run:  python obj_kinds.py dogs"
    )
