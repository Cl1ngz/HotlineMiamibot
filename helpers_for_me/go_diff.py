# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/go_diff.py - what changes in memory when the floor is clear and the "GO!" arrow appears?
#
# It keeps taking a photo of every card on the shelf (0xB8 bytes each) while at least one enemy is alive.
# When the last enemy is gone (is_enemy says no for everyone for a moment) it waits a bit for GO! to show up,
# takes one more photo and compares the two:
#   NEW      cards that weren't there before (or got a new kind - a reused card)
#   CHANGED  cards near the stairs (+0x10 is 0x51 or 0x55) - which 4-byte spots changed
#
#   python -m helpers_for_me.go_diff     (start on a floor with ONE enemy left alive, then go kill him;
#                                        hmbot can do the killing - stand still after, wait for GO!)
import os
import struct
import time

from core.enemies import RECORD, find_me, is_enemy, load_rules
from core.memory import X_OFF, Y_OFF, attach, read_double, table_records

LAYER, KIND = 0x14, 0x10  # card offsets: layer, kind/state
WATCH = (0x51, 0x55)  # kinds we saw at the stairs
EVERY = 0.25  # seconds between photos
CLEAR_FOR = 1.0  # no enemy for this long = the floor is clear
AFTER = 2.0  # then wait this long for GO! to show up
GIVE_UP = 90  # seconds

mem, regions, static_regions = attach()
rules = load_rules()


def shelf(records):
    """Every card on the shelf around the table's cards that stands at a real position."""
    cards = []
    for card in range(min(records) - 64 * RECORD, max(records) + 64 * RECORD + 1, RECORD):
        try:
            x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        except OSError:
            continue
        if 0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000:
            cards.append(card)
    return cards


def photo():
    """{card: its 0xB8 bytes} for the whole shelf, and how many enemies are alive on it."""
    records = table_records(mem)
    if not records:
        return {}, 0, set()
    copies = {}
    alive = 0
    for card in shelf(records):
        try:
            data = os.pread(mem, RECORD, card)
        except OSError:
            continue
        if len(data) == RECORD:
            copies[card] = data
            alive += is_enemy(mem, card, rules)
    return copies, alive, set(records)


def u32(data, offset):
    return int.from_bytes(data[offset : offset + 4], "little")


def double(data, offset):
    """8 bytes of the photo at offset, read as a double (like read_double, but from the copy)."""
    return struct.unpack("<d", data[offset : offset + 8])[0]


def show(card, data, table):
    x, y = double(data, X_OFF), double(data, Y_OFF)
    where = "table" if card in table else "SHELF"
    return f"{card:#x} ({x:4.0f},{y:4.0f})  layer {u32(data, LAYER):#x}  +0x10 {u32(data, KIND):#x}  {where}"


before, alive, _ = photo()
if alive == 0:
    raise SystemExit("no enemy alive right now - start while at least ONE enemy is still alive on this floor")
print(f"{alive} enemies alive - go kill them. Waiting for the floor to be clear...")
started = time.monotonic()
clear_since = None
while True:
    now = time.monotonic()
    if now - started > GIVE_UP:
        raise SystemExit(f"gave up after {GIVE_UP} s - is somebody still counted as an enemy? (a ghost?)")
    copies, alive, _ = photo()
    if alive:
        before = copies  # the newest photo with somebody still alive
        clear_since = None
    elif clear_since is None:
        clear_since = now
    elif now - clear_since > CLEAR_FOR:
        break
    print(f"enemies alive: {alive}   ", end="\r", flush=True)
    time.sleep(EVERY)

print(f"\nfloor clear! waiting {AFTER} s for GO! ...")
time.sleep(AFTER)
after, _, table = photo()
you = find_me(mem)
print(f"you at {you[0]:.0f},{you[1]:.0f}" if you else "can't find you")

print("\nNEW (not there before, or a new kind):")
new = 0
for card, data in after.items():
    old = before.get(card)
    if old is None or u32(old, LAYER) != u32(data, LAYER) or u32(old, KIND) != u32(data, KIND):
        print("  " + show(card, data, table))
        new += 1
if not new:
    print("  nothing")

print("\nCHANGED cards with +0x10 in", [hex(k) for k in WATCH], "(which 4-byte spots changed: old -> new):")
for card, data in after.items():
    old = before.get(card)
    if old is None or u32(data, KIND) not in WATCH:
        continue
    spots = [
        f"+{offset:#x}: {u32(old, offset):#x} -> {u32(data, offset):#x}"
        for offset in range(0, RECORD - 3, 4)
        if u32(old, offset) != u32(data, offset) and not (X_OFF <= offset < X_OFF + 0x20)
    ]
    print("  " + show(card, data, table) + ("   " + ", ".join(spots) if spots else "   (nothing changed)"))
