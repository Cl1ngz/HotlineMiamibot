# https://github.com/Cl1ngz/HotlineMiamibot
import sys
import time

from memory import attach, auto_setup, follow, load_address, read_double


def addresses_work(mem):
    # True if addresses.json exists and both paths lead to real positions.
    try:
        for name in ("player", "crosshair"):
            x = read_double(mem, follow(mem, load_address(name)))
            if not 0.01 < abs(x) < 100000:
                return False
    except (OSError, KeyError, ValueError):
        return False
    return True


mem, regions, static_regions = attach()

if "--setup" in sys.argv or not addresses_work(mem):
    print("Running automatic setup - follow the popups")
    auto_setup(mem)

PLAYER = load_address("player")
CROSSHAIR = load_address("crosshair")
Y_OFFSET = load_address("y_offset")

try:
    while True:
        try:
            p = follow(mem, PLAYER)
            c = follow(mem, CROSSHAIR)
            x, y = read_double(mem, p), read_double(mem, p + Y_OFFSET)
            cx, cy = read_double(mem, c), read_double(mem, c + Y_OFFSET)
            print(
                f"you: {x:7.1f} {y:7.1f}   aim: {cx:7.1f} {cy:7.1f}   ",
                end="\r",
                flush=True,
            )
        except OSError:
            print("not in a level (menu / loading?)          ", end="\r", flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nbye!")
