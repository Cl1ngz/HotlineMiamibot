# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/arrow_bob.py - find the red arrow by the way it MOVES: it bobs up and down, all the time.
#
# What arrow_find showed (16:13): the game keeps NO number like "the arrow points at the TV" - no pointer, no id,
# no step counter, no position. The arrow is probably just DRAWN over whatever is next, every frame. But to draw
# it, the game writes where it goes into the list of things the graphics card gets each frame (4 corners of the
# arrow's little picture). And those corners bob: the y goes up and down a few pixels, again and again.
# If you stand still and don't move the mouse, almost nothing else on the screen does that.
#
# 2 moments (Enter in THIS terminal), both times: stand still, hands off the mouse:
#   1. stand in front of the TV, the arrow over it
#   2. use the TV, click the text away (the arrow is over the round thing now), stand still again
# Each time it: finds every float / double in memory that changed a little in 0.16 s (2-5000, by 0.05-12),
# watches those for 1.5 s, and keeps the ones that went up AND down (a bob), not more than 20.
# Then it prints them (the vertex lists of the graphics: x, y and a few numbers around them) and saves
# arrow_bob.npz - send me the printout + the npz.
#
#   python -m helpers_for_me.arrow_bob      (only READS memory)
import math
import os
import struct
import time

import numpy as np

from core.enemies import find_me_card
from core.memory import X_OFF, attach
from core.shelf import Shelf

CHUNK = 16 << 20  # read the memory 16 MB at a time...
GAPS = (0.07, 0.09, 0)  # ...3 times, with these pauses (not even steps: a bob can't hide between them)
LOW, HIGH = 2, 5000  # a position on the screen / in the room (not 0-1: those are picture corners, colors...)
MIN_STEP, MAX_STEP = 0.05, 12  # how much it may change in GAP
SAMPLES, EVERY = 30, 0.05  # then watch it this many times, this often (1.5 s)
MIN_BOB, MAX_BOB = 0.5, 20  # a bob: went up and down by this much
WINDOW = 64  # bytes saved around every bobbing number (to see what's next to it)
SHOW = 30
NPZ_FILE = "arrow_bob.npz"


def u32(data, offset):
    return int.from_bytes(data[offset : offset + 4], "little")


def f64(data, offset):
    return struct.unpack_from("<d", data, offset)[0]


def where_you_are():
    """(you, crosshair) - (x, y) of each, or None."""
    shelf = Shelf(mem)
    me = find_me_card(shelf) if shelf.records else None
    you = aim = None
    if me is not None:
        you = (f64(shelf.read(16, me + X_OFF), 0), f64(shelf.read(16, me + X_OFF), 8))
    for card in shelf.records:
        try:
            if u32(shelf.read(4, card + 0x14), 0) == 0xAF:
                aim = (f64(shelf.read(16, card + X_OFF), 0), f64(shelf.read(16, card + X_OFF), 8))
        except OSError:
            continue
    return you, aim


def pieces():
    for start, end in regions:
        for at in range(start, end, CHUNK):
            yield at, min(CHUNK, end - at)


def read(at, size):
    try:
        return os.pread(mem, size, at)
    except OSError:
        return b""


def moving_numbers():
    """Every float / double that changed a little during 0.16 s (looked at 3 times: a bob can come back
    to the same spot between 2 looks). -> {kind: addresses}"""
    found = {"float": [], "double": []}
    for at, size in pieces():
        looks = []
        for pause in GAPS:
            looks.append(read(at, size))
            time.sleep(pause)
        n = min(len(data) for data in looks)
        for kind, dtype, width, shifts in (("float", "<f4", 4, (0,)), ("double", "<f8", 8, (0, 4))):
            for shift in shifts:
                count = (n - shift) // width
                if count <= 0:
                    continue
                with np.errstate(invalid="ignore", over="ignore"):
                    rows = [np.frombuffer(d, dtype=dtype, count=count, offset=shift).astype(np.float64) for d in looks]
                    low, high = np.minimum.reduce(rows), np.maximum.reduce(rows)
                    step = high - low
                    size_ok = (np.abs(rows[0]) >= LOW) & (np.abs(rows[0]) <= HIGH)
                    ok = size_ok & (step >= MIN_STEP) & (step <= MAX_STEP)
                found[kind].append(at + shift + np.nonzero(ok)[0].astype(np.int64) * width)
    return {kind: np.concatenate(parts) if parts else np.zeros(0, np.int64) for kind, parts in found.items()}


def page_runs(addresses, width):
    """The pages these addresses are on, merged into runs: [(start, size)]."""
    pages = np.unique(np.concatenate([addresses // 4096, (addresses + width - 1) // 4096]))
    runs = []
    for page in pages.tolist():
        if runs and runs[-1][0] + runs[-1][1] == page * 4096:
            runs[-1][1] += 4096
        else:
            runs.append([page * 4096, 4096])
    return runs


def sample(addresses, dtype, width, runs):
    """The numbers at these addresses right now (NaN = can't read)."""
    out = np.full(len(addresses), np.nan)
    for start, size in runs:
        data = read(start, size)
        inside = np.nonzero((addresses >= start) & (addresses + width <= start + len(data)))[0]
        if len(inside):
            raw = np.frombuffer(data, dtype=np.uint8)
            offsets = addresses[inside] - start
            grabbed = np.ascontiguousarray(raw[offsets[:, None] + np.arange(width)])
            with np.errstate(invalid="ignore", over="ignore"):
                out[inside] = grabbed.view(dtype).ravel().astype(np.float64)
    return out


def bobbing(candidates):
    """Watch the candidates for a while, keep the ones that bob. -> [(kind, address, series)]"""
    kinds = [("float", "<f4", 4), ("double", "<f8", 8)]
    runs = {kind: page_runs(candidates[kind], width) for kind, _, width in kinds if len(candidates[kind])}
    series = {kind: [] for kind in runs}
    for _ in range(SAMPLES):
        for kind, dtype, width in kinds:
            if kind in runs:
                series[kind].append(sample(candidates[kind], dtype, width, runs[kind]).astype(np.float32))
        time.sleep(EVERY)
    found = []
    for kind, rows in series.items():
        rows = np.stack(rows)  # (SAMPLES, n)
        with np.errstate(invalid="ignore"):
            size = np.nanmax(rows, axis=0) - np.nanmin(rows, axis=0)
            steps = np.sign(np.diff(rows, axis=0))
        turns = np.zeros(rows.shape[1], dtype=int)  # how often it changed direction (up -> down, down -> up)
        last = np.zeros(rows.shape[1])
        for row in steps:
            moving = row != 0
            turns += moving & (last != 0) & (row != last)
            last = np.where(moving, row, last)
        ok = (size >= MIN_BOB) & (size <= MAX_BOB) & (turns >= 2) & ~np.isnan(rows).any(axis=0)
        for i in np.nonzero(ok)[0]:
            found.append((kind, int(candidates[kind][i]), rows[:, i]))
    found.sort(key=lambda f: f[1])
    return found


def around_text(address):
    """The 4 floats before and the 4 after this address (a vertex list is x, y, ... over and over)."""
    data = read(address - 16, 36)
    if len(data) < 36:
        return ""
    values = struct.unpack("<9f", data)
    return " ".join(f"{v:8.2f}" if math.isfinite(v) and abs(v) < 1e6 else "       ?" for v in values)


def look_once(number, text):
    input(f"\n{number}. {text}\n   Enter = start (then don't touch anything for ~10 s): ")
    you, aim = where_you_are()
    print(f"   you {you}  crosshair {aim}" if you else "   (can't see you - menu?)")
    print("   looking for numbers that move a little...")
    candidates = moving_numbers()
    print(f"   {sum(len(v) for v in candidates.values())} of them - watching them for {SAMPLES * EVERY:.1f} s...")
    found = bobbing(candidates)
    print(f"   {len(found)} of them bob")
    print("\n   BOBBING (address, kind, from - to, and the floats around it: 4 before, ITSELF, 4 after):")
    for kind, address, rows in found[:SHOW]:
        print(f"   {address:#x} {kind:6} {np.nanmin(rows):8.2f} - {np.nanmax(rows):8.2f}   [{around_text(address)}]")
    if len(found) > SHOW:
        print(f"   ...and {len(found) - SHOW} more (all in {NPZ_FILE})")
    windows = [read(address - WINDOW, 2 * WINDOW).ljust(2 * WINDOW, b"\0") for _, address, _ in found]
    return {
        "you": np.array(you or (0, 0), dtype=float),
        "aim": np.array(aim or (0, 0), dtype=float),
        "addresses": np.array([f[1] for f in found], dtype=np.int64),
        "kinds": np.array([f[0] for f in found]),
        "series": np.array([f[2] for f in found]) if found else np.zeros((0, SAMPLES)),
        "windows": np.frombuffer(b"".join(windows), dtype=np.uint8).reshape(len(found), 2 * WINDOW),
    }


mem, regions, static_regions = attach()
print(f"looking in {len(regions)} memory regions, {sum(e - s for s, e in regions) / 1e6:.0f} MB")
try:
    one = look_once(1, "stand in front of the TV, the arrow over it - stand still, hands off the mouse")
    two = look_once(2, "use the TV, click the text away, then stand still again, hands off the mouse")
    arrays = {f"m{m}_{key}": value for m, found in ((1, one), (2, two)) for key, value in found.items()}
    np.savez_compressed(NPZ_FILE, **arrays)
    print(f"\nsaved {NPZ_FILE}")
except KeyboardInterrupt:
    print()
