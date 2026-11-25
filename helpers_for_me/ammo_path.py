# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/ammo_path.py - how do we get to the ammo from something we always know?
#
# ammo_watch found your ammo: a 4-byte whole number on the heap. Its address changes between game starts
# (maybe between floors and guns too), so the bot needs a way there that doesn't change: a pointer in your
# card / folder (or one step further), or in the game file. This lists the places that point at the ammo
# or a bit before it (the start of the thing that holds it), and says whose they are.
#
#   python -m helpers_for_me.ammo_path 0x30fb308     the address ammo_watch printed (the same game run!)
import os
import sys

import numpy as np

from core.enemies import INSTANCE, RECORD, find_me_card, shelf_cards
from core.memory import attach, find_game, read_u32, table_records

NEAR = 0x800  # the thing that holds the ammo starts at most this far before it
CHUNK = 4 << 20
LOOK = 0x800  # one step further: how much of each thing your card / folder points at to read
SHOW = 30
WIDE = 1024


def all_regions():
    """Every writable piece of the game's memory - but no devices."""
    regions = []
    with open(f"/proc/{find_game()[0]}/maps") as f:
        for line in f:
            parts = line.split(None, 5)
            path = parts[5].strip() if len(parts) == 6 else ""
            if parts[1].startswith("rw") and not path.startswith(("/dev/", "[v")):
                start, end = (int(x, 16) for x in parts[0].split("-"))
                regions.append((start, end))
    return regions


def pointers_to(low, high):
    """[(place, value), ...] of every 4-byte aligned place in the memory whose value is in low..high."""
    found = []
    for start, end in all_regions():
        for at in range(start, end, CHUNK):
            try:
                data = os.pread(mem, min(CHUNK, end - at), at)
            except OSError:
                continue
            values = np.frombuffer(data, "<u4", len(data) // 4)
            for i in np.nonzero((values >= low) & (values <= high))[0]:
                found.append((at + 4 * int(i), int(values[i])))
    return found


def owner(place):
    """(rank, text): whose card / folder the place is in - you first, then the game file, then the rest."""
    if card <= place < card + RECORD:
        return 0, f"YOUR card +{place - card:#x}"
    if folder <= place < folder + INSTANCE:
        return 0, f"YOUR folder +{place - folder:#x}"
    if any(s <= place < e for s, e in static_regions):
        return 1, "in the game file (same address every launch)"
    table = table_records(mem)
    for other in shelf_cards(mem, table, WIDE) if table else []:
        try:
            other_folder = read_u32(mem, other)
            layer = read_u32(mem, other + 0x14)
            picture = read_u32(mem, other_folder + 0x10)
        except OSError:
            continue
        if other <= place < other + RECORD:
            return 2, f"card +{place - other:#x} (layer {layer:#x} picture {picture:#x})"
        if other_folder <= place < other_folder + INSTANCE:
            return 2, f"folder +{place - other_folder:#x} (layer {layer:#x} picture {picture:#x})"
    return 3, "somewhere else"


args = sys.argv[1:]
if len(args) != 1:
    raise SystemExit("usage: python -m helpers_for_me.ammo_path 0x30fb308   (the address from ammo_watch)")
ammo = int(args[0], 16)
mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - be in a level")
folder = read_u32(mem, card)
try:
    print(f"ammo at {ammo:#x} holds {int.from_bytes(os.pread(mem, 4, ammo), 'little', signed=True)}")
except OSError:
    raise SystemExit("can't read that address - a new game start? run ammo_watch again")

# 1. who points at the ammo (or a bit before it), anywhere in the memory
found = sorted((owner(place), place, value) for place, value in pointers_to(ammo - NEAR, ammo))
print(f"\n{len(found)} places point at the ammo or up to {NEAR:#x} before it:")
for (rank, text), place, value in found[:SHOW]:
    print(f"  {place:#x} -> {value:#x}  (ammo at +{ammo - value:#x})   {text}")

# 2. one step further from you: your card / folder -> a thing -> (a bit before) the ammo
print("\nfrom your card / folder, one step further:")
steps = 0
for name, base, size in (("card", card, RECORD), ("folder", folder, INSTANCE)):
    data = os.pread(mem, size, base)
    for offset in range(0, size - 3, 4):
        thing = int.from_bytes(data[offset : offset + 4], "little")
        if thing < 0x10000 or thing == base:
            continue
        try:
            inside = np.frombuffer(os.pread(mem, LOOK, thing), "<u4")
        except OSError:
            continue
        for i in np.nonzero((inside >= ammo - NEAR) & (inside <= ammo))[0]:
            value = int(inside[i])
            print(f"  your {name} +{offset:#x} -> {thing:#x}, +{4 * int(i):#x} -> {value:#x}, ammo at +{ammo - value:#x}")
            steps += 1
if not steps:
    print("  nothing - send me this output")
