import time

from memory import attach, follow, read_double

PLAYER = [0xBEC8C8, 0xF68]
# the first of each 819.8 group
CANDIDATES = [0x252AC50, 0x30F5A88]

mem, regions, static_regions = attach()

while True:
    p = follow(mem, PLAYER)
    px, py = read_double(mem, p), read_double(mem, p + 0x8)
    line = ""
    for a in CANDIDATES:
        cx, cy = read_double(mem, a), read_double(mem, a + 0x8)
        line += f"{hex(a)}: dx={cx - px:+6.0f} dy={cy - py:+6.0f}   "
    print(line, end="\r", flush=True)
    time.sleep(0.1)
