# https://github.com/Cl1ngz/HotlineMiamibot
import math
import time

from enemies import find_aim, find_me
from memory import attach, read_double, read_kind, table_records

mem, regions, static_regions = attach()


# def find_me(mem):
#     found = []
#     for record, (x, y) in table_records(mem).items():
#         if read_kind(mem, record, 0, 0x14) == 0x2C:
#             found.append((x, y))
#     if len(found) == 1:
#         return found[0]
#     else:
#         return None
#
#
# def find_aim(mem):
#     found = []
#     for record, (x, y) in table_records(mem).items():
#         if read_kind(mem, record, 0, 0x14) == 0xAF:
#             found.append((x, y))
#     if len(found) == 0:
#         return None
#     if len(found) == 1 or me is None:
#         return found[0]
#     closest = min(found, key=lambda pos: math.dist(pos, me))
#     return closest


while True:
    cards = table_records(mem)
    if not cards:  # menu / ładowanie: spis pusty
        print("menu")
        time.sleep(0.5)
        continue
    lo, hi = min(cards), max(cards)  # pierwsza i ostatnia karta ze spisu
    found = []
    for card in range(
        lo - 64 * 0xB8, hi + 64 * 0xB8, 0xB8
    ):  # każde miejsce na półce, co 0xB8
        try:
            if ...:  # DZIURA: podpis gracza - oba warunki, tak jak w is_player
                found.append(
                    (
                        hex(card),
                        round(read_double(mem, card + 0x50)),
                        round(read_double(mem, card + 0x58)),
                    )
                )
        except OSError:
            continue
    print(found)
    time.sleep(0.5)
