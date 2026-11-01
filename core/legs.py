# https://github.com/Cl1ngz/HotlineMiamibot
# core/legs.py - the bot's legs: walk toward a point by holding W/A/S/D in memory (a library)
#
#   keys_toward(you, point)          which keys walk from you toward point: e.g. {KEY_W, KEY_D} = up-right
#   next_point(path, you)            the first point of the path you haven't reached yet
#   hold(mem, mem_rw, keys, held)    hold exactly these keys (presses new ones, lets go of old ones)
import math

from .hands import KEY_A, KEY_D, KEY_S, KEY_W, key_down, key_up

# closer than this on one axis -> don't press a key for that axis (no zig-zag)
DEAD_ZONE = 4
# a path point closer than this counts as reached
REACHED = 8


def keys_toward(you, point):
    """The keys that walk from you toward point, as a set."""
    dx, dy = point[0] - you[0], point[1] - you[1]
    keys = set()
    if dx > DEAD_ZONE:
        keys.add(KEY_D)
    elif dx < -DEAD_ZONE:
        keys.add(KEY_A)
    if dy > DEAD_ZONE:
        keys.add(KEY_S)
    elif dy < -DEAD_ZONE:
        keys.add(KEY_W)
    return keys


def next_point(path, you):
    """The point of the path right AFTER the one closest to you. None = you're at the end."""
    # the INDEX (0, 1, 2...) of the path point closest to you
    closest = min(range(len(path)), key=lambda i: math.dist(path[i], you))
    if closest == len(path) - 1:
        # the closest point is the last one: you're at the end
        return None
    return path[closest + 1]


def hold(mem, mem_rw, keys, held):
    """Hold exactly `keys`. `held` = what we're holding now. Returns what we hold afterwards."""
    for key in held - keys:
        key_up(mem, mem_rw, key)
    for key in keys - held:
        key_down(mem, mem_rw, key)
    return keys
