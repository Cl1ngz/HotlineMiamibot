# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/look_find.py - where are look X / look Y today? (a helper, only reads)
#
# chain_check showed: [GAME] -> +0x3F4 is still the table of the game's globals, but its places
# +0x460 (look X) and +0x438 (look Y) are EMPTY (0) today - the two "where the mouse is" globals sit
# somewhere else. Each one is a pointer to a 16-byte slot with the value (a double) at +8,
# and the value is exactly where the crosshair is. So:
#   1. go through the WHOLE globals table: which slots follow the crosshair while you move the mouse?
#   2. nothing there -> go through all the game's memory for doubles that follow the crosshair,
#      and for the pointers to their slots (where the chain goes today)
#
#   python -m helpers_for_me.look_find     the bot NOT running, you in a level with the crosshair on
#                                         screen, the game focused - move the mouse when it says so
import os
import time
from collections import Counter, defaultdict

import numpy as np

from core.enemies import find_aim
from core.hands import GAME, LOOK_X, LOOK_Y
from core.memory import attach, read_bytes, read_double, read_u32, wait

TABLE = 0x2000  # bytes of the globals table to go through (2048 places, the old ones were 0x438 / 0x460)
SAMPLES = 25  # looks at the table...
EVERY = 0.2  # ...this many seconds apart (5 s of moving the mouse)
NEAR = 0.5  # a value this close to the crosshair "is" the crosshair
CHUNK = 4 << 20  # read the memory 4 MB at a time
SHOW = 20  # print at most this many

mem, regions, static_regions = attach()
table_at = read_u32(mem, read_u32(mem, GAME) + LOOK_X[0][0])
print(f"the globals table: [{GAME:#x}] -> +{LOOK_X[0][0]:#x} = {table_at:#x}")


def table_pointers():
    """{place in the table: the pointer there} - the places that aren't 0."""
    try:
        data = read_bytes(mem, TABLE, table_at)
    except OSError:
        return {}
    words = np.frombuffer(data[: len(data) // 4 * 4], "<u4")
    return {i * 4: int(q) for i, q in enumerate(words) if q}


def slot_text(q):
    """The 16 bytes of a slot: two whole numbers and the double."""
    try:
        return f"slot {q:#x}: +0 {read_u32(mem, q):#x}  +4 {read_u32(mem, q + 4):#x}  +8 {read_double(mem, q + 8):.1f}"
    except OSError:
        return f"slot {q:#x}: can't read"


for name, (offsets, _) in (("look X", LOOK_X), ("look Y", LOOK_Y)):
    print(f"  the old place of {name}, +{offsets[1]:#x}: {table_pointers().get(offsets[1], 0):#x}")

# --- 1. the table ---
find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("move the mouse around in the game - circles, all over the screen - for 5 s", 3)
hits = Counter()  # (place, "X"/"Y") -> how many looks its value was the crosshair's
values = defaultdict(set)  # place -> the values it had
looks_with_aim = 0
aims = set()
for _ in range(SAMPLES):
    aim = find_aim(mem)
    if aim is not None:
        looks_with_aim += 1
        aims.add((round(aim[0]), round(aim[1])))
    for place, q in table_pointers().items():
        try:
            value = read_double(mem, q + 8)
        except OSError:
            continue
        values[place].add(round(value, 1))
        if aim is not None:
            hits[(place, "X")] += abs(value - aim[0]) < NEAR
            hits[(place, "Y")] += abs(value - aim[1]) < NEAR
    time.sleep(EVERY)

print(f"\nthe crosshair was found in {looks_with_aim} of {SAMPLES} looks, at {len(aims)} different spots")
if looks_with_aim == 0:
    raise SystemExit("no crosshair at all - be in a level (the crosshair on screen) and try again")
if len(aims) < 5:
    print("  !! it hardly moved - move the mouse more next time (the game must be focused)")
found = [
    (place, axis, count)
    for (place, axis), count in hits.items()
    if count >= 0.8 * looks_with_aim and len(values[place]) >= 3
]
print("\nplaces in the table that follow the crosshair (the new look X / look Y):")
pointers = table_pointers()
for place, axis, count in sorted(found):
    print(f"  look {axis}: +{place:#x}  ({count}/{looks_with_aim} looks)   {slot_text(pointers.get(place, 0))}")
if found:
    raise SystemExit("\nsend me this - the fix is new numbers in core/hands.py (or finding them by itself)")
print("  none in the table")

# --- 2. all the game's memory ---
def scan(test):
    """Every 8-aligned address in the game's writable memory whose double passes test(array) -> mask."""
    out = []
    for start, end in regions:
        for at in range(start, end, CHUNK):
            try:
                data = os.pread(mem, min(CHUNK, end - at), at)
            except OSError:
                continue
            numbers = np.frombuffer(data[: len(data) // 8 * 8], "<f8")
            with np.errstate(invalid="ignore", over="ignore"):
                out.extend((at + 8 * np.nonzero(test(numbers))[0]).tolist())
    return out


wait("put the mouse on ONE spot and keep it STILL", 3)
first = find_aim(mem)
if first is None:
    raise SystemExit("lost the crosshair - try again")
xs = scan(lambda n: np.abs(n - first[0]) < NEAR)
ys = scan(lambda n: np.abs(n - first[1]) < NEAR)
wait("now put it on ANOTHER spot, far from the first, and keep it STILL", 3)
second = find_aim(mem)
if second is None or abs(second[0] - first[0]) < 20 or abs(second[1] - first[1]) < 20:
    raise SystemExit("the second spot must be far from the first (both ways) - try again")


def still_follows(addresses, value):
    keep = []
    for address in addresses:
        try:
            if abs(read_double(mem, address) - value) < NEAR:
                keep.append(address)
        except OSError:
            continue
    return keep


xs, ys = still_follows(xs, second[0]), still_follows(ys, second[1])
print(f"\ndoubles that followed the crosshair: {len(xs)} for X, {len(ys)} for Y")
slots = {address - 8: axis for axis, group in (("X", xs), ("Y", ys)) for address in group[:SHOW]}
for slot, axis in slots.items():
    print(f"  {axis}  {slot_text(slot)}")

# who points at those slots? (the chain's last link)
targets = np.array(sorted(slots), dtype="<u4")
print("\npointers to those slots:")
shown = 0
for start, end in regions:
    for at in range(start, end, CHUNK):
        try:
            data = os.pread(mem, min(CHUNK, end - at), at)
        except OSError:
            continue
        words = np.frombuffer(data[: len(data) // 4 * 4], "<u4")
        for i in np.nonzero(np.isin(words, targets))[0]:
            where = at + 4 * int(i)
            slot = int(words[i])
            near_table = f"  = the table +{where - table_at:#x}" if 0 <= where - table_at < 0x100000 else ""
            print(f"  at {where:#x} -> slot {slot:#x} (look {slots[slot]}){near_table}")
            shown += 1
if not shown:
    print("  none")
print("\nsend me all of this")
