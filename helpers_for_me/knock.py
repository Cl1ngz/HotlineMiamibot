# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/knock.py - what happens in memory when you knock the sitting enemy over at the door?
#
# 1. photo: every place holding the X of the sitting enemy you always knock over (the one further left)
# 2. you walk in and knock him over - the script waits for that moment by itself
# 3. for a few seconds it keeps looking at every place from the photo
# 4. it prints the places that changed, and what's around the ones that kept moving off the shelf
#
#   python -m helpers_for_me.knock      (no REPL needed, it does everything in one go)
import os
import struct
import subprocess
import time

from enemies import RECORD
from memory import (
    X_OFF,
    Y_OFF,
    attach,
    read_double,
    read_kind,
    table_records,
    take_snapshot,
)

WATCH = 5  # seconds to keep looking after the knock
LOOK_EVERY = 0.5  # seconds between looks
SLOTS = 24  # how many 16-byte slots to show before and after a brain candidate

mem, regions, static_regions = attach()


def notify(text, seconds=3):
    """Pop-up on the screen, because you can't see the terminal while playing."""
    print(text)
    subprocess.run(["notify-send", "-t", str(seconds * 1000), "HMBot", text])


def all_places(snapshot, pattern):
    """Every address in the photo where these bytes sit."""
    found = []
    for start, data in snapshot.items():
        i = data.find(pattern)
        while i != -1:
            found.append(start + i)
            i = data.find(pattern, i + 1)
    return found


def read_value(address, fmt):
    """The number at this address: fmt "<d" = double (8 bytes), "<f" = float (4 bytes). None if unreadable."""
    size = struct.calcsize(fmt)
    try:
        data = os.pread(mem, size, address)
    except OSError:
        return None
    if len(data) < size:
        return None
    return struct.unpack(fmt, data)[0]


def looks_real(value):
    """A sensible position (not junk like 1e-43 or a huge number)."""
    return value is not None and 1 < abs(value) < 10000


def slot(address):
    """One 16-byte slot: (the double in its first 8 bytes, the two 4-byte numbers after it)."""
    value = read_value(address, "<d")
    try:
        tail = os.pread(mem, 8, address + 8)
    except OSError:
        return value, None, None
    if len(tail) < 8:
        return value, None, None
    return value, int.from_bytes(tail[:4], "little"), int.from_bytes(tail[4:], "little")


def show(value):
    """A double as text: the number if it looks like one, 'junk' if it's really something else."""
    if value is None:
        return f"{'?':>12}"
    if value == 0 or 1e-6 < abs(value) < 1e7:
        return f"{value:12.3f}"
    return f"{'junk':>12}"


def show_tag(number):
    return f"{'?':>10}" if number is None else f"{number:#10x}"


# --- 1. the enemy you knock over: the sitting one further left ---
sitting = [card for card in table_records(mem) if read_kind(mem, card, 0, 0x14) == 0xA6]
if not sitting:
    raise SystemExit("no sitting enemy - restart the floor so they sit again")
enemy = min(sitting, key=lambda card: read_double(mem, card + X_OFF))
x = read_double(mem, enemy + X_OFF)
y = read_double(mem, enemy + Y_OFF)
print(f"watching the sitting enemy at {x:.0f}, {y:.0f} (card {hex(enemy)})")

notify("photo of memory, don't move...")
snapshot = take_snapshot(mem, regions)
candidates = {}  # address -> "<d" or "<f"
for address in all_places(snapshot, struct.pack("<d", x)):
    candidates[address] = "<d"
for address in all_places(snapshot, struct.pack("<f", x)):
    candidates[address] = "<f"
print(f"{len(candidates)} places hold the number {x}")

# --- 2. wait for the knock: his card stops being "sitting at x" ---
notify(f"go in and knock him over (the one at {x:.0f}, {y:.0f})", 5)
while read_kind(mem, enemy, 0, 0x14) == 0xA6 and read_double(mem, enemy + X_OFF) == x:
    time.sleep(0.02)
print(f"knocked! watching for {WATCH} seconds...")

# --- 3. keep looking at every place from the photo ---
history = {address: [] for address in candidates}  # address -> its values over time
for _ in range(int(WATCH / LOOK_EVERY)):
    for address, fmt in candidates.items():
        history[address].append(read_value(address, fmt))
    time.sleep(LOOK_EVERY)
notify("done watching - check the terminal", 5)

# --- 4. which places changed? ---
cards = table_records(mem)
shelf_low = min(cards) - 64 * RECORD if cards else 0
shelf_high = max(cards) + 65 * RECORD if cards else 0
movers = []  # places off the shelf that took at least 3 different sensible values
print(f"\nplaces that changed after the knock (a value every {LOOK_EVERY} s, - = junk):")
for address, values in sorted(history.items()):
    if all(value == x for value in values):
        continue  # never changed: it has nothing to do with him
    where = "shelf" if shelf_low <= address < shelf_high else "     "
    kind = "double" if candidates[address] == "<d" else "float "
    row = " ".join(f"{value:7.1f}" if looks_real(value) else "      -" for value in values)
    print(f"  {hex(address):>11} {where} {kind} {row}")
    different = {round(value, 1) for value in values if looks_real(value)}
    if where != "shelf" and len(different) >= 3:
        movers.append(address)

# --- 5. what's around the places that kept moving? ---
# Last time it looked like a list of 16-byte slots: an 8-byte number + 8 bytes that look like a label.
# Show the slots around each candidate, looked at twice, 2 s apart, and mark the ones that changed.
for address in movers:
    first = {n: slot(address + n * 16) for n in range(-SLOTS, SLOTS + 1)}
    time.sleep(2)
    second = {n: slot(address + n * 16) for n in range(-SLOTS, SLOTS + 1)}
    print(f"\naround {hex(address)} (it kept moving - a brain candidate)")
    print("  slot  address      look 1       look 2    the 8 bytes after the number")
    for n in range(-SLOTS, SLOTS + 1):
        (v1, a1, b1), (v2, a2, b2) = first[n], second[n]
        mark = "  <- changed" if v1 != v2 else ""
        here = "  <- the candidate" if n == 0 else ""
        print(f"  {n:+4}  {hex(address + n * 16)}  {show(v1)} {show(v2)}    {show_tag(a1)} {show_tag(b1)}{here}{mark}")
if not movers:
    print("\nnothing off the shelf kept moving with him")
