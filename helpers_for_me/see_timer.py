# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/see_timer.py - which piece of see() eats the time? Measure before speeding anything up.
# Only READS memory (the bot can be off). Stand in a level - floor 1 with enemies alive is the best test.
#
#   python -m helpers_for_me.see_timer          the table of times
#   python -m helpers_for_me.see_timer --dump   the same + save the memory around the shelf to see_dump.npz
#                                               (send it to Claude: then the speed-up can be tested on REAL memory)
#
# For every piece: ms per call (avg / max over RUNS calls) and how many os.pread calls it made (= syscalls).
import json
import os
import sys
import time

import numpy as np

from core import lockon
from core.enemies import (
    INSTANCE,
    RECORD,
    find_me_card,
    is_enemy,
    load_rules,
    shelf_cards,
)
from core.memory import (
    TABLE_END,
    TABLE_START,
    X_OFF,
    Y_OFF,
    attach,
    read_double,
    read_u32,
    table_cards,
    table_records,
)
from core.path import blocked_cells
from core.stairs import find_car, find_stairs
from core.walls import fake_door_boxes, find_walls, wall_boxes, wall_lines
from core.weapons import find_goals, find_weapons

RUNS = 20
PAGE = 0x1000  # memory comes in 4 KB pages
CHUNK = 0x10000  # for the "one big read" test: 64 KB at a time

# count every os.pread (core/memory.py calls os.pread for every single read)
calls = 0
real_pread = os.pread


def counting_pread(fd, size, address):
    global calls
    calls += 1
    return real_pread(fd, size, address)


os.pread = counting_pread


def measure(job):
    """Run job RUNS times -> (avg ms, max ms, preads per call, the last result)."""
    global calls
    calls = 0
    times = []
    result = None
    for _ in range(RUNS):
        start = time.perf_counter()
        result = job()
        times.append((time.perf_counter() - start) * 1000)
    return sum(times) / RUNS, max(times), calls // RUNS, result


def show(group, pieces):
    """Print one group of pieces, return the sum of their avg ms."""
    print(f"\n{group}")
    total = 0
    for name, job in pieces:
        avg, worst, preads, result = measure(job)
        total += avg
        if result is None:
            size = "none"
        elif isinstance(result, (tuple, int)):
            size = "found"
        else:
            size = f"{len(result)} found"
        print(f"  {name:28} {avg:7.2f} ms  (max {worst:6.2f})  {preads:6} preads  {size}")
    print(f"  {'= together':28} {total:7.2f} ms")
    return total


def big_read_test(mem, start, size):
    """Can the whole shelf be read in a few big reads instead of thousands of small ones?"""
    t = time.perf_counter()
    got, failed = 0, 0
    for at in range(start, start + size, CHUNK):
        try:
            got += len(real_pread(mem, min(CHUNK, start + size - at), at))
        except OSError:
            failed += 1
    ms = (time.perf_counter() - t) * 1000
    print(f"  the whole shelf in 64 KB reads: {ms:.2f} ms, {got} of {size} bytes, {failed} chunks failed")
    t = time.perf_counter()
    for _ in range(1000):
        try:
            real_pread(mem, 8, start + 64 * RECORD + X_OFF)
        except OSError:
            pass
    us = (time.perf_counter() - t) * 1e6 / 1000
    print(f"  one small read (8 bytes):       {us:.1f} us average (1000 tries)")


def read_pages(mem, start, end, pages):
    """Every readable 4 KB page between start and end -> pages {page address: bytes}."""
    for at in range(start - start % PAGE, end, PAGE):
        if at in pages:
            continue
        try:
            data = real_pread(mem, PAGE, at)
        except OSError:
            continue
        if len(data) == PAGE:
            pages[at] = data


def dump(mem, records, rules):
    """Save the table, the shelf and the folders of its cards to see_dump.npz."""
    pages = {}
    read_pages(mem, TABLE_START, TABLE_END, pages)
    low, high = min(records) - 64 * RECORD, max(records) + 65 * RECORD
    read_pages(mem, low, high, pages)
    folders = 0
    for card in shelf_cards(mem, records):
        try:
            folder = read_u32(mem, card)
        except OSError:
            continue
        read_pages(mem, folder, folder + INSTANCE, pages)
        folders += 1
    starts = sorted(pages)
    np.savez_compressed(
        "see_dump.npz",
        starts=np.array(starts, dtype=np.uint64),
        data=np.frombuffer(b"".join(pages[s] for s in starts), dtype=np.uint8),
        rules=np.array(json.dumps(rules)),
    )
    size = os.path.getsize("see_dump.npz") / 1e6
    print(f"\nsaved see_dump.npz: {len(pages)} pages, {folders} folders, {size:.1f} MB")


mem, regions, static_regions = attach()
rules = load_rules()
records = table_records(mem)
if not records:
    raise SystemExit("the table is empty - stand in a level first")
me = find_me_card(mem)
if me is None:
    raise SystemExit("no player found - stand in a level (not the menu, not on the stairs)")
you = (read_double(mem, me + X_OFF), read_double(mem, me + Y_OFF))
shelf = shelf_cards(mem, records)
enemies = [card for card in shelf if is_enemy(mem, card, rules)]
lines = wall_lines(find_walls(mem, records, rules))
boxes = wall_boxes(mem, records, rules) + fake_door_boxes(mem, records)

slots = (max(records) - min(records)) // RECORD + 129
print(f"table: {len(records)} cards | shelf: {slots} slots, {len(shelf)} at a real position | "
      f"{len(enemies)} enemies | {len(boxes)} boxes")

frame = show("EVERY FRAME (60x a second)", [
    ("table_cards", lambda: table_cards(mem)),
    ("find_me_card", lambda: find_me_card(mem)),
    ("still enemies (is_enemy)", lambda: [c for c in enemies if is_enemy(mem, c, rules)]),
    ("visible_enemies", lambda: lockon.visible_enemies(mem, enemies, set(enemies), you, lines)),
])
scan = show("EVERY SCAN (4x a second)", [
    ("table_records", lambda: table_records(mem)),
    ("shelf_cards", lambda: shelf_cards(mem, records)),
    ("enemies (shelf + is_enemy)", lambda: {c for c in shelf_cards(mem, records) if is_enemy(mem, c, rules)}),
    ("find_stairs", lambda: find_stairs(mem, records)),
    ("find_car", lambda: find_car(mem, records)),
    ("find_weapons", lambda: find_weapons(mem)),
    ("find_goals", lambda: find_goals(mem)),
])
walls = show("EVERY 2 SECONDS (walls)", [
    ("find_walls + wall_lines", lambda: wall_lines(find_walls(mem, records, rules))),
    ("wall_boxes", lambda: wall_boxes(mem, records, rules)),
    ("fake_door_boxes", lambda: fake_door_boxes(mem, records)),
    ("blocked_cells", lambda: blocked_cells(boxes)),
])
print("\nSUM")
print(f"  a normal frame:                 {frame:7.2f} ms   (one frame lasts {1000 / 60:.1f} ms)")
print(f"  a frame with a scan:            {frame + scan:7.2f} ms")
print(f"  a frame with a scan + walls:    {frame + scan + walls:7.2f} ms")
print(f"  out of every second:            {frame * 60 + scan * 4 + walls / 2:7.0f} ms spent reading")

print("\nCAN IT BE FASTER?")
big_read_test(mem, min(records) - 64 * RECORD, slots * RECORD)

if "--dump" in sys.argv:
    dump(mem, records, rules)
