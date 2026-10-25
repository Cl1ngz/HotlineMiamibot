# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/test_look.py - does core/look.py work?
# Finds where your character looks, then turns you to the RIGHT for 3 s. Works with the game unfocused too.
#
#   python -m helpers_for_me.test_look        (be in a level, let go of the mouse when the pop-up says so)
import time

from core.enemies import find_aim, find_me
from core.look import GAP, find_look, look_at
from core.memory import attach, open_rw, wait

DISTANCE = 80  # how far to the right of you to look (game units)

mem, regions, static_regions = attach()
mem_rw = open_rw()

find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("move the mouse a little, then LET GO of it", 3)
aim = find_aim(mem)
if aim is None:
    raise SystemExit("no crosshair - are you in a level?")

start = time.perf_counter()
look = find_look(mem, regions, aim)
took = time.perf_counter() - start
if look is None:
    raise SystemExit("find_look found nothing (or more than one) - was the mouse still moving? run it again")
# well under 1 ms = the fast way (KNOWN) worked, hundreds of ms = it had to search all the memory
print(f"look X at {look:#x}, look Y at {look - GAP:#x}   (found in {took * 1000:.1f} ms)")

you = find_me(mem)
if you is None:
    raise SystemExit("can't find you")
target = (you[0] + DISTANCE, you[1])
wait("watch your character - it should face RIGHT for 3 s", 2)
start = time.monotonic()
while time.monotonic() - start < 3:
    look_at(mem_rw, look, target)
    time.sleep(0.001)
print("done - did your character face right the whole time?")
