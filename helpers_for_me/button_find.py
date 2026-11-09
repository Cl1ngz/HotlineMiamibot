# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/button_find.py - where is the LEFT mouse button byte today? (a helper, only reads)
#
# DirectInput keeps every mouse button as one byte: 0x80 while it's held, 0 when it's let go
# (the right button is the byte right after the left one). hands.py presses the left button by writing
# 0x80 at [GAME] -> +0x42C -> +0x9C -> +0x52D. If that byte stays 0 while you HOLD the button in the game,
# the chain leads to an old place (like the look did today). This finds the byte that really follows the
# button: 3 photos of the game's writable memory - held, let go, held again.
#
#   python -m helpers_for_me.button_find     the bot NOT running, a safe spot in a level (nobody near)
#   when it says HOLD: click into the game and keep the LEFT button down until it says LET GO
import os

import numpy as np

from core.hands import BUTTON, follow
from core.memory import attach, read_bytes, wait

HELD = 0x80
CHUNK = 4 << 20  # read the memory 4 MB at a time
SHOW = 20

mem, regions, static_regions = attach()
try:
    old = follow(mem, BUTTON)
    print(f"the chain in hands.py leads to {old:#x}")
except OSError:
    old = None
    print("the chain in hands.py leads nowhere")


def photo(keep, pieces=None):
    """{piece start: places in it} where keep(bytes, piece start) says so. pieces = only read these pieces."""
    found = {}
    for start, end in regions:
        for at in range(start, end, CHUNK):
            if pieces is not None and at not in pieces:
                continue
            try:
                data = np.frombuffer(os.pread(mem, min(CHUNK, end - at), at), np.uint8)
            except OSError:
                continue
            places = keep(data, at)
            if len(places):
                found[at] = places
    return found


def still(found, value):
    """Only the places from found whose byte is value NOW."""

    def keep(data, at):
        places = found[at]
        places = places[places < len(data)]
        return places[data[places] == value]

    return photo(keep, found)


def count(found):
    return sum(len(places) for places in found.values())


wait("HOLD the LEFT mouse button in the game and keep holding it", 3)
held = photo(lambda data, at: np.nonzero(data == HELD)[0])
print(f"  0x80 bytes while held: {count(held)}")
wait("LET GO of the button (hands off the mouse)", 3)
held = still(held, 0)
print(f"  ...and 0 when let go: {count(held)}")
wait("HOLD the LEFT button again", 3)
held = still(held, HELD)
print(f"  ...and 0x80 again: {count(held)}")
wait("you can let go now", 1)

print("\nbytes that followed the left button:")
shown = 0
for at, places in held.items():
    for place in places[:SHOW]:
        address = at + int(place)
        try:
            right = read_bytes(mem, 1, address + 1)[0]
        except (OSError, IndexError):
            right = None
        same = "  <- the one hands.py uses" if address == old else ""
        print(f"  {address:#x}   (the byte after it, the right button: {right})" + same)
        shown += 1
if not shown:
    print("  none - was the game focused while you held the button?")
print("\nsend me this; next: python -m helpers_for_me.find_path <the address>")
