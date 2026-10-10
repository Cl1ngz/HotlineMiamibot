# https://github.com/Cl1ngz/HotlineMiamibot
import json

from memory import attach, pointer_scan, take_snapshot

mem, regions, static_regions = attach()
x_addr = int(input("Your X address right now: "), 16)

heap = take_snapshot(mem, regions)
static = take_snapshot(mem, static_regions)
paths = pointer_scan(heap, static, x_addr)
print(len(paths), "pointer paths found")

with open("paths.json", "w") as f:
    json.dump(paths, f)
print("Saved restart the level,  run: check.py")
