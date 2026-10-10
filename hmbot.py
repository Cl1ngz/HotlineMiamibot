# https://github.com/Cl1ngz/HotlineMiamibot
import time

from memory import attach, follow, read_double

PLAYER = [0xBEC91C, 0x50]
Y_OFFSET = 0x8

mem, regions, static_regions = attach()

while True:
    try:
        x_addr = follow(mem, PLAYER)
        x = read_double(mem, x_addr)
        y = read_double(mem, x_addr + Y_OFFSET)
        print(f"X: {x:8.1f}   Y: {y:8.1f}     ", end="\r", flush=True)
    except OSError:
        print("player not found (menu / loading?)   ", end="\r", flush=True)
    time.sleep(0.1)
