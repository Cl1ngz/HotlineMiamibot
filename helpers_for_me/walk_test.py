# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/walk_test.py - walk to the crosshair BY ITSELF: core/path.py finds the way, core/legs.py walks it
#
# Every REPLAN seconds it looks for the way again (from where you are now), and every frame it holds the keys
# toward the next point of that way. It stops when you arrive, when there's no way, or when you're stuck
# (holding keys but not moving for STUCK seconds - a wall corner, a closed door...). All keys are let go at the end.
#
#   python -m helpers_for_me.walk_test      (a level with NO enemies near - nobody fights here;
#                                            put the crosshair around a corner when told, then hands OFF)
import math
import time

from core.enemies import find_aim, find_me, load_rules
from core.hands import KEY_A, KEY_D, KEY_S, KEY_W
from core.legs import REACHED, hold, keys_toward, next_point
from core.memory import attach, open_rw, table_records, wait
from core.path import blocked_cells, find_path
from core.walls import fake_door_boxes, wall_boxes

REPLAN = 0.5  # seconds between two searches for the way
GIVE_UP = 15  # seconds
STUCK = 1.0  # seconds of holding keys without moving = stuck
ARRIVED = 2 * REACHED  # this close to the goal = there
NAMES = {KEY_W: "W", KEY_A: "A", KEY_S: "S", KEY_D: "D"}

mem, regions, static_regions = attach()
mem_rw = open_rw()
rules = load_rules()
if not rules:
    raise SystemExit("no enemy rules yet - the walls are found with them")

find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
wait("put the crosshair AROUND A CORNER (where you want to go), then hands OFF the keyboard", 4)
goal = find_aim(mem)
if goal is None or find_me(mem) is None:
    raise SystemExit("can't find you or the crosshair - are you in a level?")
records = table_records(mem)
# walls, sofas and the doors that never open
blocked = blocked_cells(wall_boxes(mem, records, rules) + fake_door_boxes(mem, records))
print(f"goal: {goal[0]:.0f},{goal[1]:.0f}")

held = set()
path = None
started = time.monotonic()
next_plan = 0
still_xy, still_since = None, started
try:
    while True:
        now = time.monotonic()
        if now - started > GIVE_UP:
            print(f"\ngave up after {GIVE_UP} s")
            break
        you = find_me(mem)
        if you is None:
            print("\nlost you (dead? new floor?)")
            break
        if math.dist(you, goal) < ARRIVED:
            print(f"\nARRIVED in {now - started:.1f} s")
            break
        if now >= next_plan:
            path = find_path(you, goal, blocked)
            next_plan = now + REPLAN
            if path is None:
                print("\nNO WAY to the crosshair")
                break
        point = next_point(path, you)
        keys = keys_toward(you, point) if point is not None else set()
        held = hold(mem, mem_rw, keys, held)
        # stuck? (we hold keys, but you don't move)
        if still_xy is None or math.dist(you, still_xy) > 2:
            still_xy, still_since = you, now
        elif held and now - still_since > STUCK:
            print(f"\nSTUCK at {you[0]:.0f},{you[1]:.0f} holding {''.join(sorted(NAMES[k] for k in held))}")
            break
        keys_text = "".join(sorted(NAMES[k] for k in held)) or "-"
        print(f"you {you[0]:4.0f},{you[1]:4.0f}  next point {point[0] if point else 0:4.0f},{point[1] if point else 0:4.0f}  keys {keys_text:3}", end="\r", flush=True)
        time.sleep(1 / 60)
finally:
    hold(mem, mem_rw, set(), held)  # let go of everything
