# https://github.com/Cl1ngz/HotlineMiamibot
# core/hands.py - the bot's hands: it aims and clicks by WRITING to the game's memory (a library)
#
# No fake mouse, no focus needed, your cursor stays yours. Everything is found through chains of links
# that start at a fixed locker inside the game file (GAME) - they still work after you die or restart.
#   [GAME] -> +0x3F4 -> +0x460  then +0x8      the look X: where your character looks (a double)
#   [GAME] -> +0x3F4 -> +0x438  then +0x8      the look Y
#   [GAME] -> +0x42C -> +0x9C   then +0x52D    the left mouse button in DirectInput (0x80 held, 0 released)
#
# hmbot uses it like this:
#   look_at(mem, mem_rw, xy)     every frame: your character looks at xy (the game puts the mouse back every frame)
#   press(mem, mem_rw)           hold the left button
#   release(mem, mem_rw)         let it go
import os

from .memory import read_u32, write_double

# a locker inside the game file: the same address after every restart
GAME = 0xBB0D68
# a chain = (the offsets to follow links through, the number to add at the very end)
LOOK_X = ([0x3F4, 0x460], 0x8)
LOOK_Y = ([0x3F4, 0x438], 0x8)
BUTTON = ([0x42C, 0x9C], 0x52D)
# DirectInput's "the button is down"
HELD = b"\x80"
RELEASED = b"\x00"


def follow(mem, chain):
    """Where a chain ends: start at GAME, follow a link through every offset, add the last number at the end."""
    offsets, last = chain
    here = read_u32(mem, GAME)
    for offset in offsets:
        here = read_u32(mem, here + offset)
    return here + last


def look_at(mem, mem_rw, xy):
    """Your character looks at xy (x, y). Call it every frame."""
    write_double(mem_rw, follow(mem, LOOK_X), xy[0])
    write_double(mem_rw, follow(mem, LOOK_Y), xy[1])


def press(mem, mem_rw):
    """Hold the left mouse button down."""
    os.pwrite(mem_rw, HELD, follow(mem, BUTTON))


def release(mem, mem_rw):
    """Let go of the left mouse button."""
    os.pwrite(mem_rw, RELEASED, follow(mem, BUTTON))
