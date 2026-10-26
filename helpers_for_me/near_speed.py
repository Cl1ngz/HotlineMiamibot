# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/near_speed.py - which of your character's variables MOVE during a swing?
#
# The speed place (0 at rest, 0.7 swinging) is one of the game's variables for your character.
# The other variables of your character most likely sit close to it in memory - like the "second frame"
# (0.4 at rest) that find_attack sometimes found. This copies the memory around the speed place many
# times a second while you swing, and prints every double that:
#   ANIMATES  - takes many different values during swings, but only a few at rest (it stands still between
#               swings - maybe on a different number after each one, like the "second frame": 0.4, then 2.4)
#   SWITCHES  - one value at rest, another one during a swing (like the speed itself)
#
#   python -m helpers_for_me.near_speed 0x2ff5bb8          (the speed place from find_attack, from THIS life)
#   be in a level with your weapon, somewhere safe, swing at the air a few times WITH PAUSES
import os
import sys
import time

import numpy as np

from core.memory import attach, read_double, wait

RADIUS = 0x2000  # look this many bytes before and after the speed place
REST_VALUES = 8  # at rest it may stand on a few different numbers (one per pause) - but not more than this
WATCH_TIME = 6  # seconds

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.near_speed 0x2ff5bb8   (the speed place from find_attack)")
speed_address = int(sys.argv[1], 16)
start_address = speed_address - RADIUS

mem, regions, static_regions = attach()
if read_double(mem, speed_address) != 0:
    raise SystemExit("the speed place isn't 0 - stand still (or it moved: did you die? run find_attack again)")

wait("swing at the air a few times - WITH PAUSES between swings", 3)
rows, speeds = [], []
start = time.monotonic()
while time.monotonic() - start < WATCH_TIME:
    try:
        data = os.pread(mem, 2 * RADIUS, start_address)
    except OSError:
        raise SystemExit("can't read around the speed place")
    values = np.frombuffer(data, dtype="<f8")
    rows.append(values.copy())
    speeds.append(values[RADIUS // 8])  # the speed place itself
    time.sleep(0.005)

table = np.array(rows)
swinging = np.array(speeds) != 0
print(f"{(~swinging).sum()} copies at rest, {swinging.sum()} while swinging")
if not swinging.any() or swinging.all():
    raise SystemExit("need both - swing a few times, with pauses")

rest_part, swing_part = table[~swinging], table[swinging]
with np.errstate(invalid="ignore"):
    usable = np.isfinite(table).all(axis=0) & (np.abs(table) < 1e6).all(axis=0)
    still_at_rest = (rest_part == rest_part[0]).all(axis=0)


def count_different(part):
    """How many different values each spot has in these copies."""
    ordered = np.sort(part, axis=0)
    return 1 + (np.diff(ordered, axis=0) != 0).sum(axis=0)


different = count_different(swing_part)  # while swinging
different_at_rest = count_different(rest_part)


def show(values):
    values = np.unique(values)
    return ", ".join(f"{v:.2f}" for v in values[:10]) + (" ..." if len(values) > 10 else "")


print("\nANIMATES (many values while swinging, only a few at rest):")
for i in np.flatnonzero(usable & (different >= 3) & (different_at_rest <= REST_VALUES)):
    print(f"  {start_address + i * 8:#x}   at rest: {show(rest_part[:, i]):24}   swinging: {show(swing_part[:, i])}")

print("\nSWITCHES (one value at rest, another one while swinging):")
for i in np.flatnonzero(usable & still_at_rest & (different == 1) & (swing_part[0] != rest_part[0])):
    marker = "   <- the speed place" if start_address + i * 8 == speed_address else ""
    print(f"  {start_address + i * 8:#x}   at rest {rest_part[0, i]:8.3f}   swinging: {swing_part[0, i]:.3f}{marker}")
