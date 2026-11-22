# https://github.com/Cl1ngz/HotlineMiamibot
# core/hands.py - the bot's hands: aims, clicks and presses keys by writing bytes to the game's memory
# look_at() every frame, press/release_left/right(), key_down/up() - every chain starts at GAME
import os

from .memory import read_bytes, read_double, read_u32, write_double

# start of every chain - a fixed address in the .exe
GAME = 0xBB0D68
# look X / look Y = where the mouse is in the game. The way there changes between launches,
# so we keep a few known ways and find_look() takes the one whose numbers are the crosshair's X, Y
LOOK_CHAINS = [
    [0x3F4, 0x460],
    [0x238, 0x4C8],
    [0x23C, 0x498],
    [0x240, 0x468],
    [0x244, 0x438],
    [0x248, 0x408],
    [0x2D0, 0x4E0],
]
LOOK_Y_BEFORE = 0x28  # Y's last link is 0x28 smaller than X's
LOOK_NEAR = 0.5  # look and crosshair are the same number - 0.5 of room
LOOK_X = ([0x3F4, 0x460], 0x8)  # find_look() puts the right chains here
LOOK_Y = ([0x3F4, 0x438], 0x8)


# mouse buttons: a few known ways too, find_button() takes the one that ends in the mouse
BUTTON_CHAINS = [
    [0x42C, 0xA4],
    [0x42C, 0x9C],
    [0x2D0, 0x14, 0x4],
    [0x42C, 0x0, 0x74],
    [0x42C, 0x90, 0x14],
]
BUTTON_AT = 0x52D  # left button byte in the mouse, the right one is +1
GUID_SYS_MOUSE = bytes.fromhex(
    "602b1d6fa0d5cf11bfc7444553540000"
)  # Windows' name for "the mouse" - only the mouse has it inside
BUTTON = ([0x42C, 0xA4], BUTTON_AT)  # find_button() puts the right chain here
HELD = b"\x80"  # button down
RELEASED = b"\x00"  # button up

KEYBOARD = ([0x2B4, 0x14], 0x521)  # keyboard row: 256 bytes, one per key
# key number = its place in the keyboard row
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
