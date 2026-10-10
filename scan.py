# https://github.com/Cl1ngz/HotlineMiamibot
import json
import math
from collections import Counter

from memory import attach, first_scan, narrow, pointer_scan, read_double, take_snapshot

mem, regions, static_regions = attach()

# x
candidates = first_scan(mem, regions, "Walk RIGHT, then press Enter...")
print(len(candidates), "after first scan")

for r in range(2):
    input("Walk LEFT, then press Enter...")
    candidates = narrow(mem, candidates, "down")
    input("Walk RIGHT, then press Enter...")
    candidates = narrow(mem, candidates, "up")
    input("Stand STILL, then press Enter...")
    candidates = narrow(mem, candidates, "same")
    input("Move the MOUSE around (DON'T walk), then press Enter...")
    candidates = narrow(mem, candidates, "same")
    print(f"round {r + 1}: {len(candidates)} left")

for a, v in candidates.items():
    print(hex(a), round(v, 1))


# y
def safe_read(address):
    try:
        return read_double(mem, address)
    except OSError:
        return math.nan


def nearby(x_addr):
    # look in range(-64, 72, 8)
    return {off: safe_read(x_addr + off) for off in range(-0x40, 0x48, 8)}


start = {a: nearby(a) for a in candidates}
input("Walk DOWN (no left/right), then press Enter...")
down = {a: nearby(a) for a in candidates}
input("Walk UP (no left/right), then press Enter...")
up = {a: nearby(a) for a in candidates}


counts = Counter(round(v, 1) for v in candidates.values())
# the value with the most copies
player_value = counts.most_common(1)[0][0]
print(f"Your X should be {player_value} (it has the most copies)")
best = None
for a in sorted(candidates):
    if round(candidates[a], 1) != player_value:
        # not in the biggest group -> not you
        continue
    for off in start[a]:
        if a + off in candidates:
            # that's another X copy, not a Y
            continue
        moved_down = down[a][off] - start[a][off]
        moved_up = up[a][off] - down[a][off]
        if abs(moved_down) > 5 and abs(moved_up) > 5 and moved_down * moved_up < 0:
            # it moved one way, then back the other way = Y!
            best, y_offset = a, off
            break
    if best is not None:
        break

if best is None:
    print("\n!!! memory plays hide and seek gl.")
    raise SystemExit

print(f"\n>>> FOUND YOU: X at {hex(best)}, Y at {hex(best + y_offset)}")
print("\n! Put this line in hmbot.py:")
print(f">>> Y_OFFSET = {hex(y_offset)}")

#  find the game's note that says where you
# print(">>> Looking for pointer paths to you...")
paths = pointer_scan(
    take_snapshot(mem, regions), take_snapshot(mem, static_regions), best
)
print(f">>> {len(paths)} pointer paths found")
with open("paths.json", "w") as f:
    json.dump(paths, f)

if paths:
    print(">>> NEXT: restart the level and run: python check.py")
else:
    print("!!! 0 paths. GG i so done idk jump out of a windo or something")
