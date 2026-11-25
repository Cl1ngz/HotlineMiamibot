# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/ammo_find.py - where does the game keep your ammo?
#
# Hold a gun. "start" keeps every whole number 1..MOST in the writable memory (as a double - GameMaker
# keeps numbers that way). Then each "shot" keeps only the places that went down by exactly 1, and each
# "same" (you didn't shoot) only the ones that didn't change. You don't need to see the number on screen.
# Do it all on one floor - a new floor can move things around.
#
#   python -m helpers_for_me.ammo_find start   gun in hand: remember every whole number 1..MOST
#   (shoot ONCE - a short tap)
#   python -m helpers_for_me.ammo_find shot    keep the places that went down by 1
#   (walk around, don't shoot)
#   python -m helpers_for_me.ammo_find same    keep the places that didn't change
#   python -m helpers_for_me.ammo_find 5       or: keep the places that hold 5 (if you can see the number)
#   python -m helpers_for_me.ammo_find clear   start again
#
#   python -m helpers_for_me.ammo_find watch [0x30cfff8 ...]
#       all in one: start, then after every shot (your hand shows a "fire" picture) it keeps the places that
#       went down by 1 by itself. It also says when your card changes, and how the given addresses change.
#       Ctrl+C stops it.
import os
import sys
import time

import numpy as np

from core.enemies import INSTANCE, RECORD, find_me_card, shelf_cards
from core.memory import attach, read_double, read_kind, read_u32, table_records
from core.weapons import load_names

FILE = "ammo_find.npz"
MOST = 250  # no gun holds more than this
CHUNK = 4 << 20  # read the memory 4 MB at a time
FEW = 10  # this few places left = show where they live
WIDE = 1024  # how far around the table to look for the card that holds it
FIRE = (0x28, 0x29)  # your hand while shooting, if weapon_names.json has no "fire" yet


def chunks(regions):
    """(start, bytes) of the writable memory, CHUNK at a time."""
    for start, end in regions:
        for at in range(start, end, CHUNK):
            try:
                yield at, os.pread(mem, min(CHUNK, end - at), at)
            except OSError:
                continue


def start():
    """Every 4-byte aligned double that is a whole number 1..MOST: (places, values)."""
    places, values = [], []
    for at, data in chunks(regions):
        for shift in (0, 4):
            size = (len(data) - shift) // 8 * 8
            numbers = np.frombuffer(data[shift : shift + size], "<f8")
            with np.errstate(invalid="ignore"):  # NaN bytes in memory - they just don't match
                hit = np.nonzero((numbers >= 1) & (numbers <= MOST) & (numbers == np.floor(numbers)))[0]
            places.append(at + shift + 8 * hit)
            values.append(numbers[hit])
    return np.concatenate(places).astype(np.int64), np.concatenate(values)


def now(places):
    """What the places hold now (NaN where it can't be read)."""
    values = np.full(len(places), np.nan)
    order = np.argsort(places)
    sorted_places = places[order]
    for at, data in chunks(regions):
        lo = np.searchsorted(sorted_places, at, side="left")
        hi = np.searchsorted(sorted_places, at + len(data) - 8, side="right")
        if lo == hi:
            continue
        pick = order[lo:hi]
        raw = np.frombuffer(data, np.uint8)
        offsets = (places[pick] - at)[:, None] + np.arange(8)
        values[pick] = raw[offsets].copy().view("<f8").ravel()
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


def show(places, values):
    if 0 < len(places) <= FEW:
        for place, value in zip(places, values):
            print(f"  {int(place):#x}   holds {value:g}   {owner(int(place))}")


def watch(extra):
    """start, then after every shot keep the places that went down by 1 - until Ctrl+C."""
    fire = {int(info["fire"], 16) for info in load_names().values() if "fire" in info} or set(FIRE)
    places, values = start()
    print(f"{len(places)} places kept - shoot ONE shot at a time (shotgun), Ctrl+C to stop")
    card = hand = None
    last = {address: None for address in extra}
    shots = 0
    try:
        while True:
            me = find_me_card(mem)
            if me != card:
                print(f"  your card: {card if card is None else hex(card)} -> {me if me is None else hex(me)}")
                card = me
            for address in extra:
                try:
                    value = read_double(mem, address)
                except OSError:
                    value = None
                if value != last[address]:
                    print(f"  {address:#x}: {last[address]} -> {value}")
                    last[address] = value
            try:
                now_hand = None if me is None else read_kind(mem, me, 0, 0xA0)
            except OSError:
                now_hand = None
            if now_hand is not None and now_hand != hand:
                if hand in fire and now_hand not in fire:  # a shot just ended
                    shots += 1
                    new = now(places)
                    keep = new == values - 1
                    places, values = places[keep], new[keep]
                    print(f"shot {shots}: {len(places)} places went down by 1")
                    show(places, values)
                    np.savez(FILE, places=places, values=values)
                hand = now_hand
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        print(f"\nstopped after {shots} shots, {len(places)} places left (saved - shot/same still work on them)")


args = sys.argv[1:]
if args and args[0] == "watch":
    mem, regions, static_regions = attach()
    watch([int(word, 16) for word in args[1:]])
    raise SystemExit
if args == ["clear"]:
    if os.path.exists(FILE):
        os.remove(FILE)
    raise SystemExit("forgot everything - start with: python -m helpers_for_me.ammo_find start")
if len(args) != 1 or not (args[0] in ("start", "shot", "same") or args[0].isdigit()):
    raise SystemExit("usage: python -m helpers_for_me.ammo_find start | shot | same | 5 | clear")
word = args[0]

mem, regions, static_regions = attach()
try:
    kept = np.load(FILE)
    places, values = kept["places"], kept["values"]
except (OSError, ValueError, KeyError):
    places = values = None

if word == "start" or (places is None and word.isdigit()):
    places, values = start()
    if word.isdigit():
        keep = values == int(word)
        places, values = places[keep], values[keep]
    print(f"{len(places)} places kept - now shoot once and run: python -m helpers_for_me.ammo_find shot")
elif places is None:
    raise SystemExit("nothing kept yet - run: python -m helpers_for_me.ammo_find start")
else:
    new = now(places)
    if word == "shot":
        keep = new == values - 1
    elif word == "same":
        keep = new == values
    else:
        keep = new == int(word)
    print(f"{len(places)} -> {int(keep.sum())} places ({word})")
    places, values = places[keep], new[keep]
    if not len(places):
        print("nothing left - two shots instead of one? run start again")

np.savez(FILE, places=places, values=values)
show(places, values)
