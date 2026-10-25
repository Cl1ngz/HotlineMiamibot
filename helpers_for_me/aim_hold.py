# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/aim_hold.py - does an attack go where the CHARACTER looks, or where the CROSSHAIR is?
#
# write_mouse showed: writing the mouse x at 0x2845858 turns your character, but not the crosshair.
# Now we hold the character's look (x AND y) on a point to the RIGHT of you, while the crosshair sits on your LEFT,
# and you attack. Where the swing / the bullet goes answers the question.
#
#   python -m helpers_for_me.aim_hold 0x2845858 0x2845808        (x place, then y place - from find_mouse)
#   be in a level with a weapon, STAND STILL, crosshair on your LEFT, then click to attack while it holds
import os
import sys
import time

from core.enemies import find_me
from core.memory import attach, find_game, wait, write_double

HOLD_TIME = 5  # seconds
DISTANCE = 80  # how far to the right of you the bot points (game units)

if len(sys.argv) < 3:
    raise SystemExit("usage: python -m helpers_for_me.aim_hold 0x2845858 0x2845808   (x place, y place)")
x_address, y_address = (int(text, 16) for text in sys.argv[1:3])

mem, regions, static_regions = attach()
pid = find_game()[0]
mem_rw = os.open(f"/proc/{pid}/mem", os.O_RDWR)

wait("put the crosshair on the LEFT of your character and let go of the mouse. Then CLICK to attack!", 4)
you = find_me(mem)
if you is None:
    raise SystemExit("can't find you - are you in a level?")
target = (you[0] + DISTANCE, you[1])  # a point to the RIGHT of you
print(f"you at {you[0]:.1f}, {you[1]:.1f} - holding the look on {target[0]:.1f}, {target[1]:.1f} for {HOLD_TIME} s")

start = time.monotonic()
writes = 0
while time.monotonic() - start < HOLD_TIME:
    write_double(mem_rw, x_address, target[0])
    write_double(mem_rw, y_address, target[1])
    writes += 1
    time.sleep(0.001)
print(f"done - wrote {writes} times")
print("Did your character face RIGHT the whole time? Where did your attacks go: RIGHT (bot) or LEFT (crosshair)?")
