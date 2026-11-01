# https://github.com/Cl1ngz/HotlineMiamibot

import sys

import numpy as np

from core.memory import attach, take_snapshot, wait

ROUNDS = 8  # at most this many hold/release rounds
MIN_ROUNDS = 3  # always at least this many - ones and zeros are everywhere
ENOUGH = 10  # after that, stop when this few places are left
HELD = (
    int(sys.argv[1], 16) if len(sys.argv) > 1 else 1
)  # the value while the key is held
# kind -> (numpy type, value while held, value while released)
KINDS = {"byte": (np.uint8, HELD, 0)}
if HELD == 1:
    KINDS["double"] = (
        np.dtype("<f8"),
        1.0,
        0.0,
    )  # a game variable could be a double 1.0 too


def view(data, dtype, shift):
    """The memory as a row of numbers of this type, starting `shift` bytes in."""
    size = np.dtype(dtype).itemsize
    return np.frombuffer(
        data, dtype=dtype, count=(len(data) - shift) // size, offset=shift
    )


mem, regions, static_regions = attach()

# (kind, region start, shift) -> positions still in the race (numbered in that kind's size: bytes 1, doubles 8)
candidates = {}
round_number = 1
while round_number <= ROUNDS:
    wait(f"round {round_number}: HOLD the key (and keep holding)", 3)
    held = take_snapshot(mem, regions)
    wait(f"round {round_number}: RELEASE the key", 3)
    released = take_snapshot(mem, regions)

    for start, held_data in held.items():
        released_data = released.get(start)
        if released_data is None or len(released_data) != len(held_data):
            continue  # that part of memory changed size - skip it this round
        for kind, (dtype, on, off) in KINDS.items():
            for shift in (0,) if kind == "byte" else (0, 4):
                a, b = view(held_data, dtype, shift), view(released_data, dtype, shift)
                key = (kind, start, shift)
                if round_number == 1:
                    positions = np.flatnonzero(
                        (a == on) & (b == off)
                    )  # first round: everything that fits
                elif key in candidates:
                    positions = candidates[key]
                    positions = positions[positions < len(a)]
                    positions = positions[
                        (a[positions] == on) & (b[positions] == off)
                    ]  # still fits?
                else:
                    continue
                if len(positions):
                    candidates[key] = positions
                else:
                    candidates.pop(key, None)

    total = sum(len(positions) for positions in candidates.values())
    print(
        f"round {round_number}: {total} places were {HELD:#x} while held and 0 while released (every round so far)"
    )
    if not total or (round_number >= MIN_ROUNDS and total <= ENOUGH):
        break
    round_number += 1

if not candidates:
    raise SystemExit(
        "nothing left - the game keeps the key some other way (or a round went wrong) - run it again"
    )

print("\nleft:")
for (kind, start, shift), positions in sorted(candidates.items()):
    size = np.dtype(KINDS[kind][0]).itemsize
    for position in positions[:20]:
        address = start + shift + int(position) * size
        fixed = (
            "FIXED address (inside the game file)"
            if any(s <= address < e for s, e in static_regions)
            else ""
        )
        print(f"  {kind:6} {address:#x}   {fixed}")
    if len(positions) > 20:
        print(f"  ... and {len(positions) - 20} more {kind}s near {start:#x}")
