# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/pickup.py - picking weapons up: which button, and what does your card say you hold?
#
# Two things we don't know yet:
#   1. is the RIGHT mouse button at +0x52E (one byte after the left one, +0x52D)?
#   2. what is in your hand? +0xA0 of your card: 0x13 = bat at rest, 0x1 = empty hands... and the rest?
#
#   python -m helpers_for_me.pickup          WATCH: play by hand, pick weapons up / throw them (right button).
#                                            It writes down every change of your +0xA0 and every weapon
#                                            that disappears from the floor or shows up on it. Ctrl+C = end.
#   python -m helpers_for_me.pickup press    PRESS: stand ON a weapon, run it. It presses the right button
#                                            by writing memory (like hmbot's left one) and says what happened.
import math
import os
import sys
import time

from core.enemies import RECORD, find_me_card
from core.hands import BUTTON, HELD, RELEASED, follow
from core.memory import X_OFF, Y_OFF, attach, open_rw, read_double, read_kind, read_u32, table_records
from core.weapons import FLOOR, FRAME, MARK, load_names

HAND = 0xA0  # your card: what you hold / do
RIGHT = 1  # the right button's byte sits one after the left one (+0x52D -> +0x52E)
NEAR = 40  # a weapon this close to you counts as "under you"
EVERY = 1 / 30  # seconds between two looks (watch mode)
HOLD = 0.15  # seconds to hold the right button (press mode)

mem, regions, static_regions = attach()
names = load_names()


def name(frame):
    if frame == 0:
        return "phantom? (frame 0)"
    return names.get(frame, {}).get("name", f"unknown frame {frame}")


def weapons_now():
    """{card: (x, y, frame)} of every weapon lying on the floor - like core.weapons.find_weapons,
    but it keeps the card too, so a weapon that slides or flies is still the same weapon."""
    records = table_records(mem)
    if not records:
        return {}
    found = {}
    for card in range(min(records) - 64 * RECORD, max(records) + 64 * RECORD + 1, RECORD):
        try:
            if read_kind(mem, card, 0, 0x14) == FLOOR and read_kind(mem, card, 1, 0x10) == MARK:
                xy = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
                found[card] = (*xy, int(read_double(mem, card + FRAME)))
        except OSError:
            continue
    return found


def me():
    """(your xy, your +0xA0) or None (menu, dead, sitting on an enemy)."""
    card = find_me_card(mem)
    if card is None:
        return None
    try:
        return (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)), read_u32(mem, card + HAND)
    except OSError:
        return None


def describe(card, weapon, you):
    x, y, frame = weapon
    far = f"far {math.dist((x, y), you):4.0f}" if you else "far ?"
    return f"{name(frame):18} at ({x:4.0f},{y:4.0f}) {far}   card {card:#x}"


def changes(before, after, you):
    """Lines about weapons that disappeared from the floor / showed up on it."""
    lines = [f"  GONE from the floor: {describe(c, w, you)}" for c, w in before.items() if c not in after]
    lines += [f"  NEW on the floor:   {describe(c, w, you)}" for c, w in after.items() if c not in before]
    return lines


def watch():
    print("WATCH: pick weapons up / throw them by hand (right button), swing too. Ctrl+C = end.\n")
    start = time.monotonic()
    floor = weapons_now()
    seen = me()
    you = seen[0] if seen else None
    print("weapons on the floor now:")
    for card, weapon in sorted(floor.items(), key=lambda cw: math.dist(cw[1][:2], you) if you else 0):
        print("  " + describe(card, weapon, you))
    hand = seen[1] if seen else None
    print(f"\nyour +0xA0 at the start: {hand:#x}\n" if hand is not None else "\ncan't find you yet\n")
    next_floor = 0
    while True:
        now = time.monotonic()
        t = f"t={now - start:6.2f}s"
        seen = me()
        if seen is not None:
            you, new_hand = seen
            if new_hand != hand:
                print(f"{t}  +0xA0 {hand if hand is None else hex(hand)} -> {new_hand:#x}")
                hand = new_hand
        if now >= next_floor:  # the floor scan is slower - 10 times a second is plenty
            try:
                new_floor = weapons_now()
            except OSError:
                new_floor = floor  # loading - keep the old list
            for line in changes(floor, new_floor, you):
                print(f"{t}{line}")
            floor = new_floor
            next_floor = now + 0.1
        time.sleep(EVERY)


def press():
    seen = me()
    if seen is None:
        raise SystemExit("can't find you - are you in a level?")
    you, hand = seen
    floor = weapons_now()
    under = {c: w for c, w in floor.items() if math.dist(w[:2], you) < NEAR}
    print(f"you at ({you[0]:.0f},{you[1]:.0f}), +0xA0 {hand:#x}")
    print(f"weapons closer than {NEAR}:" if under else f"no weapon closer than {NEAR} (a press will throw what you hold)")
    for card, weapon in under.items():
        print("  " + describe(card, weapon, you))

    mem_rw = open_rw()
    button = follow(mem, BUTTON) + RIGHT
    print(f"\npressing the right button: writing 0x80 to {button:#x} for {HOLD} s ...")
    os.pwrite(mem_rw, HELD, button)
    time.sleep(HOLD)
    os.pwrite(mem_rw, RELEASED, button)
    time.sleep(0.5)  # let the game finish picking up / throwing

    after = me()
    new_floor = weapons_now()
    print()
    print(f"+0xA0: {hand:#x} -> {after[1]:#x}" if after else "+0xA0: can't find you now")
    lines = changes(floor, new_floor, you)
    print("\n".join(lines) if lines else "  nothing on the floor changed -> the button did nothing (wrong byte?)")


if len(sys.argv) > 1 and sys.argv[1] == "press":
    press()
else:
    try:
        watch()
    except KeyboardInterrupt:
        print("\nbye!")
