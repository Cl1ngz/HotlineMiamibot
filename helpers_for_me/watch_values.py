# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/watch_values.py - watch some doubles next to your swing (+0xA0) and frame, over time
#
# find_attack leaves a few places that are one thing at rest and another while swinging.
# This shows HOW they change: do they jump when you click? count down? go back to rest when the swing ends?
# A line is printed every time anything changes.
#
#   python -m helpers_for_me.watch_values 0x2fe1308 0x132e028 0x9c1fdd8     (any addresses, doubles)
#   be in a level with your weapon, stand still, swing a few times WITH PAUSES
import sys
import time

from core.enemies import find_me_card
from core.memory import attach, read_double, read_u32, wait

SPRITE = 0xA0
FRAME = 0x98
WATCH_TIME = 5  # seconds

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.watch_values 0x2fe1308 0x132e028 ...   (addresses of doubles)")
addresses = [int(text, 16) for text in sys.argv[1:]]

mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")


def peek(address):
    try:
        return f"{read_double(mem, address):8.3f}"
    except OSError:
        return "     ???"


print("time      +0xA0  frame  " + "".join(f"{address:>11x}" for address in addresses))
wait("stand still - swing a few times WITH PAUSES", 3)
start = time.monotonic()
last = None
while time.monotonic() - start < WATCH_TIME:
    now = (f"{read_u32(mem, card + SPRITE):#6x}", f"{read_double(mem, card + FRAME):5.2f}", *(peek(a) for a in addresses))
    if now != last:
        print(f"{time.monotonic() - start:5.2f} s  {now[0]}  {now[1]}  " + "".join(f"{value:>11}" for value in now[2:]))
        last = now
    time.sleep(0.005)
