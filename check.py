# https://github.com/Cl1ngz/HotlineMiamibot
import json
import os
import sys

from memory import attach, follow, read_double, wait

filename = sys.argv[1] if len(sys.argv) > 1 else "paths.json"
if not os.path.exists(filename):
    raise SystemExit(f"No {filename} yet run scan.py")

mem, regions, static_regions = attach()
with open(filename) as f:
    paths = json.load(f)
print(len(paths), "paths to check")


def read_x(path):
    try:
        x = read_double(mem, follow(mem, path))
    except OSError:
        return None
    return x if 0.01 < abs(x) < 100000 else None


def keep(paths, how):
    before = [read_x(p) for p in paths]
    wait("Walk RIGHT and stop" if how == "up" else "Walk LEFT and stop")
    kept = []
    # zip = walk through both lists together
    for p, old in zip(paths, before):
        new = read_x(p)
        if old is None or new is None:
            continue
        if (how == "up" and new > old) or (how == "down" and new < old):
            kept.append(p)
    return kept


paths = keep(paths, "up")
paths = keep(paths, "down")
print(len(paths), "paths still find you:")
for p in paths[:10]:
    print("[" + ", ".join(hex(v) for v in p) + "]")

with open("good_paths.json", "w") as f:
    json.dump(paths, f)

if paths:
    print("\n>>> DONE! Put this line in hmbot.py:")
    print("PLAYER = [" + ", ".join(hex(v) for v in paths[0]) + "]")
else:
    print("!!! paths are dead. GG i so done idk jump out of a windo or something")
