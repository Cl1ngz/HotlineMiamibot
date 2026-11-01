# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/test_keys.py - do key_down / key_up in core/hands.py work? Walk a small square by memory writes.
#
# W (up), D (right), S (down), A (left) - each held for STEP seconds. After every key it checks
# by itself that you went the right way (up = Y gets smaller, right = X gets bigger).
#
#   python -m helpers_for_me.test_keys       (be in a level with free space around you; stay in the terminal)
import time

from core.enemies import find_me
from core.hands import KEY_A, KEY_D, KEY_S, KEY_W, key_down, key_up
from core.memory import attach, open_rw, wait

STEP = 0.4  # seconds per key
MOVED = 5  # game units
# key, its name, which way you should go (dx sign, dy sign)
SQUARE = [(KEY_W, "W up", (0, -1)), (KEY_D, "D right", (1, 0)), (KEY_S, "S down", (0, 1)), (KEY_A, "A left", (-1, 0))]

mem, regions, static_regions = attach()
mem_rw = open_rw()
wait("hands OFF - your character should walk a small square: up, right, down, left", 4)

for key, name, (want_x, want_y) in SQUARE:
    before = find_me(mem)
    if before is None:
        raise SystemExit("can't find you - are you in a level?")
    key_down(mem, mem_rw, key)
    time.sleep(STEP)
    key_up(mem, mem_rw, key)
    time.sleep(0.2)
    after = find_me(mem)
    if after is None:
        raise SystemExit("lost you (dead? new floor?)")
    dx, dy = after[0] - before[0], after[1] - before[1]
    ok = (want_x == 0 or dx * want_x > MOVED) and (want_y == 0 or dy * want_y > MOVED)
    print(f"{name:8} {'OK ' if ok else 'NO!'}  moved by ({dx:+.0f}, {dy:+.0f})")
