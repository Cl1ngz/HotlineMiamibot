# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/click_test.py - does writing 1 into the "button held" byte make your character attack?
#
#   test 1 (once): write 1 one time and read it back for 1 s - does it stay, or does the game reset it?
#   test 2 (hold): keep writing 1 for 2 s - does your character attack WITHOUT you touching the mouse?
# Both tests write 0 at the end, so the game never thinks the button got stuck.
#
#   python -m helpers_for_me.click_test 0x132fc53        (the byte find_click found)
#   be in a level with empty hands or a melee weapon, somewhere safe, DON'T touch the mouse
import os
import sys
import time

from core.memory import attach, open_rw, wait

HOLD_TIME = 2  # seconds

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.click_test 0x132fc53   (the byte from find_click)")
address = int(sys.argv[1], 16)

mem, regions, static_regions = attach()
mem_rw = open_rw()


def read_byte():
    return os.pread(mem, 1, address)[0]


def write_byte(value):
    os.pwrite(mem_rw, bytes([value]), address)


# the neighbours: the game may keep "just pressed" / "just released" right next to "held"
around = os.pread(mem, 16, address - 8)
print(f"bytes around {address:#x} (ours is in [brackets]):")
print("  " + " ".join(f"[{b:02x}]" if i == 8 else f"{b:02x}" for i, b in enumerate(around)))

wait("test 1: hands OFF the mouse", 3)
write_byte(1)
start = time.monotonic()
while time.monotonic() - start < 1:
    print(f"  {time.monotonic() - start:4.2f} s   byte = {read_byte()}")
    time.sleep(0.1)
write_byte(0)

wait("test 2: WATCH YOUR CHARACTER - does it attack by itself?", 3)
start = time.monotonic()
writes = 0
while time.monotonic() - start < HOLD_TIME:
    write_byte(1)
    writes += 1
    time.sleep(0.002)
write_byte(0)
print(f"test 2: wrote 1 {writes} times, then 0")
print("Did your character attack? Once, or again and again? Did anything else happen?")
