# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/rebuild/table_rebuild.py - rebuild "which cards does the table point to?" and test it on the live game
#
#   python -m helpers_for_me.rebuild.table_rebuild        (be in a level)
#
import os
import time

import numpy as np

from core import memory

TABLE_START = 0xBEB900
TABLE_END = 0xBED900


def read_u32(mem, address):
    return int.from_bytes(os.pread(mem, 4, address), "little")


def cards_in_table(mem):
    """Every card address the table points to right now (empty slots skipped)."""
    # a set is like a list, but it never holds the same thing twice and "is X in it?" is very fast
    # cards = set()
    # for slot in range(0, TABLE_END - TABLE_START, 4):
    #     card = read_u32(mem, TABLE_START + slot)
    #     if card != 0:
    #         cards.add(card)
    data = os.pread(mem, TABLE_END - TABLE_START, TABLE_START)
    cards = set(np.frombuffer(data, dtype="<u4").tolist())
    return cards - {0}


mem, regions, static_regions = memory.attach()

start = time.perf_counter()
mine = cards_in_table(mem)
my_time = time.perf_counter() - start

start = time.perf_counter()
real = memory.table_cards(mem) - {
    0
}  # the real one keeps the empty slot (0) in the set - drop it to compare
real_time = time.perf_counter() - start

print(f"yours: {len(mine)} cards in {my_time * 1000:.2f} ms")
print(f"real:  {len(real)} cards in {real_time * 1000:.2f} ms")
if mine == real:
    print("OK   same cards")
else:
    print("FAIL different cards")
    print(f"  only in yours: {[hex(card) for card in sorted(mine - real)]}")
    print(f"  only in real:  {[hex(card) for card in sorted(real - mine)]}")
    print(
        "  (just one or two? the game may have changed between the two reads - run it again)"
    )
