# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/attack_watch.py - what happens to YOUR card while you swing a weapon?
#
# Watches your card every 5 ms and prints a line every time the layer, the picture or the frame changes.
# The card is found BEFORE the attack and then watched by its address: find_me looks for picture 0x47,
# and if the picture changes while you swing, find_me would lose you mid-attack.
#
#   python -m helpers_for_me.attack_watch
#   be in a level with a MELEE weapon (bat, pipe...), STAND STILL, then click to swing at the air a few times
import time

from core.enemies import find_me_card
from core.memory import attach, read_double, read_kind, wait

WATCH_TIME = 5  # seconds
FRAME = 0x98  # the frame number on the card (which page of the picture)

mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level (and not attacking right now)?")
print(f"your card: {card:#x}")

wait("STAND STILL with a melee weapon, then SWING at the air a few times (click, wait, click...)", 3)
start = time.monotonic()
last = None
while time.monotonic() - start < WATCH_TIME:
    try:
        now = (read_kind(mem, card, 0, 0x14), read_kind(mem, card, 1, 0x10), read_double(mem, card + FRAME))
    except OSError:
        now = None
    if now != last:
        if now is None:
            print(f"  {time.monotonic() - start:5.2f} s   can't read the card any more")
        else:
            layer, picture, frame = now
            print(f"  {time.monotonic() - start:5.2f} s   layer {layer:#6x}   picture {picture:#6x}   frame {frame:6.2f}")
        last = now
    time.sleep(0.005)
print("\nWhich picture is the swing? How do the frames run during one swing (start, end, step)?")
