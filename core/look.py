# https://github.com/Cl1ngz/HotlineMiamibot
# core/look.py - where your character looks (a library)
#
# The game keeps "where your character looks" as two doubles: look X, and look Y GAP bytes BEFORE it.
# Every frame the game copies the mouse in there - but if the bot keeps writing its own point,
# your character turns to it (and swings / shoots there), even when the game isn't focused.
# The crosshair on screen doesn't move - it reads the mouse from somewhere else.
#
# hmbot uses it like this:
#   find_look(mem, regions, aim)    once: the address of look X (or None)
#   look_at(mem_rw, look, xy)       every frame: make your character look at xy
import numpy as np

from .memory import read_double, take_snapshot, write_double

GAP = 0x50  # look Y lies GAP bytes BEFORE look X

# so another PC / Proton version may put it somewhere else: always check it before trusting it
KNOWN = 0x2845858


def is_look(mem, address, aim):
    """Does this address hold the crosshair's X, and GAP bytes before it the crosshair's Y?"""
    try:
        return (
            read_double(mem, address) == aim[0]
            and read_double(mem, address - GAP) == aim[1]
        )
    except OSError:
        return False


def find_look(mem, regions, aim):
    """Address of look X, or None. aim = (x, y) of the crosshair right now (hold the mouse still!)."""
    if is_look(mem, KNOWN, aim):
        return KNOWN
    found = []
    for start, data in take_snapshot(mem, regions).items():
        for shift in (0, 4):
            count = (len(data) - shift) // 8
            values = np.frombuffer(data[shift : shift + count * 8], dtype="<d")
            for i in np.flatnonzero(values == aim[0]):
                address = start + shift + i * 8
                if is_look(mem, address, aim):
                    found.append(address)
    if len(found) == 1:
        return found[0]
    return None


def look_at(mem_rw, look, xy):
    """Make your character look at xy. Call it every frame - the game puts the mouse back every frame."""
    write_double(mem_rw, look, xy[0])
    write_double(mem_rw, look - GAP, xy[1])
