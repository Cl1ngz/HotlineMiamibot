# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/attack_write.py - can the bot START a swing by writing to memory?
#
# attack_diff showed: while you swing a bat, card +0xA0 goes 0x13 (resting) -> 0x57 (swinging),
# and the frame (+0x98) runs 0, 0.5 ... 6.5. Here we write +0xA0 = the swing number and frame = 0
# ("you're at the start of a swing") and watch what the game does with it:
#   the frame runs and +0xA0 goes back by itself at the end -> the game plays our swing
#   +0xA0 jumps back at once                                   -> the game sets it every frame, it's a "board" again
#
#   python -m helpers_for_me.attack_write 0x57        (the swing number attack_diff showed for your weapon)
#   be in a level with THAT weapon, STAND STILL, hands off the mouse - best with an enemy right in front of you
import os
import struct
import sys
import time

from core.enemies import find_me_card
from core.memory import attach, open_rw, read_double, read_u32, wait, write_double

SPRITE = 0xA0  # card +0xA0: changes when you swing
FRAME = 0x98  # card +0x98: the frame
WATCH_TIME = 1  # seconds to watch after the write

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.attack_write 0x57   (the swing number from attack_diff)")
swing = int(sys.argv[1], 16)

mem, regions, static_regions = attach()
mem_rw = open_rw()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")
print(f"your card {card:#x}: +0xA0 = {read_u32(mem, card + SPRITE):#x}, frame = {read_double(mem, card + FRAME):.2f}")

wait("hands OFF the mouse - WATCH YOUR CHARACTER (and the enemy in front of you)", 3)
os.pwrite(mem_rw, struct.pack("<I", swing), card + SPRITE)
write_double(mem_rw, card + FRAME, 0.0)

start = time.monotonic()
last = None
while time.monotonic() - start < WATCH_TIME:
    now = (read_u32(mem, card + SPRITE), read_double(mem, card + FRAME))
    if now != last:
        print(f"  {time.monotonic() - start:5.3f} s   +0xA0 = {now[0]:#x}   frame = {now[1]:.2f}")
        last = now
    time.sleep(0.002)
print("\nDid your character swing? Did the enemy in front of you die?")
