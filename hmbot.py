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
from core.hands import look_at, press, release
from core.memory import attach, open_rw, table_cards, table_records
from core.walls import find_walls, wall_lines

FPS = 60  # the game runs at 60 frames per second, no point going faster
SCAN_EVERY = 0.25  # seconds between the slow part: finding enemies and walls
# Enemy this cloes get hit
REACH = 35
# seconds to hold the leftbutton
HOLD = 0.15
# seconds betwen two swings
COOLDOWN = 0.4


def status(text):
    """One line at the bottom of the terminal that keeps being overwritten."""
    print(f"{text:60}", end="\r", flush=True)


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

try:
    wait_for_game(mem)
    enemies, lines = [], []
    next_scan = 0
    # when to let go of the button
    release_at = None
    # when to swing again
    next_swing = 0
    while time.monotonic() < stop_at:
        now = time.monotonic()

        # --- see ---
        try:
            if now >= next_scan:
                records = table_records(mem)
                enemies = [r for r in records if is_enemy(mem, r, rules)]
                lines = wall_lines(find_walls(mem, records, rules))
                next_scan = now + SCAN_EVERY
            you = find_me(mem)
            aim = find_aim(mem)
            if aim is None:
                raise OSError("no crosshair found")
            if you is None:
                raise OSError("no player found")
        except OSError as err:
            lockon.reset()  # menu / new floor: forget the old target
            status(f"{err} (paused)")
            time.sleep(0.2)
            continue

        # --- decide ---
        spots = lockon.visible_enemies(mem, enemies, table_cards(mem), you, lines)
        target = lockon.choose_target(mem, spots, you, rules)

        # --- act ---
        if target is None:
            status("no enemy in sight")
        else:
            look_at(mem, mem_rw, spots[target])
            # if close enought? and button free? and cooldown over?
            far = math.dist(spots[target], you)
            if (
                far < REACH
                and (release_at is None or now >= release_at)
                and now >= next_swing
            ):
                press(mem, mem_rw)
                release_at = now + HOLD
                next_swing = now + COOLDOWN

            status(f"LOCKED on enemy {far:3.0f} away ({len(spots)} in sight)")
        if release_at is not None and now >= release_at:
            release(mem, mem_rw)
            release_at = None

        # time.sleep(1 / FPS)
        frame_end = now + 1 / FPS
        while time.monotonic() < frame_end:
            if target is not None:
                look_at(mem, mem_rw, spots[target])
            time.sleep(0.002)  # don't burn CPU while waiting for the next frame
except KeyboardInterrupt:
    pass
finally:
    print("\nbye!")
