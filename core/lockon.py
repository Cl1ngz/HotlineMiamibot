# https://github.com/Cl1ngz/HotlineMiamibot
# core/lockon.py - target lock: keep the crosshair on the closest enemy you can see (a library)
#
# hmbot.py uses it like this:
#   calibrate(mem)                                 once at the start: game units per mouse count
#   visible_enemies(mem, enemies, alive, you, lines)  every frame: who can you see right now?
#   choose_target(mem, spots, you, rules)          every frame: which one do we aim at?
#   aim_at(enemy_xy, aim, scales)                  every frame: one small mouse step toward him
#   reset()                                        forget the target (new floor, you died...)
import math
import time

from . import fakemouse
from .enemies import find_aim, is_enemy
from .memory import X_OFF, Y_OFF, read_double
from .walls import can_see

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

# kept between calls (like aim_last_xy in enemies.py): the enemy we're locked on to, and where he was
target = None
last_xy = None


def calibrate(mem):
    """Nudge the fake mouse and watch the crosshair: (game units per mouse count sideways, up/down)."""
    # warm-up: find_aim has to see the crosshair move once to tell it from a frozen copy
    find_aim(mem)
    fakemouse.move(20, 0)
    time.sleep(0.1)
    find_aim(mem)
    fakemouse.move(-20, 0)
    time.sleep(0.1)

    scales = []
    for dx, dy in ((100, 0), (0, 100)):
        before = find_aim(mem)
        # 5 small moves, like a hand would do it (one big jump gets sped up by mouse acceleration)
        for _ in range(5):
            fakemouse.move(dx // 5, dy // 5)
            time.sleep(0.01)
        time.sleep(0.1)
        after = find_aim(mem)
        # put it back the same way
        for _ in range(5):
            fakemouse.move(-dx // 5, -dy // 5)
            time.sleep(0.01)
        time.sleep(0.2)
        if before is None or after is None:
            raise RuntimeError(
                "lost the crosshair while calibrating - are you in a level?"
            )
        moved = after[0] - before[0] if dx else after[1] - before[1]
        scales.append(moved / 100)
    if min(abs(s) for s in scales) < 0.005:
        # a library doesn't quit the program - it reports the problem and hmbot decides what to do
        raise RuntimeError(
            "the crosshair didn't follow the fake mouse - was the game focused the whole time?"
        )
    return scales


def visible_enemies(mem, enemies, alive, you, lines):
    """{card: (x, y)} of the enemies still in the table, close to you and not behind a wall."""
    spots = {}
    for card in enemies:
        if card not in alive:
            # the game deleted it, its memory is junk now
            continue
        try:
            xy = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        except OSError:
            continue
        if math.dist(xy, you) < MAX_RANGE and can_see(you, xy, lines):
            spots[card] = xy
    return spots


def choose_target(mem, spots, you, rules):
    """Keep the current target, or switch to a clearly closer one. Returns his card, or None."""
    global target, last_xy
    # drop the target if he died, vanished, went behind a wall or teleported (junk memory)
    if target is not None:
        if target not in spots or not is_enemy(mem, target, rules):
            target = None
        elif math.dist(spots[target], last_xy) > MAX_JUMP:
            target = None
    # the closest enemy to YOU wins. Keep the current one unless another is clearly closer
    # (otherwise the aim would flick back and forth between two guys at about the same distance)
    if spots:
        closest = min(spots, key=lambda card: math.dist(spots[card], you))
        if target is None or math.dist(spots[closest], you) < SWITCH * math.dist(
            spots[target], you
        ):
            target = closest
    if target is not None:
        last_xy = spots[target]
    return target


def aim_at(enemy_xy, aim, scales):
    """One small mouse step from the crosshair toward the enemy. Returns how far off the crosshair still is."""
    scale_x, scale_y = scales
    # the gap between crosshair and enemy, turned into mouse counts (only GAIN of it per frame)
    gap_x, gap_y = enemy_xy[0] - aim[0], enemy_xy[1] - aim[1]
    dx = max(-MAX_STEP, min(MAX_STEP, round(gap_x / scale_x * GAIN)))
    dy = max(-MAX_STEP, min(MAX_STEP, round(gap_y / scale_y * GAIN)))
    if dx or dy:
        fakemouse.move(dx, dy)
    return math.hypot(gap_x, gap_y)


def reset():
    """Forget the target - after a new floor, a death, the menu..."""
    global target, last_xy
    target = None
    last_xy = None
