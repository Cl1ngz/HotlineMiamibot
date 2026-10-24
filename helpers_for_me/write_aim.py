# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/write_aim.py - can the bot aim by WRITING to memory instead of moving the mouse?
#
# The crosshair card has its X at +0x50 and Y at +0x58 - so far we have only ever READ them.
#   test 1 (once): write a new X one time, then read it back for 1 s: does it stay, or does the game put it back?
#   test 2 (hold): keep writing the same X 60 times a second for 3 s: does the crosshair sit there on screen?
#
#   python -m helpers_for_me.write_aim        (be in a level, let go of the mouse when the pop-up says so)
import os
import struct
import time

from core.enemies import find_aim, find_aim_card
from core.memory import X_OFF, Y_OFF, attach, find_game, read_double, read_kind, wait

SHIFT = 60  # how far to the right to put the crosshair (game units - the screen is ~430 wide)


def write_double(mem, address, value):
    # TODO 1: turn the number into 8 bytes, little-endian (struct.pack - you used "<dd" before, this is ONE double)
    # TODO 2: write those bytes at the address (os.pwrite is the mirror of os.pread: os.pwrite(mem, the_bytes, address))
    ...
    code = struct.pack("<d", value)
    os.pwrite(mem, code, address)


def still_aim(mem, card):
    """Is this card still the crosshair? Never write into a card that has become something else."""
    try:
        return (
            read_kind(mem, card, 0, 0x14) == 0xAF
            and read_kind(mem, card, 1, 0x10) == 0xA5
        )
    except OSError:
        return False


mem, regions, static_regions = attach()
pid = find_game()[0]
# attach() opens the game's memory read-only - writing needs a second door that lets us write too
mem_rw = os.open(f"/proc/{pid}/mem", os.O_RDWR)

find_aim(
    mem
)  # warm-up: find_aim has to see the crosshair move once to tell it from a frozen copy
wait("move the mouse a little, then LET GO of it", 3)
card = find_aim_card(mem)
if card is None or not still_aim(mem, card):
    raise SystemExit("no crosshair - are you in a level?")
x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
print(f"crosshair card {card:#x} at {x:.1f}, {y:.1f}")

# test 1: write once, then watch X for one second
print(f"\ntest 1: write X = {x + SHIFT:.1f} once, then read it back")
write_double(mem_rw, card + X_OFF, x + SHIFT)
start = time.monotonic()
while time.monotonic() - start < 1:
    print(
        f"  {time.monotonic() - start:4.2f} s   X = {read_double(mem, card + X_OFF):.1f}"
    )
    time.sleep(0.1)

# test 2: keep writing for 3 seconds - watch the screen!
wait(
    f"test 2: WATCH THE GAME - the crosshair should sit {SHIFT} units to the right for 3 s",
    3,
)
start = time.monotonic()
writes = 0
while time.monotonic() - start < 3:
    if not still_aim(mem, card):
        raise SystemExit("the card stopped being the crosshair - stopped writing")
    write_double(mem_rw, card + X_OFF, x + SHIFT)
    writes += 1
    time.sleep(1 / 60)
print(f"\ntest 2: wrote {writes} times, now X = {read_double(mem, card + X_OFF):.1f}")
print(
    "What did you see? Did the crosshair stay, jump back or flicker? Did your character turn to face it?"
)
