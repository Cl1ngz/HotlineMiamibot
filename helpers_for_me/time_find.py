# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/time_find.py - how long does each "look around" in hmbot take?
#
# One game frame is 16.7 ms (60 FPS). If one loop of hmbot takes longer, the game runs a frame
# without our look_at - and puts the mouse back into the look (the flicker in blackbox_3).
# This times the suspects, each 50 times, and prints the average.
#
#   python -m helpers_for_me.time_find      (be in a level; best: once on a fresh floor, once after a fight)
import time

from core.enemies import find_aim, find_me, find_me_card
from core.memory import attach, read_kind, table_cards, table_records

TIMES = 50
FRAME = 1000 / 60  # ms

mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")


def timed(name, job):
    """Run job TIMES times, print the average in ms. Returns it."""
    start = time.perf_counter()
    for _ in range(TIMES):
        job()
    ms = (time.perf_counter() - start) / TIMES * 1000
    print(f"{name:32} {ms:7.2f} ms   ({ms / FRAME * 100:4.0f}% of a frame)")
    return ms


print(f"one game frame = {FRAME:.1f} ms, objects in the table right now: {len(table_records(mem))}\n")
timed("table_cards", lambda: table_cards(mem))
timed("table_records", lambda: table_records(mem))
me = timed("find_me", lambda: find_me(mem))
aim = timed("find_aim", lambda: find_aim(mem))
check = timed("is it still my card? (2 reads)", lambda: (read_kind(mem, card, 0, 0x14), read_kind(mem, card, 1, 0x10)))
print(f"\nfind_me + find_aim every frame: {me + aim:.2f} ms")
print(f"checking a remembered card instead: {check:.3f} ms  (~{(me + aim) / check:.0f}x less)")
