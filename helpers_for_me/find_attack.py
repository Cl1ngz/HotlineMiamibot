# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/find_attack.py - where does the game remember "an attack is going on"?
#
# Card +0xA0 and the frame are only EFFECTS of a swing (writing them did nothing). But the game must keep
# "I'm attacking" somewhere - it knows when the swing ends and puts +0xA0 back by itself.
# The game keeps its own variables as doubles, so we look in ALL its memory for a double that:
#   while resting:  always holds the SAME value
#   while swinging: holds a DIFFERENT value
# One look at all the memory takes ~0.2 s and one swing lasts ~0.2 s, so a look only counts if you were
# swinging (card +0xA0 = the swing number) from its first byte to its last. Otherwise it's thrown away and retried.
#
#   python -m helpers_for_me.find_attack 0x57        (the swing number attack_diff showed for your weapon)
#   be in a level with THAT weapon, somewhere SAFE, stand still. When the pop-up says CLICK: click fast, non-stop
import os
import sys
import time

import numpy as np

from core.enemies import RECORD, find_me_card
from core.memory import attach, read_double, read_u32, wait

SPRITE = 0xA0  # card +0xA0: the swing number while swinging
FRAME = 0x98  # card +0x98: the frame
ROUNDS = 8  # at most this many rest/swing rounds
MIN_ROUNDS = 3  # always at least this many
ENOUGH = 10  # after that, stop when this few places are left
TRIES = 80  # attempts to get one clean look while swinging (each ~0.2 s)
MAX_FAILS = 4  # give up after this many rounds without a clean look

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.find_attack 0x57   (the swing number from attack_diff)")
swing_sprite = int(sys.argv[1], 16)

mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - are you in a level?")
rest_sprite = read_u32(mem, card + SPRITE)
if rest_sprite == swing_sprite:
    raise SystemExit(f"+0xA0 is {swing_sprite:#x} already - swing once by hand so the game puts it back, then run again")
print(f"your card {card:#x}: resting +0xA0 = {rest_sprite:#x}, swinging = {swing_sprite:#x}")


def state():
    return read_u32(mem, card + SPRITE), read_double(mem, card + FRAME)


def snapshot(kind):
    """All the memory - but only if you were swinging (or resting) from the first byte to the last. Else None."""
    first = state()

    def still_ok():
        now = state()
        if kind == "swing":
            return now[0] == swing_sprite
        return now == first and now[0] == rest_sprite  # resting: nothing moves at all

    if not still_ok():
        return None
    snap = {}
    for start, end in regions:
        try:
            snap[start] = os.pread(mem, end - start, start)
        except OSError:
            continue
        if not still_ok():
            return None  # the swing ended (or started) halfway through - this look is mixed, throw it away
    return snap


def take(kind, prompt, tries):
    wait(prompt, 2)
    for _ in range(tries):
        snap = snapshot(kind)
        if snap is not None:
            return snap
        time.sleep(0.005)
    return None


def view(data, shift):
    return np.frombuffer(data, dtype="<f8", count=(len(data) - shift) // 8, offset=shift)


def sane(values):
    """Doubles a game would really keep: not NaN, not huge, and not a tiny 'almost zero'
    (those are two halves of other numbers read as one double)."""
    with np.errstate(invalid="ignore"):
        return np.isfinite(values) & ((values == 0) | (np.abs(values) > 1e-6)) & (np.abs(values) < 1e9)


# (region start, shift) -> (positions still in the race, their resting value)
candidates = None
round_number = 1
fails = 0
while round_number <= ROUNDS:
    rest = take("rest", f"round {round_number}: STOP clicking - stand still", 20)
    swing = take("swing", f"round {round_number}: CLICK CLICK CLICK - click fast, non-stop", TRIES)
    if rest is None or swing is None:
        fails += 1
        print(f"round {round_number}: couldn't get a clean look ({'resting' if rest is None else 'swinging'}) - again")
        if fails >= MAX_FAILS:
            raise SystemExit("too many failed rounds - click faster during CLICK, and stand still during STOP")
        continue

    new = {}
    for start, rest_data in rest.items():
        swing_data = swing.get(start)
        if swing_data is None or len(swing_data) != len(rest_data):
            continue
        for shift in (0, 4):
            a, b = view(rest_data, shift), view(swing_data, shift)
            key = (start, shift)
            if candidates is None:
                # first round: everything that differs between resting and swinging (and isn't junk)
                positions = np.flatnonzero((a != b) & sane(a) & sane(b))
                values = a[positions]
            elif key in candidates:
                positions, values = candidates[key]
                inside = positions < len(a)
                positions, values = positions[inside], values[inside]
                keep = (a[positions] == values) & (b[positions] != values) & sane(b[positions])  # same at rest, different swinging
                positions, values = positions[keep], values[keep]
            else:
                continue
            # your own card has the frame in it - we know that one moves
            addresses = start + shift + positions * 8
            mine = (addresses >= card) & (addresses < card + RECORD)
            positions, values = positions[~mine], values[~mine]
            if len(positions):
                new[key] = (positions, values)
    candidates = new

    total = sum(len(positions) for positions, _ in candidates.values())
    print(f"round {round_number}: {total} places had one value at rest and another while swinging (every round)")
    if not total or (round_number >= MIN_ROUNDS and total <= ENOUGH):
        break
    round_number += 1

if not candidates:
    raise SystemExit("nothing left - no double says 'attacking' (or a round went wrong) - we'll think again")

print("\nleft:")
for (start, shift), (positions, values) in sorted(candidates.items()):
    for position, value in list(zip(positions, values))[:20]:
        address = start + shift + int(position) * 8
        fixed = "FIXED address (inside the game file)" if any(s <= address < e for s, e in static_regions) else ""
        print(f"  {address:#x}   at rest {value:10.3f}   now {read_double(mem, address):10.3f}   {fixed}")
    if len(positions) > 20:
        print(f"  ... and {len(positions) - 20} more near {start:#x}")
