# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/click_write.py - which 0x80 byte makes your character really SWING?
#
# find_click 0x80 found bytes that are 0x80 while you hold the left button and 0 when you let go.
# One of them may be DirectInput's own copy of the mouse - the one the game reads every frame.
# For each place: write 0x80 ("held") for a short moment, then 0 ("released") - like a quick click.
# The bot checks by itself whether a swing started: card +0xA0 leaves its resting number (0x13 with a bat).
#
#   python -m helpers_for_me.click_write 0x181cc29 0x7b6003b 0x7bd003b ...     (the places from find_click 0x80)
#   be in a level with a melee weapon, somewhere safe. The GAME must be focused (switch to it with the
#   keyboard, NOT by clicking) and don't touch the mouse during the test.
import os
import sys
import time

from core.enemies import find_me_card
from core.memory import attach, open_rw, read_u32, wait

SPRITE = 0xA0  # card +0xA0: leaves its resting number when a swing starts
HOLD = 0.15  # seconds of "held"
AFTER = 0.5  # seconds to watch after letting go

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.click_write 0x181cc29 0x7b6003b ...   (from find_click 0x80)")
places = [int(text, 16) for text in sys.argv[1:]]

mem, regions, static_regions = attach()
mem_rw = open_rw()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")
rest = read_u32(mem, card + SPRITE)
print(f"your card {card:#x}, +0xA0 at rest = {rest:#x}")

wait("switch to the GAME with the keyboard (no clicking!) and let go of the mouse", 4)
for n, place in enumerate(places, 1):
    if os.pread(mem, 1, place)[0] != 0:
        print(f"{place:#x}: not 0 right now - skipped")
        continue
    swung = False
    end = time.monotonic() + HOLD
    while time.monotonic() < end:  # "held"
        os.pwrite(mem_rw, b"\x80", place)
        swung |= read_u32(mem, card + SPRITE) != rest
        time.sleep(0.002)
    os.pwrite(mem_rw, b"\x00", place)  # "released"
    end = time.monotonic() + AFTER
    while time.monotonic() < end:
        swung |= read_u32(mem, card + SPRITE) != rest
        time.sleep(0.002)
    print(f"{place:#x}: {'SWING!' if swung else 'nothing'}")
    time.sleep(0.5)
