# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/write_mouse.py - which of the places that follow the mouse is the SOURCE (the "notebook")?
#
# find_mouse found places that hold the mouse x. Some may be copies (like the crosshair's own X - writing
# there did nothing). Test each one: keep writing x + SHIFT there for a moment and watch the crosshair.
#   the crosshair jumps to our value  -> the game reads from this place: it's the notebook
#   the crosshair doesn't care        -> just another copy
#
#   python -m helpers_for_me.write_mouse 0x2845858 0x2fde968 0x2fdee68 0x2fdf588
#   (the addresses find_mouse printed - be in a level and DON'T touch the mouse during the tests)
import os
import sys
import time

from core.enemies import find_aim, find_aim_card
from core.memory import X_OFF, attach, find_game, read_double, wait, write_double

SHIFT = 60  # how far to the right we try to push the crosshair (game units)
TEST_TIME = 1.5  # seconds per place
CLOSE = 0.5  # the crosshair counts as "on our value" when it's this close to it

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.write_mouse 0x2845858 0x2fde968 ...   (addresses from find_mouse)")
addresses = [int(text, 16) for text in sys.argv[1:]]

mem, regions, static_regions = attach()
pid = find_game()[0]
# attach() opens the game's memory read-only - writing needs a second door
mem_rw = os.open(f"/proc/{pid}/mem", os.O_RDWR)

find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("move the mouse a little, then LET GO of it for the whole test", 3)
card = find_aim_card(mem)
if card is None:
    raise SystemExit("no crosshair - are you in a level?")

for n, address in enumerate(addresses, 1):
    wait(f"place {n} of {len(addresses)}: {address:#x} - WATCH THE CROSSHAIR", 2)
    before = read_double(mem, address)
    aim_before = read_double(mem, card + X_OFF)
    if abs(before - aim_before) > CLOSE:
        print(f"{address:#x}: holds {before:.1f} but the crosshair is at {aim_before:.1f} - not the mouse any more, skipped")
        continue
    target = before + SHIFT
    samples = kept = followed = 0
    start = time.monotonic()
    while time.monotonic() - start < TEST_TIME:
        write_double(mem_rw, address, target)
        time.sleep(0.002)
        samples += 1
        if read_double(mem, address) == target:
            kept += 1  # our value is still there
        if abs(read_double(mem, card + X_OFF) - target) < CLOSE:
            followed += 1  # the crosshair took our value
    write_double(mem_rw, address, before)  # put it back the way it was
    print(
        f"{address:#x}: our value stayed {kept * 100 // samples:3}% of the time, "
        f"the crosshair sat on it {followed * 100 // samples:3}% of the time"
    )
    time.sleep(0.5)

print("\nWhich place moved the crosshair? What did you see on screen - did your character turn too?")
