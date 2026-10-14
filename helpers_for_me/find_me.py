import math
import time

from enemies import find_aim, find_me
from memory import attach, read_kind, table_records

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
# def find_aim(mem, me):
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
    objects = table_records(mem)
    ile_mnie = 0
    ile_celownikow = 0
    for record, (x, y) in objects.items():
        try:
            if read_kind(mem, record, 1, 0x10) == 0x47:
                plus_18 = read_kind(mem, record, 1, 0x18)
                plus_80 = read_kind(mem, record, 1, 0x80)
                print(
                    "  0x47:",
                    hex(record),
                    "na",
                    round(x),
                    round(y),
                    "  +0x18:",
                    hex(plus_18),
                    "  +0x80:",
                    hex(plus_80),
                )
        except OSError:
            continue
    print("---")
    # time.sleep(0.5)
    # print("obiektów:", len(objects), "  ja:", ile_mnie, "  celowników:", ile_celownikow)
    # time.sleep(0.5)
