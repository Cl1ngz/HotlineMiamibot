# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/test_hands.py - does core/hands.py work? (with the game in the background)
#
#   1. prints where the chains lead right now
#   2. your character looks RIGHT for 2 s (look_at)
#   3. one quick click (press, 0.15 s, release) - and checks by itself whether a swing started (card +0xA0)
#
#   python -m helpers_for_me.test_hands       (be in a level with a melee weapon; stay in the terminal)
import time

from core.enemies import find_me, find_me_card
from core.hands import BUTTON, LOOK_X, LOOK_Y, follow, look_at, press, release
from core.memory import attach, open_rw, read_u32, wait

SPRITE = 0xA0  # card +0xA0: leaves its resting number when a swing starts

mem, regions, static_regions = attach()
mem_rw = open_rw()
print(f"look X at {follow(mem, LOOK_X):#x}, look Y at {follow(mem, LOOK_Y):#x}, button at {follow(mem, BUTTON):#x}")

you = find_me(mem)
card = find_me_card(mem)
if you is None or card is None:
    raise SystemExit("can't find you - are you in a level?")

wait("watch your character - it should look RIGHT for 2 s", 2)
end = time.monotonic() + 2
while time.monotonic() < end:
    look_at(mem, mem_rw, (you[0] + 80, you[1]))
    time.sleep(0.002)

rest = read_u32(mem, card + SPRITE)
press(mem, mem_rw)
swung = False
end = time.monotonic() + 0.15
while time.monotonic() < end:
    look_at(mem, mem_rw, (you[0] + 80, you[1]))
    swung |= read_u32(mem, card + SPRITE) != rest
    time.sleep(0.002)
release(mem, mem_rw)
end = time.monotonic() + 0.5
while time.monotonic() < end:
    swung |= read_u32(mem, card + SPRITE) != rest
    time.sleep(0.002)
print("click:", "SWING! (to the right?)" if swung else "nothing")
