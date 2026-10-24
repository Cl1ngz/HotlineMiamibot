# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/look.py - what's around an address? (doubles from -0x40 to +0x40)
#
#   python -m helpers_for_me.look 0x2fce5f8        look once
#   python -m helpers_for_me.look 0x2fce5f8 5      look 5 times, 1 second apart (watch it change)
import sys
import time

from memory import attach, nearby

mem, regions, static_regions = attach()
address = int(sys.argv[1], 16)  # "0x2fce5f8" -> a number
times = int(sys.argv[2]) if len(sys.argv) > 2 else 1

for t in range(times):
    print(f"--- look {t + 1} at {hex(address)} ---")
    for off, value in nearby(mem, address).items():
        sign = "-" if off < 0 else "+"
        print(f"  {sign}{abs(off):#04x}  {value}")
    if t < times - 1:
        time.sleep(1)
