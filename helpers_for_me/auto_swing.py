# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/auto_swing.py - does our written swing really HIT? The bot tests it on a real enemy, fast.
#
# Our swing (swing number + frame + speed) doesn't LOOK like a real one - but what counts is the hit.
# You can't test that by hand (one second and you're dead), so the bot does it:
#   it watches the closest enemy; when he gets closer than RANGE, in the same moment it turns your
#   character to him and writes the swing. Then for 0.6 s it keeps you looking at him and watches his
#   layer and picture: if they change, he got hit.
# Enemies who DON'T chase you count too (standing, walking, sitting) - sneak up on one from behind.
# An enemy lying on the floor without a weapon (layer -100, picture 0x47) is NOT a target: a swing can't hit
# a lying enemy (not even a real one) - he gets finished off instead.
# A status line shows the closest enemy all the time, so you see when the bot is about to swing.
# After each swing it puts card +0xA0 back to the resting number, like the end of a real swing does.
# It also watches the click byte (0x132fc53): if YOU clicked around a swing, that hit may be yours - it says so.
# It stops after 3 swings, RUN_TIME, or Ctrl+C.
# The places move after you die, so you give them by hand: the speed place from find_attack, and if you want
# the bot to turn you too, the look X and Y from find_mouse + aim_hold (from THIS life - old ones are junk now).
# Without a look, aim at the enemy with your own mouse - the bot only writes the swing.
#
#   python -m helpers_for_me.auto_swing 0x57 SPEED 0.7                    (swing number, speed place, swing speed)
#   python -m helpers_for_me.auto_swing 0x57 SPEED 0.7 25                 (... and a different range, default 25)
#   python -m helpers_for_me.auto_swing 0x57 SPEED 0.7 25 LOOK_X LOOK_Y   (... and the bot turns you as well)
#   YOU keep your weapon. Pick an ENEMY without a gun (or one who hasn't seen you) and walk up to him
import math
import os
import struct
import sys
import time

from core.enemies import find_me_card
from core.memory import X_OFF, Y_OFF, attach, open_rw, read_double, read_kind, read_u32, table_records, wait, write_double

SPRITE = 0xA0  # card +0xA0: the swing number
FRAME = 0x98  # card +0x98: the frame
FIRST_FRAME = 1.0  # a real bat swing starts at frame 1.0
TARGETS = {6: "chasing", 0x3B: "other state", 0xA6: "sitting / down"}  # enemy layers the bot swings at
TOO_CLOSE = 3  # anything closer than this is you yourself (your legs?), not an enemy
CLICK = 0x132FC53  # the "left button held" byte from find_click - READING it works, so we know if YOU clicked
CLICK_WINDOW = 0.3  # a click this close before the swing (or during it) means the hit may be yours, not the bot's
WATCH = 0.6  # seconds to watch the enemy after a swing
SWINGS = 3  # stop after this many swings
RUN_TIME = 120  # ...or after this many seconds

if len(sys.argv) < 4:
    raise SystemExit("usage: python -m helpers_for_me.auto_swing 0x57 SPEED 0.7 [range] [LOOK_X LOOK_Y]")
swing = int(sys.argv[1], 16)
speed_address = int(sys.argv[2], 16)
speed = float(sys.argv[3])
reach = float(sys.argv[4]) if len(sys.argv) > 4 else 25  # game units
look = (int(sys.argv[5], 16), int(sys.argv[6], 16)) if len(sys.argv) > 6 else None

mem, regions, static_regions = attach()
mem_rw = open_rw()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")
rest = read_u32(mem, card + SPRITE)
if rest == swing:
    raise SystemExit("+0xA0 is stuck on the swing number - swing once by hand, then run again")
if read_double(mem, speed_address) != 0:
    raise SystemExit(f"the speed place {speed_address:#x} isn't 0 at rest - it moved (did you die?): run find_attack again")


last_click = -999.0  # when we last saw the left button held


def check_click():
    """Remember when you last held the left button."""
    global last_click
    try:
        if os.pread(mem, 1, CLICK)[0] == 1:
            last_click = time.monotonic()
    except OSError:
        pass


def look_at(xy):
    """Turn your character to xy (only if we were given the look places - else you aim yourself)."""
    if look is not None:
        write_double(mem_rw, look[0], xy[0])
        write_double(mem_rw, look[1], xy[1])


def xy_of(thing):
    return read_double(mem, thing + X_OFF), read_double(mem, thing + Y_OFF)


def kind_name(layer, picture):
    """What kind of enemy this is - or None if it isn't one."""
    # (picture is kept for later: a lying enemy without a weapon is layer -100 + picture 0x47 - not a swing target)
    return TARGETS.get(layer)


def closest_enemy(you):
    """(card, distance, xy, (layer, picture)) of the closest enemy, or None."""
    best = None
    for enemy in table_records(mem):
        try:
            kind = read_kind(mem, enemy, 0, 0x14), read_kind(mem, enemy, 1, 0x10)
            if kind_name(*kind) is None:
                continue
            xy = xy_of(enemy)
        except OSError:
            continue
        distance = math.dist(xy, you)
        if distance < TOO_CLOSE:
            continue
        if best is None or distance < best[1]:
            best = (enemy, distance, xy, kind)
    return best


def write_swing():
    write_double(mem_rw, speed_address, speed)
    write_double(mem_rw, card + FRAME, FIRST_FRAME)
    os.pwrite(mem_rw, struct.pack("<I", swing), card + SPRITE)


def swing_at(enemy, xy, kind):
    """Turn to him, swing, watch his layer and picture for WATCH seconds. True if they changed."""
    look_at(xy)
    write_swing()
    t0 = time.monotonic()
    last = kind
    while time.monotonic() - t0 < WATCH:
        check_click()
        try:
            look_at(xy_of(enemy))  # keep facing him during the swing
            now = read_kind(mem, enemy, 0, 0x14), read_kind(mem, enemy, 1, 0x10)
        except OSError:
            print(f"  {time.monotonic() - t0:5.2f} s   his card is gone (junk memory)")
            return True
        if now != last:
            print(f"  {time.monotonic() - t0:5.2f} s   layer {last[0]:#x} -> {now[0]:#x}   picture {last[1]:#x} -> {now[1]:#x}")
            last = now
        time.sleep(1 / 240)
    # the end of a real swing puts +0xA0 back - ours doesn't, so we do it (wait up to 1 s for the swing to end)
    end = time.monotonic() + 1
    while read_double(mem, speed_address) != 0 and time.monotonic() < end:
        time.sleep(0.005)
    if read_double(mem, speed_address) == 0 and read_u32(mem, card + SPRITE) == swing:
        os.pwrite(mem_rw, struct.pack("<I", rest), card + SPRITE)
    return last != kind


try:
    print(f"click byte {CLICK:#x} now: {os.pread(mem, 1, CLICK)[0]}  (should be 0 - hold the left button to see 1)")
except OSError:
    print(f"click byte {CLICK:#x} can't be read - clicks won't be checked")
wait(f"keep your weapon - walk up to an enemy (no gun, or one who hasn't seen you). Swing range: {reach:.0f}", 3)
swings = 0
start = time.monotonic()
next_status = 0
try:
    while swings < SWINGS and time.monotonic() - start < RUN_TIME:
        try:
            you = xy_of(card)
            resting = read_u32(mem, card + SPRITE) == rest and read_double(mem, speed_address) == 0
        except OSError:
            raise SystemExit("\nlost your card - did you die or leave the level?")
        check_click()
        target = closest_enemy(you)
        now = time.monotonic()
        if now >= next_status:
            if target is None:
                text = "no enemy in the table"
            else:
                text = f"closest enemy {target[1]:6.1f} away ({kind_name(*target[3])})"
            print(f"\r  {text:60}", end="", flush=True)
            next_status = now + 0.1
        if target is None or target[1] > reach or not resting:
            time.sleep(1 / 120)
            continue

        enemy, distance, xy, kind = target
        swings += 1
        print(f"\n\nswing {swings}: enemy {enemy:#x} at {distance:.1f} ({kind_name(*kind)})")
        swing_time = time.monotonic()
        hit = swing_at(enemy, xy, kind)
        clicked = last_click > swing_time - CLICK_WINDOW
        verdict = "HIT - he changed" if hit else "no change"
        if clicked:
            verdict += "   (YOU CLICKED around this swing - doesn't count)"
        print(f"  result: {verdict}\n")
except KeyboardInterrupt:
    print("\nstopped (Ctrl+C)")
print(f"{swings} swing(s)")
