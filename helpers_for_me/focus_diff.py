# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/focus_diff.py - what changes in DirectInput's mouse when the game gets / loses focus?
#
# Writing 0x80 into DirectInput's button byte (0x181cc29) is a real click - but only while the game is focused.
# DirectInput keeps a status for every device: "acquired" (the game owns it, it's focused) or not.
# That status is a number in memory, most likely close to the button byte. This copies the memory around
# the button byte with the game focused and unfocused, a few times, and prints every 4-byte spot that is
# one value EVERY time the game is focused and another value EVERY time it isn't.
#
#   python -m helpers_for_me.focus_diff                (button byte 0x181cc29)
#   python -m helpers_for_me.focus_diff 0x181cc29
#   follow the pop-ups: switch focus with the KEYBOARD (no clicking, don't touch the mouse)
import os
import sys

import numpy as np

from core.memory import attach, wait

BEFORE = 0x1000  # look this many bytes before the button byte...
AFTER = 0x400  # ...and this many after it
ROUNDS = 3

button = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x181CC29
start = (button - BEFORE) & ~3  # start on a 4-byte boundary
size = BEFORE + AFTER

mem, regions, static_regions = attach()


def look(prompt):
    wait(prompt, 4)
    return np.frombuffer(os.pread(mem, size, start), dtype="<u4").copy()


focused, unfocused = [], []
for round_number in range(1, ROUNDS + 1):
    focused.append(look(f"round {round_number}/{ROUNDS}: switch to the GAME (keyboard), hands off the mouse"))
    unfocused.append(look(f"round {round_number}/{ROUNDS}: switch to the TERMINAL (keyboard)"))
focused, unfocused = np.array(focused), np.array(unfocused)

same_when_focused = (focused == focused[0]).all(axis=0)
same_when_unfocused = (unfocused == unfocused[0]).all(axis=0)
different = focused[0] != unfocused[0]
spots = np.flatnonzero(same_when_focused & same_when_unfocused & different)

print(f"\n{len(spots)} spots follow the focus exactly (offset from the button byte {button:#x}):")
for i in spots:
    address = start + int(i) * 4
    print(f"  {address:#x}  ({address - button:+#06x})   focused: {focused[0, i]:#010x}   unfocused: {unfocused[0, i]:#010x}")
