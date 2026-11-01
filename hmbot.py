# https://github.com/Cl1ngz/HotlineMiamibot
# hmbot.py - the bot: one loop that sees, decides and acts, every frame
#
#   python hmbot.py         run until Ctrl+C
#   python hmbot.py 30      stop by itself after 30 seconds
import math
import sys
import time

from core import lockon
from core.enemies import find_aim, find_me, is_enemy, load_rules
from core.hands import KEY_SPACE, key_down, key_up, look_at, press, release
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
from core.path import find_path
from core.walls import find_walls, wall_lines

FPS = 60  # the game runs at 60 frames per second, no point going faster
SCAN_EVERY = 0.25  # seconds between the slow part: finding enemies and walls
# Enemy this cloes get hit
REACH = 35
# seconds to hold the leftbutton
HOLD = 0.15
# seconds betwen two swings
COOLDOWN = 0.25
# a lying enemy: a swing does nothing to him, SPACE finishes him
# card +0x14 of a lying enemy (-100, as read_kind/read_u32 sees it)
LYING = 0xFFFFFF9C
# stand this close (on top of him) - a guess, we'll check it with the blackbox/
EXECUTE_REACH = 35
# after SPACE you sit on him: the game hides your card (no player found) and you finish him with the LEFT button
MOUNTED_FOR = 2.0  # seconds after SPACE we keep hitting even without seeing you
# seconds between two searches for the way
REPLAN = 0.5


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
rules = load_rules()
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
    # when to let go of the button
    release_at = None
    # when to let go of SPACE
    space_up_at = None
    # until when we think you're sitting on an enemy
    mounted_until = 0
    # when to swing again
    next_swing = 0
    path, next_plan = None, 0
    while time.monotonic() < stop_at:
        now = time.monotonic()
        if release_at is not None and now >= release_at:
            release(mem, mem_rw)
            release_at = None
        if space_up_at is not None and now >= space_up_at:
            key_up(mem, mem_rw, KEY_SPACE)
            space_up_at = None

        # --- see ---
        try:
            if now >= next_scan:
                records = table_records(mem)
                enemies = {r for r in records if is_enemy(mem, r, rules)}
                lines = wall_lines(find_walls(mem, records, rules))
                next_scan = now + SCAN_EVERY
            # cards that weren't in the table last frame (someone stood up, a new enemy came in):
            # check them NOW instead of waiting for the next scan
            cards = table_cards(mem)
            for card in cards - known_cards:
                if is_enemy(mem, card, rules):
                    enemies.add(card)
            known_cards = cards
            you = find_me(mem)
            if you is None:
                raise OSError("no player found")
        except OSError as err:
            if now < mounted_until:
                # sitting on him: we can't see you, but we know what's going on - keep hitting
                if release_at is None and now >= next_swing:
                    press(mem, mem_rw)
                    release_at = now + HOLD
                    next_swing = now + COOLDOWN
                status("MOUNTED - hitting")
                time.sleep(1 / FPS)  # not 0.2 s like a pause - every frame counts here
                held = hold(mem, mem_rw, set(), held)
                continue
            lockon.reset()  # menu / new floor: forget the old target
            status(f"{err} (paused)")
            time.sleep(0.2)
            held = hold(mem, mem_rw, set(), held)
            continue

        # --- decide ---
        # only cards that are STILL enemies right now - a shell or a body drops out at once
        still_enemies = [card for card in enemies if is_enemy(mem, card, rules)]
        spots = lockon.visible_enemies(mem, still_enemies, cards, you, lines)
        target = lockon.choose_target(mem, spots, you, rules)

        # --- act ---
        if target is None:
            status("no enemy in sight")
        else:
            look_at(mem, mem_rw, spots[target])
            # if close enought? and button free? and cooldown over?
            far = math.dist(spots[target], you)
            lying = read_kind(mem, target, 0, 0x14) == LYING
            if lying:
                # on the floor: stand on him and press SPACE (like a click: hold a moment, then let go)
                if far < EXECUTE_REACH and space_up_at is None and now >= next_swing:
                    key_down(mem, mem_rw, KEY_SPACE)
                    # print(f"\nSPACE! far {far:.0f}")
                    space_up_at = now + HOLD
                    next_swing = now + COOLDOWN
                    mounted_until = now + MOUNTED_FOR
            elif far < REACH and release_at is None and now >= next_swing:
                press(mem, mem_rw)
                release_at = now + HOLD
                next_swing = now + COOLDOWN
            status(
                f"LOCKED on {'LYING' if lying else 'standing'} enemy {far:3.0f} away ({len(spots)} in sight)"
            )
        # --- walk ---
        goal = None  # where to go
        close_enough = REACH  # this close - stop walking
        target_spot = spots.get(target)
        if target_spot is not None:
            goal = target_spot
            close_enough = (
                EXECUTE_REACH if read_kind(mem, target, 0, 0x14) == LYING else REACH
            )
        else:
            hidden = where(
                mem, still_enemies, cards
            )  # every enemy, also behind the walls
            if hidden:
                goal = min(hidden.values(), key=lambda xy: math.dist(xy, you))
        keys = set()
        if goal is not None and math.dist(goal, you) > close_enough:
            if now >= next_plan:
                path = find_path(you, goal, lines)
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
    release(mem, mem_rw)
    key_up(mem, mem_rw, KEY_SPACE)
    hold(mem, mem_rw, set(), held)
    print(f"slowest loop: {slowest:.1f} ms")
