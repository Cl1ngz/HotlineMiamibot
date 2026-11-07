# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/shelf_check.py - did the speed-up change any answer? The old way (mem) vs the new way (a Shelf)
# Only READS memory. Stand in a level - or use a saved dump, then the game doesn't even have to run.
#
#   python -m helpers_for_me.shelf_check                         on the running game
#   python -m helpers_for_me.shelf_check --dump see_dump.npz     on a dump from see_timer --dump
#
# For every finder:  OK (the same answer both ways)  /  DIFFERENT (+ both answers)  /  TODO n not done yet.
# Then a whole worst frame (scan + walls) both ways: ms and kernel reads (os.pread calls).
# Run it at different moments: weapons on the floor, the briefcase, GO! on, the car ready - every finder gets checked.
import os
import sys
import time

import numpy as np

from core.enemies import find_me_card, is_enemy, load_rules, shelf_cards
from core.memory import attach, table_records
from core.shelf import PAGE, Shelf
from core.stairs import find_car, find_stairs
from core.walls import fake_door_boxes, find_walls, real_walls, wall_boxes
from core.weapons import find_goals, find_weapons

RUNS = 20

# count every kernel read - and with --dump, answer them from the dump instead of the game
calls = 0
real_pread = os.pread
dump = None  # {page address: 4096 bytes} with --dump


def counting_pread(fd, size, address):
    global calls
    calls += 1
    if dump is None:
        return real_pread(fd, size, address)
    data = b""
    while size > 0:
        start = address - address % PAGE
        if start not in dump:
            if data:
                return data
            raise OSError(5, "Input/output error")
        take = min(size, start + PAGE - address)
        data += dump[start][address - start : address - start + take]
        address, size = address + take, size - take
    return data


os.pread = counting_pread

if "--dump" in sys.argv:
    saved = np.load(sys.argv[sys.argv.index("--dump") + 1])
    data = saved["data"].tobytes()
    dump = {int(s): data[i * PAGE : (i + 1) * PAGE] for i, s in enumerate(saved["starts"].tolist())}
    mem = 0  # no game: every read comes from the dump
    print(f"the dump: {len(dump)} pages")
else:
    mem, regions, static_regions = attach()
rules = load_rules()


def same(a, b):
    """The same answer? (lists and sets in any order)"""
    if isinstance(a, (list, set)) and isinstance(b, (list, set)):
        return sorted(map(repr, a)) == sorted(map(repr, b))
    return repr(a) == repr(b)


def short(value):
    text = repr(sorted(value, key=repr) if isinstance(value, (list, set)) else value)
    return text if len(text) < 90 else text[:87] + "..."


# --- every finder, both ways ---
# (name, the TODO that makes the new way work, the old way, the new way)
records = table_records(mem)
shelf = Shelf(mem)
checks = [
    ("find_me_card", "", lambda: find_me_card(mem), lambda: find_me_card(shelf)),
    ("enemies", "", lambda: {c for c in shelf_cards(mem, records) if is_enemy(mem, c, rules)},
     lambda: {c for c in shelf.cards if is_enemy(shelf, c, rules)}),
    ("walls: positions", "4a", lambda: find_walls(mem, records),
     lambda: [xy for xy, box in real_walls(shelf, shelf.records, shelf.cards)]),
    ("walls: boxes", "4a", lambda: wall_boxes(mem, records),
     lambda: [box for xy, box in real_walls(shelf, shelf.records, shelf.cards)]),
    ("fake doors", "", lambda: fake_door_boxes(mem, records), lambda: fake_door_boxes(shelf, shelf.records)),
    ("stairs", "", lambda: find_stairs(mem, records), lambda: find_stairs(shelf, shelf.records)),
    ("car", "2", lambda: find_car(mem, records), lambda: find_car(shelf, shelf.records, shelf.cards)),
    ("weapons", "1", lambda: find_weapons(mem), lambda: find_weapons(shelf, shelf.cards)),
    ("goals", "1", lambda: find_goals(mem), lambda: find_goals(shelf, shelf.cards)),
]
print(f"table {len(records)} cards, shelf {len(shelf.cards)} cards\n")
ok = True
for name, todo, old_way, new_way in checks:
    try:
        old = old_way()
    except Exception as err:  # the tools call it like this - it must keep working
        print(f"  {name:18} the OLD way is broken now (the tools call it like that!): {err!r}")
        ok = False
        continue
    try:
        new = new_way()
    except TypeError as err:
        print(f"  {name:18} TODO {todo} not done yet  ({err})")
        ok = False
        continue
    if same(old, new):
        print(f"  {name:18} OK         {short(old)}")
    else:
        print(f"  {name:18} DIFFERENT\n      old: {short(old)}\n      new: {short(new)}")
        ok = False


# --- a whole worst frame (scan + walls), both ways ---
def old_frame():
    recs = table_records(mem)
    find_me_card(mem)
    {c for c in shelf_cards(mem, recs) if is_enemy(mem, c, rules)}
    find_walls(mem, recs), wall_boxes(mem, recs), fake_door_boxes(mem, recs)
    find_stairs(mem, recs), find_car(mem, recs), find_weapons(mem), find_goals(mem)


def new_frame():
    photo = Shelf(mem)  # a NEW photo, like every frame in hmbot
    recs, cards = photo.records, photo.cards
    find_me_card(photo)
    {c for c in cards if is_enemy(photo, c, rules)}
    real_walls(photo, recs, cards), fake_door_boxes(photo, recs)
    find_stairs(photo, recs), find_car(photo, recs, cards), find_weapons(photo, cards), find_goals(photo, cards)


def measure(job):
    global calls
    calls = 0
    start = time.perf_counter()
    for _ in range(RUNS):
        job()
    return (time.perf_counter() - start) * 1000 / RUNS, calls // RUNS


print("\nA WORST FRAME (scan + walls)")
old_ms, old_reads = measure(old_frame)
print(f"  old way: {old_ms:6.2f} ms  {old_reads:6} kernel reads")
if ok:
    new_ms, new_reads = measure(new_frame)
    print(f"  new way: {new_ms:6.2f} ms  {new_reads:6} kernel reads   ({old_ms / new_ms:.1f}x faster)")
else:
    print("  new way: finish the TODOs first (and every finder OK)")
