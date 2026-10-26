# https://github.com/Cl1ngz/HotlineMiamibot
# core/lockon.py - target lock: keep the crosshair on the closest enemy you can see (a library)
#
# hmbot.py uses it like this:
#   visible_enemies(mem, enemies, alive, you, lines)  every frame: who can you see right now?
#   choose_target(mem, spots, you, rules)          every frame: which one do we aim at?
#   reset()                                        forget the target (new floor, you died...)
import math
import time

from .enemies import find_aim, is_enemy
from .memory import X_OFF, Y_OFF, read_double
from .walls import can_see

# only lock on to enemies this close to you (game units; the screen is ~430 wide)
MAX_RANGE = 250
# jump to another enemy when he's closer to you than 75% of the current one's distance
SWITCH = 0.75
# an enemy can't move this far in one frame - if it "does", its memory is junk now
MAX_JUMP = 40

# kept between calls (like aim_last_xy in enemies.py): the enemy we're locked on to, and where he was
target = None
last_xy = None


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


def reset():
    """Forget the target - after a new floor, a death, the menu..."""
    global target, last_xy
    target = None
    last_xy = None
