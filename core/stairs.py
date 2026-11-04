# https://github.com/Cl1ngz/HotlineMiamibot
# core/stairs.py - where to go when there's nobody left: the stairs with GO! on them, or the car
#
# What go_diff showed: GO! is NOT a new card. The stairs card (+0x10 = 0x51, in the table) is there
# the whole time, and when the last enemy dies two spots inside it flip:
#     +0x48: 1 -> 0        +0x90: 0 -> 1
# The car (floor layer, folder picture 0xd7) changes its picture to 0xd9 when the chapter is done.
from .enemies import shelf_cards
from .memory import X_OFF, Y_OFF, read_double, read_kind

STAIRS = 0x51  # card +0x10 of the stairs object
OPEN_OFF = 0x90  # card +0x90 says "GO! is on"...
OPEN = 1  # ...when it holds 1
# folder picture of the car when the game says "run to the car" (0xd7 before)
CAR_READY = 0xD9
FLOOR = 0xFFFFFF9C


def find_stairs(mem, records):
    """(x, y) of the stairs with GO! on, or None (enemies still alive / no stairs on this floor)."""
    for card in records:
        try:
            if (
                read_kind(mem, card, 0, 0x10) != STAIRS
                or read_kind(mem, card, 0, OPEN_OFF) != OPEN
            ):
                continue
            return read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        except OSError:
            continue  # junk / the floor is loading
    return None


def find_car(mem, records):
    """(x, y) of the car when the chapter is done, or None (not done yet / no car on this floor).
    From the whole shelf: at the end of a level the car card is sometimes not in the table.
    """
    for card in shelf_cards(mem, records):
        try:
            if (
                read_kind(mem, card, 1, 0x10) == CAR_READY
                and read_kind(mem, card, 0, 0x14) == FLOOR
            ):
                return read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        except OSError:
            continue  # junk / the floor is loading
    return None
