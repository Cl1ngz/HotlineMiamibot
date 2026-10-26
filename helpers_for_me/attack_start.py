# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/attack_start.py - start a swing by writing ALL three things a real swing has
#
# watch_values showed one real swing with a bat:
#   card +0xA0       0x13 -> 0x57        (the swing number)
#   frame (+0x98)    1.0, 1.7, 2.4 ... 8.7
#   0x2fe1308        0 -> 0.7 for the whole swing, back to 0 when it ends
# attack_write only wrote the first two and nothing happened. Here we write all three at once,
# then watch what the game does with them (until the swing should be over).
#
#   python -m helpers_for_me.attack_start 0x57 0x2fe1308 0.7     (swing number, the speed place, its swing value)
#   python -m helpers_for_me.attack_start 0x57 0x2fe1308 0.05    (the same in slow motion: ~2.5 s instead of 0.2 s)
#   be in a level with THAT weapon, STAND STILL, hands off the mouse - best with an enemy right in front of you
import os
import struct
import sys
import time

from core.enemies import find_me_card
from core.memory import attach, open_rw, read_double, read_u32, wait, write_double

SPRITE = 0xA0  # card +0xA0
FRAME = 0x98  # card +0x98
FIRST_FRAME = 1.0  # a real bat swing started at frame 1.0
LAST_FRAME = 8.8  # ...and ended after frame 8.7

if len(sys.argv) < 4:
    raise SystemExit("usage: python -m helpers_for_me.attack_start 0x57 0x2fe1308 0.7")
swing = int(sys.argv[1], 16)
speed_address = int(sys.argv[2], 16)
speed = float(sys.argv[3])
# a smaller speed = slow motion. Watch until the swing should be over, plus half a second (the game runs 60 frames/s)
WATCH_TIME = max(1, (LAST_FRAME - FIRST_FRAME) / speed / 60 + 0.5)

mem, regions, static_regions = attach()
mem_rw = open_rw()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")


def state():
    return read_u32(mem, card + SPRITE), read_double(mem, card + FRAME), read_double(mem, speed_address)


sprite, frame, now_speed = state()
print(f"before: +0xA0 = {sprite:#x}   frame = {frame:.2f}   speed = {now_speed:.3f}")
if sprite == swing or now_speed != 0:
    raise SystemExit("you're not at rest (or +0xA0 got stuck from an old test) - swing once by hand, then run again")

wait("hands OFF the mouse - WATCH YOUR CHARACTER (and the enemy in front of you)", 3)
write_double(mem_rw, speed_address, speed)
write_double(mem_rw, card + FRAME, FIRST_FRAME)
os.pwrite(mem_rw, struct.pack("<I", swing), card + SPRITE)

start = time.monotonic()
last = None
while time.monotonic() - start < WATCH_TIME:
    now = state()
    if now != last:
        print(f"  {time.monotonic() - start:5.3f} s   +0xA0 = {now[0]:#x}   frame = {now[1]:5.2f}   speed = {now[2]:.3f}")
        last = now
    time.sleep(0.002)
print("\nDid your character swing? Did the enemy in front of you die? (If +0xA0 is stuck on the swing, swing once by hand.)")
