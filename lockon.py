# https://github.com/Cl1ngz/HotlineMiamibot
# target lock bot keeps your crosshair on the closest enemy you can see
#
# Every frame it reads where you, the crosshair and the enemies are, and nudges a fake mouse
# toward the closest enemy that has no wall between you - like your hand would, just faster.
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

import fakemouse
from enemies import is_enemy, load_rules
from memory import (
    TABLE_END,
    TABLE_START,
    X_OFF,
    Y_OFF,
    attach,
    follow,
    load_address,
    read_double,
    table_records,
)
from walls import can_see, find_walls, wall_lines

# how much of the gap to close each frame (1.0 = all at once, lower = smoother)
GAIN = 0.5
# only lock on to enemies this close to you (game units; the screen is ~430 wide)
MAX_RANGE = 250
# jump to another enemy when he's closer to you than 75% of the current one's distance
SWITCH = 0.75
# an enemy can't move this far in one frame - if it "does", its memory is junk now
MAX_JUMP = 40
# biggest single mouse move (mouse counts) - bigger moves get sped up by mouse acceleration and overshoot
MAX_STEP = 80
# the game runs at 60 frames per second, no point going faster
FPS = 60

mem, regions, static_regions = attach()
PLAYER = load_address("player")
CROSSHAIR = load_address("crosshair")
Y_OFFSET = load_address("y_offset")
rules = load_rules()
if not rules:
    raise SystemExit("no enemy rules yet - run python obj_kinds.py first")
stop_at = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else math.inf


# ask Hyprl which window has focus True if its Hotline Miami
def game_focused():
    try:
        out = subprocess.run(
            ["hyprctl", "activewindow", "-j"], capture_output=True, text=True
        ).stdout
        window = json.loads(out)
    except (OSError, ValueError):
        return False
    name = f"{window.get('class', '')} {window.get('title', '')}".lower()
    return "hotline" in name or "219150" in name  # 219150 = the game's Steam id


def read_xy(path):
    x_addr = follow(mem, path)
    x, y = read_double(mem, x_addr), read_double(mem, x_addr + Y_OFFSET)
    if not (0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000):
        raise OSError("garbage position")  # menu / loading screen
    return x, y


# Every record the table points to right now (one quick read: 'is this object still alive?').
def objects_in_table():
    data = os.pread(mem, TABLE_END - TABLE_START, TABLE_START)
    return set(np.frombuffer(data, dtype="<u4").tolist())


# Nudge the fake mouse and watch the crosshair: how many game units is one mouse count?
def calibrate():
    scales = []
    for dx, dy in ((100, 0), (0, 100)):
        before = read_xy(CROSSHAIR)
        # 5 small moves, like a hand would do it
        for _ in range(5):
            fakemouse.move(dx // 5, dy // 5)
            time.sleep(0.01)
        time.sleep(0.1)
        after = read_xy(CROSSHAIR)
        # put it back the same way speed up would do mess
        for _ in range(5):
            fakemouse.move(-dx // 5, -dy // 5)
            time.sleep(0.01)
        time.sleep(0.2)
        moved = after[0] - before[0] if dx else after[1] - before[1]
        scales.append(moved / 100)
    if min(abs(s) for s in scales) < 0.005:
        raise SystemExit(
            "the crosshair didn't follow the fake mouse - was the game focused the whole time?"
        )
    return scales


fakemouse.start()
print("Switch to the game and stand still (calibrating the mouse)...")
while not game_focused():
    time.sleep(0.2)
time.sleep(0.5)
scale_x, scale_y = calibrate()
print(
    f"1 mouse count = {scale_x:.3f} game units sideways, {scale_y:.3f} up/down. Locking!"
)

# records of living enemies (refreshed 4 times a second, it's the slow part)
enemies = []
# wall lines (refreshed together with the enemies)
lines = []
# the record we're locked on to
target = None
# where the target was last frame
last_xy = None
next_scan = next_focus_check = 0
focused = True
try:
    while time.monotonic() < stop_at:
        now = time.monotonic()
        if now >= next_focus_check:
            focused = game_focused()
            next_focus_check = now + 0.25
        if not focused:
            print("paused (game not focused)                    ", end="\r", flush=True)
            time.sleep(0.1)
            continue

        try:
            if now >= next_scan:
                records = table_records(mem)
                enemies = [r for r in records if is_enemy(mem, r, rules)]
                lines = wall_lines(find_walls(mem, records, rules))
                next_scan = now + 0.25
            you = read_xy(PLAYER)
            aim = read_xy(CROSSHAIR)
        except OSError:
            print("not in a level                               ", end="\r", flush=True)
            time.sleep(0.2)
            continue

        # where is every enemy right now? (only the ones still in the table, close to you, not behind a wall)
        alive = objects_in_table()
        spots = {}
        for r in enemies:
            if r not in alive:
                continue  # the game deleted it, its memory is junk now
            try:
                xy = read_double(mem, r + X_OFF), read_double(mem, r + Y_OFF)
            except OSError:
                continue
            if math.dist(xy, you) < MAX_RANGE and can_see(you, xy, lines):
                spots[r] = xy

        # drop the target if it died, vanished, went behind a wall or teleported (junk memory)
        if target is not None:
            if target not in spots or not is_enemy(mem, target, rules):
                target = None  # dead, gone, or behind a wall now
            elif math.dist(spots[target], last_xy) > MAX_JUMP:
                target = None  # junk position

        # the closest enemy to YOU wins. Keep the current one unless another is clearly closer
        # (otherwise the aim would flick back and forth between two guys at about the same distance)
        if spots:
            closest = min(spots, key=lambda r: math.dist(spots[r], you))
            if target is None or math.dist(spots[closest], you) < SWITCH * math.dist(
                spots[target], you
            ):
                target = closest
        if target is None:
            print(
                "no enemy in sight                              ", end="\r", flush=True
            )
            time.sleep(1 / FPS)
            continue
        last_xy = spots[target]

        # the gap between crosshair and enemy, turned into mouse counts
        gap_x, gap_y = spots[target][0] - aim[0], spots[target][1] - aim[1]
        dx = max(-MAX_STEP, min(MAX_STEP, round(gap_x / scale_x * GAIN)))
        dy = max(-MAX_STEP, min(MAX_STEP, round(gap_y / scale_y * GAIN)))
        if dx or dy:
            fakemouse.move(dx, dy)
        far = math.dist(spots[target], you)
        print(
            f"LOCKED on enemy {far:3.0f} away ({len(spots)} in sight), crosshair {math.hypot(gap_x, gap_y):5.1f} off  ",
            end="\r",
            flush=True,
        )
        time.sleep(1 / FPS)
except KeyboardInterrupt:
    pass
finally:
    fakemouse.stop()
    print("\nlock off, bye!")
