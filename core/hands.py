# https://github.com/Cl1ngz/HotlineMiamibot
# core/hands.py - the bot's hands: it aims and clicks by WRITING to the game's memory (a library)
#
# No fake mouse, no focus needed, your cursor stays yours. Everything is found through chains of links
# that start at a fixed locker inside the game file (GAME) - they still work after you die or restart.
#   [GAME] -> +0x3F4 -> +0x460  then +0x8      the look X: where your character looks (a double)
#   [GAME] -> +0x3F4 -> +0x438  then +0x8      the look Y
#   [GAME] -> +0x42C -> +0x9C   then +0x52D    the left mouse button in DirectInput (0x80 held, 0 released),
#                                              +0x52E is the right one
#   [GAME] -> +0x2B4 -> +0x14   then +0x521    the keyboard row: 256 bytes, one per key (KEY_ numbers below)
#
# hmbot uses it like this:
#   look_at(mem, mem_rw, xy)                 every frame: your character looks at xy (the game puts the mouse back)
#   press_left / release_left(mem, mem_rw)   hold / let go of the left button (swing, shoot)
#   press_right / release_right(...)         the right button (pick up / throw)
#   key_down / key_up(mem, mem_rw, KEY_W)    hold / let go of a key (core/legs.py walks with them)
import os

from .memory import read_bytes, read_double, read_u32, write_double

# a locker inside the game file: the same address after every restart
GAME = 0xBB0D68
# look X / look Y: the game's two globals "where the mouse is" - a link to a variable slot, the value at +0x8.
# The way to them is NOT the same in every launch ([GAME] -> +0x3F4 worked for a week, then led nowhere),
# so find_look() picks one at the start: the chain whose two values are exactly the crosshair.
# Y's link always sits 0x28 before X's. All but the first: helpers_for_me/find_path on 9.11.
LOOK_CHAINS = [
    [0x3F4, 0x460],
    [0x238, 0x4C8],
    [0x23C, 0x498],
    [0x240, 0x468],
    [0x244, 0x438],
    [0x248, 0x408],
    [0x2D0, 0x4E0],
]
LOOK_Y_BEFORE = 0x28  # Y's link is this many bytes before X's
LOOK_NEAR = 0.5  # the look and the crosshair are the same number (the game copies the mouse into both)
# the chains look_at() uses - find_look() puts the right ones here
LOOK_X = ([0x3F4, 0x460], 0x8)
LOOK_Y = ([0x3F4, 0x438], 0x8)
# the left mouse button: [GAME] -> ... -> the mouse's DirectInput object, the button at +0x52D (+0x52E the right one).
# The list of objects at [GAME] -> +0x42C moved too (the mouse at +0x9C until 8.11, at +0xA4 on 9.11),
# so find_button() picks the chain whose object is really the MOUSE: it has the mouse's DirectInput name
# (GUID_SysMouse) inside. All but the first two: helpers_for_me/find_path on 9.11.
BUTTON_CHAINS = [
    [0x42C, 0xA4],
    [0x42C, 0x9C],
    [0x2D0, 0x14, 0x4],
    [0x42C, 0x0, 0x74],
    [0x42C, 0x90, 0x14],
]
BUTTON_AT = 0x52D  # the button's place in the mouse's object
GUID_SYS_MOUSE = bytes.fromhex(
    "602b1d6fa0d5cf11bfc7444553540000"
)  # {6F1D2B60-D5A0-11CF-BFC7-444553540000}
# the chain press_left() and friends use - find_button() puts the right one here
BUTTON = ([0x42C, 0xA4], BUTTON_AT)
# DirectInput's "the button is down"
HELD = b"\x80"
RELEASED = b"\x00"

KEYBOARD = ([0x2B4, 0x14], 0x521)  # DirectInput's keyboard row: 256 bytes, one per key
# DirectInput's number for every key we use = its place in the row
KEY_SPACE = 0x39
KEY_W = 0x11
KEY_A = 0x1E
KEY_S = 0x1F
KEY_D = 0x20
KEY_R = 0x13


def key_down(mem, mem_rw, key):
    """Hold a key (one of the KEY_ numbers above)."""
    os.pwrite(mem_rw, HELD, follow(mem, KEYBOARD) + key)


def key_up(mem, mem_rw, key):
    """Let go of a key."""
    os.pwrite(mem_rw, RELEASED, follow(mem, KEYBOARD) + key)


def follow(mem, chain):
    """Where a chain ends: start at GAME, follow a link through every offset, add the last number at the end."""
    offsets, last = chain
    here = read_u32(mem, GAME)
    for offset in offsets:
        here = read_u32(mem, here + offset)
    return here + last


def find_look(mem, aim):
    """Pick the look chain for THIS launch: the first of LOOK_CHAINS whose two values are the crosshair's
    X and Y (aim = (x, y) from find_aim). aim None (no crosshair in this scene): the first one that can be
    read at all - a guess. Returns the chain it took, or None (none fits - run helpers_for_me/look_find).
    """
    global LOOK_X, LOOK_Y
    for chain in LOOK_CHAINS:
        x_chain = (chain, 0x8)
        y_chain = (chain[:-1] + [chain[-1] - LOOK_Y_BEFORE], 0x8)
        try:
            x = read_double(mem, follow(mem, x_chain))
            y = read_double(mem, follow(mem, y_chain))
        except OSError:
            continue  # a link on the way is junk in this launch
        if aim is None or (abs(x - aim[0]) < LOOK_NEAR and abs(y - aim[1]) < LOOK_NEAR):
            LOOK_X, LOOK_Y = x_chain, y_chain
            return chain
    return None


def find_button(mem):
    """Pick the mouse button chain for THIS launch: the first of BUTTON_CHAINS that leads to an object with
    GUID_SysMouse inside. None has it -> the first one that can be read at all (a guess).
    Returns (the chain, True if sure) - (None, False) when none can be read."""
    global BUTTON
    guess = None
    for chain in BUTTON_CHAINS:
        try:
            device = follow(mem, (chain, 0))  # where the object starts
            inside = read_bytes(mem, BUTTON_AT, device)
        except OSError:
            continue  # a link on the way is junk in this launch
        if guess is None:
            guess = chain
        if GUID_SYS_MOUSE in inside:
            BUTTON = (chain, BUTTON_AT)
            return chain, True
    if guess is not None:
        BUTTON = (guess, BUTTON_AT)
    return guess, False


def look_at(mem, mem_rw, xy):
    """Your character looks at xy (x, y). Call it every frame."""
    write_double(mem_rw, follow(mem, LOOK_X), xy[0])
    write_double(mem_rw, follow(mem, LOOK_Y), xy[1])


def press_left(mem, mem_rw):
    """Hold the left mouse button down."""
    os.pwrite(mem_rw, HELD, follow(mem, BUTTON))


def release_left(mem, mem_rw):
    """Let go of the left mouse button."""
    os.pwrite(mem_rw, RELEASED, follow(mem, BUTTON))


def press_right(mem, mem_rw):
    """Hold the right mouse button down."""
    os.pwrite(mem_rw, HELD, follow(mem, BUTTON) + 1)


def release_right(mem, mem_rw):
    """Let go of the right mouse button."""
    os.pwrite(mem_rw, RELEASED, follow(mem, BUTTON) + 1)
