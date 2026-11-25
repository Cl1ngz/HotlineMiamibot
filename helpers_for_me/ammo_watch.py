# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/ammo_watch.py - where does the game keep your ammo? (the thorough way)
#
# ammo_find looked only for doubles, only in part of the memory, and found nothing that goes down at every
# shot. This one takes a photo of ALL the writable memory, and after every shot (your hand shows a "fire"
# picture) keeps the places that went down - by any amount, as a double, a 4-byte whole number or a 4-byte
# float. Between shots it drops the places that change without a shot. Ctrl+C stops it.
#
#   python -m helpers_for_me.ammo_watch      a gun that really fires in your hand; wait for "ready", then
#                                            shoot single clicks with 1-2 s between them
import os
import time

import numpy as np

from core.enemies import INSTANCE, RECORD, find_me_card, shelf_cards
from core.memory import attach, find_game, read_kind, read_u32, table_records
from core.weapons import load_names, pictures

MOST = 250  # no gun holds more than this
CHUNK = 4 << 20  # read the memory 4 MB at a time
FEW = 10  # this few places left = show where they live
WIDE = 1024  # how far around the table to look for the card that holds it
FIRE = (0x28, 0x29)  # your hand while shooting, if weapon_names.json has no "fire" yet
TYPES = ("double", "int", "float")  # 8-byte double, 4-byte whole number, 4-byte float
VIEWS = (
    (0, "<f8", 0),
    (0, "<f8", 4),
    (1, "<i4", 0),
    (2, "<f4", 0),
)  # (type, numpy type, shift)


def all_regions():
    """Every writable piece of the game's memory (not only the ones attach() picks) - but no devices."""
    regions = []
    with open(f"/proc/{find_game()[0]}/maps") as f:
        for line in f:
            parts = line.split(None, 5)
            path = parts[5].strip() if len(parts) == 6 else ""
            if parts[1].startswith("rw") and not path.startswith(("/dev/", "[v")):
                start, end = (int(x, 16) for x in parts[0].split("-"))
                regions.append((start, end))
    return regions


def photo():
    """{piece start: bytes} of all the writable memory."""
    pieces = {}
    for start, end in regions:
        for at in range(start, end, CHUNK):
            try:
                pieces[at] = os.pread(mem, min(CHUNK, end - at), at)
            except OSError:
                continue
    return pieces


def whole(values):
    with np.errstate(invalid="ignore"):
        return (values >= 1) & (values <= MOST) & (values == np.floor(values))


def went_down(before, after):
    """(places, types, values now) of every whole number 1..MOST that went down between the photos."""
    places, types, values = [], [], []
    for at, old in before.items():
        new = after.get(at)
        if new is None:
            continue
        size = min(len(old), len(new))
        for kind, dtype, shift in VIEWS:
            step = np.dtype(dtype).itemsize
            count = (size - shift) // step
            with np.errstate(
                invalid="ignore"
            ):  # junk bytes that aren't numbers - they just don't match
                a = np.frombuffer(old, dtype, count, shift).astype(np.float64)
                b = np.frombuffer(new, dtype, count, shift).astype(np.float64)
                hit = np.nonzero(whole(a) & (b < a) & (b >= 0) & (b == np.floor(b)))[0]
            places.append(at + shift + step * hit)
            types.append(np.full(len(hit), kind, np.int8))
            values.append(b[hit])
    return np.concatenate(places), np.concatenate(types), np.concatenate(values)


def now(places, types):
    """What the places hold now, read as their type (NaN where it can't be read)."""
    values = np.full(len(places), np.nan)
    order = np.argsort(places)
    sorted_places = places[order]
    for start, end in regions:
        for at in range(start, end, CHUNK):
            lo = np.searchsorted(sorted_places, at, side="left")
            hi = np.searchsorted(sorted_places, min(at + CHUNK, end) - 8, side="right")
            if lo >= hi:
                continue
            try:
                raw = np.frombuffer(os.pread(mem, min(CHUNK, end - at), at), np.uint8)
            except OSError:
                continue
            pick = order[lo:hi]
            pick = pick[places[pick] + 8 <= at + len(raw)]
            eight = raw[(places[pick] - at)[:, None] + np.arange(8)].copy()
            kinds = types[pick]
            read = np.empty(len(pick))
            read[kinds == 0] = eight[kinds == 0].view("<f8").ravel()
            read[kinds == 1] = eight[kinds == 1][:, :4].copy().view("<i4").ravel()
            read[kinds == 2] = eight[kinds == 2][:, :4].copy().view("<f4").ravel()
            values[pick] = read
    return values


def owner(place):
    """Whose card / folder the place is in, as text."""
    if any(s <= place < e for s, e in static_regions):
        return "in the game file (same address every launch)"
    table = table_records(mem)
    me = find_me_card(mem)
    for card in shelf_cards(mem, table, WIDE) if table else []:
        try:
            folder = read_u32(mem, card)
            layer = read_u32(mem, card + 0x14)
            picture = read_u32(mem, folder + 0x10)
        except OSError:
            continue
        who = "YOUR" if card == me else f"layer {layer:#x} picture {picture:#x}"
        if card <= place < card + RECORD:
            return f"{who} card +{place - card:#x}"
        if folder <= place < folder + INSTANCE:
            return f"{who} folder +{place - folder:#x}"
    return "not in any card or folder"


def show(places, types, values):
    if 0 < len(places) <= FEW:
        for place, kind, value in zip(places, types, values):
            print(
                f"  {int(place):#x}   {TYPES[kind]:6}  holds {value:g}   {owner(int(place))}"
            )


def me_hand():
    """Your hand right now (card +0xA0), or None (you're hidden for a moment at every shot)."""
    me = find_me_card(mem)
    try:
        return None if me is None else read_kind(mem, me, 0, 0xA0)
    except OSError:
        return None


mem, _, static_regions = attach()
regions = all_regions()
fire = {p for info in load_names().values() for p in pictures(info, "fire")} or set(
    FIRE
)
print(
    f"memory: {sum(e - s for s, e in regions) >> 20} MB in {len(regions)} pieces - taking a photo..."
)
before = photo()
print("ready - shoot ONCE (a gun that really fires)")
places = types = values = None
hand, shots, calm_at = None, 0, 0.0
try:
    while True:
        if places is not None and hand not in fire and time.time() >= calm_at:
            new = now(places, types)
            keep = new == values
            if (
                me_hand() not in fire and not keep.all()
            ):  # no shot started while we were reading
                places, types, values = places[keep], types[keep], new[keep]
                print(f"  without a shot: {len(places)} places stayed the same")
                show(places, types, values)
            calm_at = time.time() + 1
        now_hand = me_hand()
        if now_hand is not None and now_hand != hand:
            if hand in fire and now_hand not in fire:  # a shot just ended
                shots += 1
                time.sleep(0.2)
                if places is None:
                    print("comparing the photos...")
                    places, types, values = went_down(before, photo())
                    before = None  # a lot of memory - let it go
                else:
                    new = now(places, types)
                    keep = (new < values) & (new >= 0)
                    places, types, values = places[keep], types[keep], new[keep]
                counts = ", ".join(
                    f"{int((types == k).sum())} {name}" for k, name in enumerate(TYPES)
                )
                print(
                    f"shot {shots}: {len(places)} places went down ({counts}) - shoot again"
                )
                show(places, types, values)
                calm_at = time.time() + 0.5
            hand = now_hand
        time.sleep(1 / 60)
except KeyboardInterrupt:
    print(
        f"\nstopped after {shots} shots, {0 if places is None else len(places)} places left"
    )
