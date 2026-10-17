# https://github.com/Cl1ngz/HotlineMiamibot
# hmbot.py - the bot: one loop that sees, decides and acts, every frame
#
#   python hmbot.py         run until Ctrl+C
#   python hmbot.py 30      stop by itself after 30 seconds
import math
import sys
import time

from core import fakemouse, lockon
from core.enemies import find_aim, find_me, is_enemy, load_rules
from core.game import game_focused
from core.memory import attach, table_cards, table_records
from core.walls import find_walls, wall_lines

FPS = 60  # the game runs at 60 frames per second, no point going faster
SCAN_EVERY = 0.25  # seconds between the slow part: finding enemies and walls
FOCUS_EVERY = 0.25  # seconds between asking Hyprland which window has focus


def status(text):
    """One line at the bottom of the terminal that keeps being overwritten."""
    print(f"{text:60}", end="\r", flush=True)


def wait_for_game(mem):
    """Wait until the game is focused and you're in a level."""
    while not (game_focused() and find_aim(mem)):
        print(
            "waiting for the game to be focused and the crosshair to be visible...",
            end="\r",
            flush=True,
        )
        time.sleep(0.2)
    print()


mem, regions, static_regions = attach()
rules = load_rules()
if not rules:
    raise SystemExit("no enemy rules yet - run python -m tools.obj_kinds first")
stop_at = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else math.inf

fakemouse.start()
try:
    wait_for_game(mem)
    try:
        scales = lockon.calibrate(mem)
    except RuntimeError as err:
        raise SystemExit(f"calibration failed: {err}")
    print(
        f"1 mouse count = {scales[0]:.3f} game units sideways, {scales[1]:.3f} up/down. Locking!"
    )

    enemies, lines = [], []
    next_scan = next_focus = 0
    focused = True
    while time.monotonic() < stop_at:
        now = time.monotonic()

        # --- is the game in front? ---
        if now >= next_focus:
            focused = game_focused()
            next_focus = now + FOCUS_EVERY
        if not focused:
            print("paused (game not focused)                    ", end="\r", flush=True)
            time.sleep(0.1)
            continue

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
            off = lockon.aim_at(spots[target], aim, scales)
            far = math.dist(spots[target], you)
            status(
                f"LOCKED on enemy {far:3.0f} away ({len(spots)} in sight), crosshair {off:5.1f} off"
            )
        time.sleep(1 / FPS)
except KeyboardInterrupt:
    pass
finally:
    fakemouse.stop()
    print("\nbye!")
