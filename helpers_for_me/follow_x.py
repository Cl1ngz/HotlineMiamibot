# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/follow_x.py - find every place in memory that moves together with an enemy's X
#
# 1. picks a SITTING enemy (he stands still, so the photo of memory can't be "blurry")
# 2. photo of all memory: every address that holds his X, as a double or as a float
# 3. you wake him up; while he moves, keep only the addresses that follow his X
# Whatever survives moves together with the enemy: his card, and hopefully his "brain".
#
#   python -m helpers_for_me.follow_x      (Ctrl+C stops it early and shows what's left)
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

MOVES = 5  # 5 moves is enough, and with 0.05 s between looks it's over in well under a second
CLOSE = 5.0  # a copy may be a frame behind or ahead of the card, so "close to his X" is good enough
MAX_JUMP = 40  # nobody runs this far in 0.05 s - if X "jumps", the card holds something else now

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


# --- 1. pick a sitting enemy ---
sitting = [card for card in table_records(mem) if read_kind(mem, card, 0, 0x14) == 0xA6]
if not sitting:
    raise SystemExit("no sitting enemy - restart the floor so they sit again")
enemy = sitting[0]
x = read_double(mem, enemy + X_OFF)
y = read_double(mem, enemy + Y_OFF)
print(f"watching the sitting enemy at {x:.0f}, {y:.0f} (card {hex(enemy)})")

# --- 2. the photo: every place that holds his X right now ---
notify("photo of memory, don't move...")
snapshot = take_snapshot(mem, regions)
candidates = {}  # address -> "<d" or "<f"
for address in all_places(snapshot, struct.pack("<d", x)):
    candidates[address] = "<d"
for address in all_places(snapshot, struct.pack("<f", x)):
    candidates[address] = "<f"
print(f"{len(candidates)} places hold the number {x}")
notify(
    f"now wake up THAT enemy (at {x:.0f}, {y:.0f}) - it's over as soon as he starts moving",
    5,
)

# --- 3. while he moves: keep only the places that stay close to his X ---
last_x = x
moves = 0
try:
    while moves < MOVES and candidates:
        time.sleep(0.05)
        if read_kind(mem, enemy, 0, 0x14) not in (6, 0xA6):
            print("  he's not an enemy any more (dead? you died?) - stopping")
            break
        x_now = read_double(mem, enemy + X_OFF)
        if abs(x_now - last_x) < 1:
            continue  # he barely moved since last time - nothing to learn yet
        if abs(x_now - last_x) > MAX_JUMP:
            print(
                f"  X jumped {last_x:.0f} -> {x_now:.0f} - the card holds something else now, stopping"
            )
            break
        survivors = {}
        for address, fmt in candidates.items():
            value = read_value(address, fmt)
            if value is not None and abs(value - x_now) < CLOSE:
                survivors[address] = fmt
        candidates = survivors
        last_x = x_now
        moves += 1
        print(
            f"  he moved to x = {x_now:.1f}: {len(candidates)} places still follow him"
        )
except KeyboardInterrupt:
    print("\nstopped early")

# --- 4. what's left ---
print(f"\nafter {moves} moves, {len(candidates)} places moved together with him:")
for address, fmt in sorted(candidates.items()):
    inside = (
        f"  <- inside his card (+{hex(address - enemy)})"
        if enemy <= address < enemy + RECORD
        else ""
    )
    kind = "double" if fmt == "<d" else "float"
    print(f"  {hex(address)}  {kind:6}  {read_value(address, fmt)}{inside}")
notify(f"done: {len(candidates)} places moved with him - check the terminal", 10)
