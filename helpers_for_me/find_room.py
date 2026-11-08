# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/find_room.py - find the number that says WHICH SCENE the game is in (GameMaker's "room")
#
# Every floor of a level, the car, the score screen, the apartment, the mask menu... is its own "room" in the
# game, and the game keeps the room's number in its memory. With that number the bot always knows where it is:
# a new floor, the end of a level, the apartment - that's what the trips between levels need.
#
#   python -m helpers_for_me.find_room            look for it (only READS memory)
#   python -m helpers_for_me.find_room --all      ...in the whole game memory, not only the game's own globals
#                                                 (slower, more RAM - only if the first try finds nothing)
#   python -m helpers_for_me.find_room --more     MORE photos to narrow down the candidates found last time
#   python -m helpers_for_me.find_room --watch    show the candidates found last time, live
#
# How: go to a scene in the game, type a NAME for it here (floor1, floor2, car, menu...) + Enter = a photo.
# Go to another scene, name it, Enter. COME BACK to scenes you've named and use the SAME name again - that's
# what tells the room number apart from all the other numbers that change. "done" + Enter = the results.
# Best: 3+ different scenes, each one 2+ times, e.g.  floor1, floor2, floor1, floor2, car, floor1
# Too many candidates? --more: name more scenes (old names AND new ones) - every photo throws out the numbers
# that don't follow the scenes, until only a few are left. You can come back to it any time.
import json
import sys
import time

import numpy as np

from core.memory import attach, read_double, read_u32, take_snapshot

SAVE_FILE = "find_room.json"
MAX_ROOM = 2000  # a room number is a small whole number - bigger values are something else
SHOW = 25  # print at most this many candidates


def candidates(photos, names):
    """[(address, "u32"/"f64", {name: value})] - values that are the same in every photo of the same scene
    and different for different scenes."""
    groups = {}  # scene name -> indexes of its photos
    for i, name in enumerate(names):
        groups.setdefault(name, []).append(i)
    found = []
    for start in photos[0]:
        if any(start not in photo for photo in photos):
            continue  # this region couldn't be read every time
        size = min(len(photo[start]) for photo in photos)
        for kind, width in (("u32", 4), ("f64", 8)):
            count = size // width
            dtype = "<u4" if kind == "u32" else "<f8"
            rows = np.stack([np.frombuffer(photo[start][: count * width], dtype=dtype) for photo in photos])
            first = rows[[ids[0] for ids in groups.values()]]  # one value per scene
            ok = np.ones(count, dtype=bool)
            # the same in every photo of the same scene
            for ids in groups.values():
                for i in ids[1:]:
                    ok &= rows[i] == rows[ids[0]]
            # different for every two different scenes
            for a in range(len(first)):
                for b in range(a + 1, len(first)):
                    ok &= first[a] != first[b]
            # a small whole number
            with np.errstate(invalid="ignore"):  # junk doubles (NaN) just don't pass
                ok &= np.all((first >= 0) & (first <= MAX_ROOM), axis=0)
                if kind == "f64":
                    ok &= np.all(first == np.floor(first), axis=0)
            for index in np.nonzero(ok)[0]:
                values = {name: first[k][index].item() for k, name in enumerate(groups)}
                found.append((start + int(index) * width, kind, values))
    return found


def load():
    """The candidates saved last time: [{"address", "kind", "values": {scene: value}}]."""
    try:
        with open(SAVE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        raise SystemExit(f"no {SAVE_FILE} yet (or an old one) - run it without --more / --watch first")


def save(found):
    with open(SAVE_FILE, "w") as f:
        json.dump(found, f, indent=1)


def now_value(candidate):
    """What the game holds at this candidate right now (None = can't read it)."""
    address = int(candidate["address"], 16)
    try:
        return read_u32(mem, address) if candidate["kind"] == "u32" else read_double(mem, address)
    except OSError:
        return None


def show(found):
    print(f"{len(found)} candidates" + (f", the first {SHOW}:" if len(found) > SHOW else ":"))
    for c in found[:SHOW]:
        print(f"  {c['address']:>10}  {c['kind']}   " + "  ".join(f"{n} {v:g}" for n, v in c["values"].items()))


def more():
    """More photos: every one throws out the candidates that don't follow the scenes."""
    found = load()
    show(found)
    while len(found) > 1:
        name = input(f"\n{len(found)} left - name of the scene you're in now (or done): ").strip()
        if name == "done":
            break
        if not name:
            continue
        kept = []
        for c in found:
            value = now_value(c)
            if value is None:
                continue
            if name in c["values"]:
                if value == c["values"][name]:  # a scene seen before: the very same number
                    kept.append(c)
            elif value not in c["values"].values():  # a new scene: a number no other scene had
                c["values"][name] = value
                kept.append(c)
        found = kept
        save(found)
        if len(found) <= SHOW:
            show(found)
    print()
    show(found)


def watch():
    found = load()[:SHOW]
    print("change scenes in the game - the room number follows you. Ctrl+C = end")
    print("   " + "  ".join(f"{c['address']:>10}" for c in found))
    while True:
        values = [now_value(c) for c in found]
        print("   " + "  ".join(f"{'?' if v is None else f'{v:g}':>10}" for v in values), end="\r", flush=True)
        time.sleep(0.2)


mem, regions, static_regions = attach()
if "--watch" in sys.argv or "--more" in sys.argv:
    try:
        watch() if "--watch" in sys.argv else more()
    except KeyboardInterrupt:
        print()
    raise SystemExit

where = regions if "--all" in sys.argv else static_regions
size = sum(end - start for start, end in where)
print(f"looking in {len(where)} regions, {size / 1e6:.1f} MB per photo")
photos, names = [], []
while True:
    name = input(f"photo {len(photos) + 1} - name of the scene you're in now (or done): ").strip()
    if name == "done":
        break
    if not name:
        continue
    photos.append(take_snapshot(mem, where))
    names.append(name)
    print(f"   ok, {len(set(names))} scenes so far: {', '.join(sorted(set(names)))}")

if len(set(names)) < 2:
    raise SystemExit("at least 2 different scenes are needed")
if len(names) == len(set(names)):
    print("(no scene was photographed twice - there will be many false candidates, come back to a scene next time)")
found = [{"address": hex(a), "kind": kind, "values": values} for a, kind, values in candidates(photos, names)]
print()
show(found)
save(found)
if len(found) > 3:
    print(f"\nsaved to {SAVE_FILE} - narrow them down:  python -m helpers_for_me.find_room --more")
elif found:
    print(f"\nsaved to {SAVE_FILE} - check them live:  python -m helpers_for_me.find_room --watch")
