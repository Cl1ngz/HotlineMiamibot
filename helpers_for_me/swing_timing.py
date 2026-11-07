# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/swing_timing.py - how soon after a click does the game take the NEXT swing? (one weapon per run)
#
# What the blackbox showed: one bat swing shows hand 0x57 for ~0.2 s, and a click 0.26 s after the last one
# did NOTHING (hand stayed 0x13) - so hmbot's COOLDOWN = 0.25 is too short, and the 2nd enemy got us.
# This finds the real number: two clicks with a growing gap between them, and it watches your hand (+0xA0):
# did a 2nd swing come or not?
#
#   python -m helpers_for_me.swing_timing              clicks hold the button 0.05 s
#   python -m helpers_for_me.swing_timing --hold 0.15  ...or as long as hmbot holds it (HOLD)
#
# Stand somewhere SAFE (no enemy near - you swing at the air), with the weapon to measure (empty hands = punches).
# Bot OFF, hands off the mouse. Then pick up another weapon and run it again - one line of result per weapon.
import sys
import time

from core.enemies import find_me_card
from core.hands import press_left, release_left
from core.memory import attach, open_rw, read_u32, wait

HAND = 0xA0  # your card: the sprite = what you hold / what you're doing
HOLD = float(sys.argv[sys.argv.index("--hold") + 1]) if "--hold" in sys.argv else 0.05
GAPS = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60)  # seconds between the two clicks
REPEAT = 3  # every gap this many times (one lucky try proves nothing)
REST = 0.4  # before a try your hand must be at rest this long
SAMPLE = 0.001  # look at the hand every millisecond


def hand():
    return read_u32(mem, me + HAND)


def wait_rest():
    """Wait until your hand has been at rest (the starting sprite) for REST seconds."""
    since = time.monotonic()
    give_up = since + 5
    while time.monotonic() - since < REST:
        if hand() != idle:
            since = time.monotonic()
        if time.monotonic() > give_up:
            raise SystemExit(f"your hand doesn't come back to {idle:#x} - did you pick something up / die?")
        time.sleep(SAMPLE)


def watch(clicks):
    """Click at these moments (seconds from now) and watch the hand until it's at rest again.
    Returns the busy runs [(from, to), ...] - the times your hand was NOT at rest - and the sprites seen."""
    start = time.monotonic()
    todo = sorted(clicks)
    release_at = None
    runs, busy, sprites = [], None, set()
    while True:
        t = time.monotonic() - start
        if todo and t >= todo[0]:
            press_left(mem, mem_rw)
            release_at = t + HOLD
            todo.pop(0)
        if release_at is not None and t >= release_at:
            release_left(mem, mem_rw)
            release_at = None
        now_hand = hand()
        if now_hand != idle:
            sprites.add(now_hand)
            if busy is None:
                busy = [t, t]
            busy[1] = t
        elif busy is not None:
            runs.append(tuple(busy))
            busy = None
        done = not todo and release_at is None and busy is None
        if (done and t > max(clicks) + 0.3) or t > 5:
            break
        time.sleep(SAMPLE)
    if busy is not None:
        runs.append(tuple(busy))
    return runs, sprites


mem, regions, static_regions = attach()
mem_rw = open_rw()
me = find_me_card(mem)
if me is None:
    raise SystemExit("no player found - stand in a level")
idle = hand()
print(f"your hand at rest: {idle:#x}   (clicks hold the button {HOLD:.2f} s)")
wait("swing test: stand still, hands OFF the mouse", 3)
try:
    # 1) one click: how long is one swing?
    wait_rest()
    runs, sprites = watch([0])
    if not runs:
        raise SystemExit("one click did nothing - is the game paused / not focused on a level?")
    one = runs[0][1] - runs[0][0]
    print(f"one swing: {one:.3f} s  (the hand shows {', '.join(hex(s) for s in sorted(sprites))}, then {idle:#x} again)")

    # 2) two clicks with a growing gap: did the 2nd one swing?
    #    a 2nd swing = a 2nd busy run, or one run much longer than one swing (no rest between the two)
    print(f"\ntwo clicks, {REPEAT} tries per gap:")
    works = {}
    for gap in GAPS:
        hits = 0
        for _ in range(REPEAT):
            wait_rest()
            runs, sprites = watch([0, gap])
            busy_time = sum(to - frm for frm, to in runs)
            if len(runs) >= 2 or busy_time > 1.5 * one:
                hits += 1
        works[gap] = hits
        print(f"  gap {gap:.2f} s:  2nd swing {hits}/{REPEAT}  {'#' * hits}")
finally:
    release_left(mem, mem_rw)

# the smallest gap from which EVERY bigger gap worked every time
safe = None
for gap in reversed(GAPS):
    if works[gap] < REPEAT:
        break
    safe = gap
if safe is None:
    print(f"\n=> {idle:#x}: even {GAPS[-1]:.2f} s wasn't always enough - tell Claude")
else:
    print(f"\n=> {idle:#x}: the next click works {safe:.2f} s after the last one (one swing {one:.2f} s)")
