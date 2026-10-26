# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/attack_objects.py - does a swing CREATE a new object?
#
# Writing the swing number, the frame and the speed played "something", but not a real swing.
# Maybe the real swing (and the hit) is a SEPARATE object the game creates when you click - like a short-lived
# "hit box" next to you. If so, a new card shows up in the table with every swing.
#   1 s at rest:   learn which cards come and go by themselves (so they don't count)
#   then swinging: print every NEW card that shows up - when, its layer and picture, how far from you
#
#   python -m helpers_for_me.attack_objects
#   be in a level with a melee weapon, somewhere SAFE (no enemies around), stand still and follow the pop-ups
import math
import time

from core.enemies import find_me_card
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_cards, wait

REST_TIME = 1.5  # seconds of learning what comes and goes by itself
WATCH_TIME = 6  # seconds of swinging

mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")
you = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))

wait("STAND STILL and DON'T click", 2)
known = set()
start = time.monotonic()
while time.monotonic() - start < REST_TIME:
    known |= table_cards(mem)
    time.sleep(0.005)
print(f"{len(known)} cards in the table at rest")

wait("now SWING a few times - with pauses between swings", 2)
seen = {}
start = time.monotonic()
while time.monotonic() - start < WATCH_TIME:
    for new in table_cards(mem) - known:
        if new in seen:
            continue
        try:
            layer = read_kind(mem, new, 0, 0x14)
            picture = read_kind(mem, new, 1, 0x10)
            xy = (read_double(mem, new + X_OFF), read_double(mem, new + Y_OFF))
        except OSError:
            continue
        seen[new] = (time.monotonic() - start, layer, picture, math.dist(xy, you))
    time.sleep(0.002)

if not seen:
    print("no new cards while swinging - the swing doesn't create objects")
for new, (when, layer, picture, distance) in sorted(seen.items(), key=lambda item: item[1][0]):
    print(f"  {when:5.2f} s   card {new:#x}   layer {layer:#10x}   picture {picture:#6x}   {distance:6.1f} from you")
