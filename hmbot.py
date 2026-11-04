# https://github.com/Cl1ngz/HotlineMiamibot
# hmbot.py - the bot: one loop that sees, decides and acts, every frame
#
#   python hmbot.py         run until Ctrl+C
#   python hmbot.py 30      stop by itself after 30 seconds
import faulthandler
import math
import signal
import sys
import time

from core import lockon
from core.enemies import find_aim, find_me_card, is_enemy, load_rules, shelf_cards
from core.hands import (
    KEY_SPACE,
    key_down,
    key_up,
    look_at,
    press_left,
    press_right,
    release_left,
    release_right,
)
from core.legs import hold, keys_toward, next_point
from core.memory import (
    X_OFF,
    Y_OFF,
    attach,
    open_rw,
    read_double,
    read_kind,
    table_cards,
    table_records,
)
from core.path import blocked_cells, cell_of, find_path
from core.stairs import find_car, find_stairs
from core.walls import can_see, fake_door_boxes, find_walls, wall_boxes, wall_lines
from core.weapons import find_goals, find_weapons, load_names

FPS = 60  # the game runs at 60 frames per second, no point going faster
# seconds between the slow part: finding enemies and walls
SCAN_EVERY = 0.25
# walls, sofas and fake doors never move - look for them less often
WALLS_EVERY = 2.0
# Enemy this cloes get hit
REACH = 35
# seconds to hold the leftbutton
HOLD = 0.15
# seconds betwen two swings
COOLDOWN = 0.25
# a lying enemy: a swing does nothing to him, SPACE finishes him
# card +0x10 of an enemy knocked out on the floor - only then SPACE finishes him
KNOCKED = 0x16
# stand this close (on top of him) - a guess, we'll check it with the blackbox/
EXECUTE_REACH = 35
# after SPACE you sit on him: the game hides your card (no player found) and you finish him with the LEFT button
MOUNTED_FOR = 2.0  # seconds after SPACE we keep hitting even without seeing you
# seconds between two searches for the way
REPLAN = 0.5
# your card +0xA0 when your hands are empty: at rest / punching
# (measured so far: 0x1 empty -> 0x13 after picking up the bat. Check knife, pipe, golf club with pickup!)
EMPTY_HANDS = (0x1, 0x85)
# this close to a weapon -> right click picks it up (the press test worked at 13)
GRAB_REACH = 10
# after a right click wait this long: +0xA0 changes a moment later, and a 2nd click would THROW the weapon
GRAB_COOLDOWN = 0.5
# the goal is this close and you can see it -> walk straight there, no path (the path ends in the
# MIDDLE of a 16x16 cell - up to 11 away from the weapon, too far to pick it up)
STRAIGHT = 32


def status(text):
    """One line at the bottom of the terminal that keeps being overwritten."""
    print(f"{text:60}", end="\r", flush=True)


def where(mem, cards, alive):
    """{card: (x, y)} of these cards that are still in the table - seen or behind a wall."""
    spots = {}
    for card in cards:
        if card not in alive:
            continue
        try:
            spots[card] = (
                read_double(mem, card + X_OFF),
                read_double(mem, card + Y_OFF),
            )
        except OSError:
            continue
    return spots


def choose_weapon(weapons, you, enemy_far, lines):
    """The weapon to go for, (x, y), or None.
    Only weapons you can see, and only if the nearest one is closer than the enemy (enemy_far = math.inf: no enemy).
    """
    seen = [xy for xy in weapons if can_see(you, xy, lines)]
    if not seen:
        return None
    nearest = min(seen, key=lambda xy: math.dist(xy, you))
    if math.dist(nearest, you) > enemy_far:
        return None
    return nearest


def wait_for_game(mem):
    """Wait until  you're in a level."""
    while not (find_aim(mem)):
        print(
            "waiting for  the crosshair to be visible...",
            end="\r",
            flush=True,
        )
        time.sleep(0.2)
    print()


mem, regions, static_regions = attach()
mem_rw = open_rw()
# stuck? in another terminal:  kill -USR1 $(pgrep -f hmbot.py)   -> where it is right now goes to stuck.txt
stuck_file = open("stuck.txt", "w")
faulthandler.register(signal.SIGUSR1, file=stuck_file)
rules = load_rules()
names = load_names()  # weapon frame -> {"name": ..., "kind": ...}
if not rules:
    raise SystemExit("no enemy rules yet - run python -m tools.obj_kinds first")
stop_at = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else math.inf

slowest = 0
# walking keys we hold now
held = set()
try:
    wait_for_game(mem)
    enemies, lines = set(), []
    known_cards = set()  # every card that was in the table last frame
    next_scan = 0
    next_walls = 0
    # when to let go of the button
    release_at = None
    # when to let go of SPACE
    space_up_at = None
    # until when we think you're sitting on an enemy
    mounted_until = 0
    # when to swing again
    next_swing = 0
    path, next_plan = None, 0
    stairs = None
    blocked = set()  # cells your middle can't stand in (walls and sofas)
    # (x, y) of melee weapons lying on the floor
    weapons = []
    # (x, y) of the level's things to take (the briefcase...)
    goals = []
    # (x, y) of the car when the chapter is done
    car = None

    # when to let go of the right button / when we may right click again
    right_up_at, next_grab = None, 0
    while time.monotonic() < stop_at:
        now = time.monotonic()
        if release_at is not None and now >= release_at:
            release_left(mem, mem_rw)
            release_at = None
        if space_up_at is not None and now >= space_up_at:
            key_up(mem, mem_rw, KEY_SPACE)
            space_up_at = None
        if right_up_at is not None and now >= right_up_at:
            release_right(mem, mem_rw)
            right_up_at = None

        # --- see ---
        try:
            if now >= next_scan:
                records = table_records(mem)
                enemies = {
                    r for r in shelf_cards(mem, records) if is_enemy(mem, r, rules)
                }
                if now >= next_walls:
                    lines = wall_lines(find_walls(mem, records, rules))
                    boxes = wall_boxes(mem, records, rules) + fake_door_boxes(
                        mem, records
                    )
                    blocked = blocked_cells(boxes)
                    next_walls = now + WALLS_EVERY
                stairs = find_stairs(mem, records)
                car = find_car(mem, records)
                weapons = [
                    (x, y)
                    for x, y, frame in find_weapons(mem)
                    if names.get(frame, {}).get("kind") == "melee"
                ]
                goals = find_goals(mem)
                next_scan = now + SCAN_EVERY
            # cards that weren't in the table last frame (someone stood up, a new enemy came in):
            # check them NOW instead of waiting for the next scan
            cards = table_cards(mem)
            for card in cards - known_cards:
                if is_enemy(mem, card, rules):
                    enemies.add(card)
            known_cards = cards
            me = find_me_card(mem)
            if me is None:
                raise OSError("no player found")
            you = (read_double(mem, me + X_OFF), read_double(mem, me + Y_OFF))
            hand = read_kind(mem, me, 0, 0xA0)  # what you hold (EMPTY_HANDS = nothing)
        except OSError as err:
            if now < mounted_until:
                # sitting on him: we can't see you, but we know what's going on - keep hitting
                if release_at is None and now >= next_swing:
                    press_left(mem, mem_rw)
                    release_at = now + HOLD
                    next_swing = now + COOLDOWN
                status("MOUNTED - hitting")
                time.sleep(1 / FPS)  # not 0.2 s like a pause - every frame counts here
                held = hold(mem, mem_rw, set(), held)
                continue
            lockon.reset()  # menu / new floor: forget the old target
            stairs = None  # new floor: the old stairs are not ours any more
            car = None
            next_scan = 0  # look at the new floor right away
            next_walls = 0  # a new floor: new walls right away
            status(f"{err} (paused)")
            time.sleep(0.2)
            held = hold(mem, mem_rw, set(), held)
            continue

        # --- decide ---
        # only cards that are STILL enemies right now - a shell or a body drops out at once
        still_enemies = [card for card in enemies if is_enemy(mem, card, rules)]
        alive = set(
            still_enemies
        )  # every card that is an enemy RIGHT NOW - from the table or the shelf
        spots = lockon.visible_enemies(mem, still_enemies, alive, you, lines)
        target = lockon.choose_target(mem, spots, you, rules)
        enemy_far = math.dist(spots[target], you) if target is not None else math.inf
        grab = None  # the thing we go to pick up
        if hand in EMPTY_HANDS:
            grab = choose_weapon(weapons, you, enemy_far, lines)
        if grab is None and goals and not still_enemies:
            # the floor is clear: take the level's goal, wherever it lies - the right button swaps it for the weapon
            grab = min(goals, key=lambda xy: math.dist(xy, you))

        # --- act ---
        if target is None:
            status("no enemy in sight")
        else:
            look_at(mem, mem_rw, spots[target])
            # if close enought? and button free? and cooldown over?
            far = math.dist(spots[target], you)
            lying = read_kind(mem, target, 0, 0x10) == KNOCKED
            if lying:
                # on the floor: stand on him and press SPACE (like a click: hold a moment, then let go)
                if far < EXECUTE_REACH and space_up_at is None and now >= next_swing:
                    key_down(mem, mem_rw, KEY_SPACE)
                    # print(f"\nSPACE! far {far:.0f}")
                    space_up_at = now + HOLD
                    next_swing = now + COOLDOWN
                    mounted_until = now + MOUNTED_FOR
            elif far < REACH and release_at is None and now >= next_swing:
                press_left(mem, mem_rw)
                release_at = now + HOLD
                next_swing = now + COOLDOWN
            status(
                f"LOCKED on {'LYING' if lying else 'standing'} enemy {far:3.0f} away ({len(spots)} in sight)"
            )
        if grab is not None:
            #   -> press_right, and set right_up_at and next_grab (look at the left click a few lines up)
            if (
                math.dist(grab, you) < GRAB_REACH
                and right_up_at is None
                and now >= next_grab
            ):
                press_right(mem, mem_rw)
                right_up_at = now + HOLD
                next_grab = now + GRAB_COOLDOWN
            status(f"GRABBING {math.dist(grab, you):3.0f} away")
        # --- walk ---
        goal = None  # where to go
        close_enough = REACH  # this close - stop walking
        target_spot = spots.get(target)
        if grab is not None:
            # a weapon (empty hands) or the level goal first
            goal = grab
            close_enough = GRAB_REACH
        elif target_spot is not None:
            goal = target_spot
            close_enough = (
                EXECUTE_REACH if read_kind(mem, target, 0, 0x10) == KNOCKED else REACH
            )
        else:
            # every enemy, also behind the walls
            hidden = where(mem, still_enemies, alive)
            if hidden:
                goal = min(hidden.values(), key=lambda xy: math.dist(xy, you))
                status(
                    f"HUNTING an enemy behind a wall {math.dist(goal, you):3.0f} away"
                )
            elif car is not None:
                goal = car  # the chapter is done: drive away (beats any stairs - some stay lit)
                close_enough = 0
                status(f"TO THE CAR {math.dist(goal, you):3.0f} away")
            elif stairs is not None:
                goal = stairs  # floor clear: go to GO!
                close_enough = 0
                status(f"TO THE STAIRS {math.dist(goal, you):3.0f} away")
        keys = set()
        if goal is not None and math.dist(goal, you) > close_enough:
            if math.dist(goal, you) < STRAIGHT and can_see(you, goal, lines):
                keys = keys_toward(you, goal)  # the last bit: straight there, no path
            else:
                if now >= next_plan:
                    path = find_path(you, goal, blocked)
                    next_plan = now + REPLAN
                if path is not None:
                    point = next_point(path, you)
                    if point is not None:
                        keys = keys_toward(you, point)
        held = hold(mem, mem_rw, keys, held)

        # ms spent on see + decide + act in this loop
        work = (time.monotonic() - now) * 1000
        slowest = max(slowest, work)
        if work > 1000 / FPS:
            print(f"\nslow loop: {work:.1f} ms")
        frame_end = now + 1 / FPS
        while time.monotonic() < frame_end:
            if target is not None:
                look_at(mem, mem_rw, spots[target])
            time.sleep(0.002)  # don't burn CPU while waiting for the next frame
except KeyboardInterrupt:
    pass
finally:
    print("\nbye!")
    release_left(mem, mem_rw)
    release_right(mem, mem_rw)
    key_up(mem, mem_rw, KEY_SPACE)
    hold(mem, mem_rw, set(), held)
    print(f"slowest loop: {slowest:.1f} ms")
