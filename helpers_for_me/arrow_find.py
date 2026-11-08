# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/arrow_find.py - WHERE does the game keep the red arrow ("do this next")?
#
# The red arrow always points at what to do next. In the apartment: the TV, then the round thing on the floor
# of the green room (card +0x10 0x53 at about (368,244)), then the stairs. If the bot can read what the arrow
# points at, it needs no special rule for every scene - it just goes there.
#
# Whatever form the game keeps "what's next" in (a step number, a pointer, an id, the arrow's spot...),
# it does something most numbers don't: it changes when you USE something - and ONLY then.
# So this looks at ALL the game's writable memory at 4 moments (Enter in THIS terminal for each one):
#   1. stand in front of the TV, the arrow over it - don't touch it yet
#   2. use the TV (walk in + LMB), click the text away, stay there
#   3. walk to the round thing (the arrow is over it now), stand next to it - don't use it yet
#   4. use it (LMB), click the text away, stay there
# and keeps only the 4-byte numbers that held still during every moment and
#     CHANGED 1 -> 2 (you used the TV)   STAYED 2 -> 3 (you only walked)   CHANGED 3 -> 4 (you used the thing)
# The text boxes leave big BLOCKS of such numbers (the letters, their pictures) - those are only counted.
# The LONELY ones (1-4 numbers on their own) are scored: a pointer to a card, a counter that goes +1 at
# every use, a double that looks like a position, the game's globals... - the best ones first.
#
#   python -m helpers_for_me.arrow_find           the 4 moments (only READS memory)
#   python -m helpers_for_me.arrow_find --again   print the last results again (from arrow_find.npz, no game)
#   python -m helpers_for_me.arrow_find --watch   the best ones, live: go to the stairs, the car, take the
#                                                 briefcase, the next level - which number follows the arrow?
# The results are saved in arrow_find.npz right after moment 4 (before printing). Send me the printout + the npz.
import json
import math
import os
import struct
import sys
import time

import numpy as np

from core.enemies import INSTANCE, RECORD, find_me_card
from core.memory import X_OFF, Y_OFF, attach
from core.shelf import Shelf

GAP = 0.3  # seconds between the two looks of one moment - a number must be the same in both
CHUNK = 16 << 20  # read the memory 16 MB at a time
LONELY = 4  # a run of at most this many changed numbers in a row = lonely (more = a block: text, graphics)
SHOW = 40  # print at most this many lonely numbers
BLOCKS = 8  # ...and this many of the biggest blocks
WATCH = 12  # --watch shows this many (the best ones)
JSON_FILE, NPZ_FILE = "arrow_find.json", "arrow_find.npz"


def u32(data, offset):
    return int.from_bytes(data[offset : offset + 4], "little")


def f64(data, offset):
    return struct.unpack_from("<d", data, offset)[0]


# ---------------------------------------------------------------- reading the game


def look():
    """One photo of every card: {"you": (x, y) or None, "table": set, "cards": {card: (card bytes, folder bytes)}}."""
    shelf = Shelf(mem)
    table = set(shelf.records)
    cards = {}
    for card in set(shelf.cards) | table:
        try:
            data = shelf.read(RECORD, card)
            folder = shelf.read(INSTANCE, u32(data, 0))
        except OSError:
            continue
        if len(data) == RECORD and len(folder) == INSTANCE:
            cards[card] = (data, folder)
    me = find_me_card(shelf) if table else None
    you = (f64(cards[me][0], X_OFF), f64(cards[me][0], Y_OFF)) if me in cards else None
    return {"you": you, "table": table, "cards": cards}


def moment(number, text):
    """Wait for Enter (until you can be seen). -> [a photo of the cards]"""
    while True:
        input(f"\n{number}. {text}\n   Enter = photo: ")
        shot = look()
        if shot["you"] is not None:
            print(f"   ok - you at ({shot['you'][0]:.0f},{shot['you'][1]:.0f}), {len(shot['cards'])} cards")
            return [shot]
        print("   can't see you (menu / loading / Esc?) - try again")


def pieces():
    """(start, size) pieces of the game's writable memory."""
    for start, end in regions:
        for at in range(start, end, CHUNK):
            yield at, min(CHUNK, end - at)


def read_words(at, size):
    """The piece as 4-byte numbers (empty if it can't be read)."""
    try:
        data = os.pread(mem, size, at)
    except OSError:
        data = b""
    return np.frombuffer(data, dtype="<u4", count=len(data) // 4)


def read_at(addresses):
    """The 4-byte numbers at these addresses right now (-1 = can't read), one pass over the memory."""
    out = np.full(len(addresses), -1, dtype=np.int64)
    for at, size in pieces():
        inside = np.nonzero((addresses >= at) & (addresses + 4 <= at + size))[0]
        if len(inside) == 0:
            continue
        words = read_words(at, size)
        index = (addresses[inside] - at) // 4
        ok = index < len(words)
        out[inside[ok]] = words[index[ok]]
    return out


def around(addresses):
    """For every address: the number before it, the number itself and the number after it (a double is 2 of
    them), read twice GAP apart.  -> (values (n, 3), did the number itself hold still)"""
    spots = np.concatenate([addresses - 4, addresses, addresses + 4])
    first = read_at(spots).reshape(3, len(addresses)).T
    time.sleep(GAP)
    again = read_at(addresses)
    return first, (first[:, 1] == again) & (again >= 0)


# ---------------------------------------------------------------- telling what a number is


def nice(value):
    return math.isfinite(value) and (value == 0 or 1e-4 < abs(value) < 1e8)


def as_float(word):
    return struct.unpack("<f", struct.pack("<I", int(word)))[0]


def as_double(low, high):
    return struct.unpack("<d", struct.pack("<II", int(low), int(high)))[0]


def readings(per_moment):
    """The 4 moments' (before, itself, after) numbers -> the ways to read them: [(name, [4 values])]."""
    middle = [int(v[1]) for v in per_moment]
    ways = [("u32", middle)]
    floats = [as_float(v) for v in middle]
    if all(nice(v) for v in floats) and any(v != 0 for v in floats):
        ways.append(("float", floats))
    for name, low, high in (("double", 1, 2), ("double@-4", 0, 1)):  # the double starting here / 4 bytes before
        doubles = [as_double(v[low], v[high]) for v in per_moment]
        if all(nice(v) for v in doubles) and len(set(doubles)) > 1:
            ways.append((name, doubles))
            break
    return ways


def way_text(name, values):
    if name == "u32":
        return "u32 " + " -> ".join(f"{int(v):#x}" for v in values)
    return f"{name} " + " -> ".join(f"{v:g}" for v in values)


class Places:
    """Which card / folder / globals an address is inside of - fast, for thousands of addresses."""

    def __init__(self, shots, statics):
        self.entries = {}  # card -> (card bytes, folder bytes) - from the first photo that has it (the newest)
        for shot in shots:
            for card, entry in shot["cards"].items():
                self.entries.setdefault(card, entry)
        self.cards = np.array(sorted(self.entries), dtype=np.int64)
        self.folder_card = {u32(entry[0], 0): card for card, entry in self.entries.items()}
        self.folders = np.array(sorted(self.folder_card), dtype=np.int64)
        self.statics = statics

    def describe(self, card):
        data, folder = self.entries[card]
        return (
            f"({f64(data, X_OFF):4.0f},{f64(data, Y_OFF):4.0f}) layer {u32(data, 0x14):#x}"
            f" +0x10 {u32(data, 0x10):#x} picture {u32(folder, 0x10):#x}"
        )

    def owner(self, number):
        """The card this number points at (its own address or its folder's), or None."""
        if number in self.entries:
            return number
        return self.folder_card.get(number)

    def where(self, address):
        """(kind, text): kind = "globals" / "card" / "folder" / "object" / "" """
        if len(self.cards):
            i = np.searchsorted(self.cards, address, side="right") - 1
            if i >= 0 and address < self.cards[i] + RECORD:
                card = int(self.cards[i])
                return "card", f"card {card:#x} +{address - card:#x}  {self.describe(card)}"
        if len(self.folders):
            i = np.searchsorted(self.folders, address, side="right") - 1
            if i >= 0 and address < self.folders[i] + INSTANCE:
                base = int(self.folders[i])
                card = self.folder_card[base]
                return "folder", f"folder +{address - base:#x} of card {card:#x}  {self.describe(card)}"
            low, high = int(self.folders[0]), int(self.folders[-1])
            if low - 64 * INSTANCE <= address < high + 64 * INSTANCE:  # folders lie in a row, one every 0x6D0
                base = address - (address - low) % INSTANCE
                return "object", f"folder +{address - base:#x} of the object at {base:#x} (no card for it)"
        if any(start <= address < end for start, end in self.statics):
            return "globals", "the game's own globals (the same address every launch)"
        return "", ""


def score(per_moment, ways, kind, places):
    """How much this number looks like "what's next": (points, [why])."""
    points, why = 0, []
    middle = [int(v[1]) for v in per_moment]
    pointed = [places.owner(v) for v in middle]
    if sum(card is not None for card in pointed) >= 2:
        points += 4
        why.append("POINTER to " + " -> ".join(places.describe(c) if c else "?" for c in pointed))
    steps = (middle[1] - middle[0], middle[3] - middle[2])
    if all(v < 100000 for v in middle):
        if steps[0] == steps[1] and 0 < steps[0] <= 4:
            points += 3
            why.append(f"COUNTER +{steps[0]}")
        else:
            points += 1
            why.append("small number")
    for name, values in ways[1:]:
        if name.startswith("double") and all(-10 <= v <= 5000 for v in values):
            points += 2
            why.append("double, like a position" if max(values) - min(values) > 30 else "small double")
            break
    points += {"globals": 3, "object": 2, "folder": 2, "card": 1}.get(kind, 0)
    return points, why


def analyse(addresses, values, shots, statics):
    """Print the results. -> the best lonely ones (for --watch)."""
    places = Places(shots, statics)
    order = np.argsort(addresses)
    addresses, values = addresses[order], values[:, order]
    # runs of changed numbers in a row (8 bytes apart at most)
    run = np.concatenate([[0], np.cumsum(np.diff(addresses) > 8)]) if len(addresses) else np.zeros(0, int)
    sizes = np.bincount(run) if len(run) else np.zeros(0, int)
    lonely = np.nonzero(sizes[run] <= LONELY)[0] if len(run) else []
    blocks = [r for r in np.argsort(-sizes) if sizes[r] > LONELY]
    print(f"\n{len(addresses)} numbers: {len(lonely)} lonely, the rest in {len(blocks)} blocks (text / graphics?)")

    found = []
    for i in lonely:
        per_moment = [values[m, i] for m in range(4)]
        ways = readings(per_moment)
        kind, where = places.where(int(addresses[i]))
        points, why = score(per_moment, ways, kind, places)
        ways = [[name, [float(v) for v in vals]] for name, vals in ways]
        found.append({"address": hex(int(addresses[i])), "points": points, "why": why, "where": where, "ways": ways})
    found.sort(key=lambda c: (-c["points"], int(c["address"], 16)))

    print("\nLONELY numbers, the best first  (moment 1 -> 2 -> 3 -> 4):")
    for c in found[:SHOW]:
        print(f"  [{c['points']:2}] {c['address']}  " + "   ".join(way_text(n, v) for n, v in c["ways"]))
        for line in ([c["where"]] if c["where"] else []) + c["why"]:
            print(f"         {line}")
    if len(found) > SHOW:
        print(f"  ...and {len(found) - SHOW} more")
    if not found:
        print("  nothing")

    print(f"\nthe biggest BLOCKS ({BLOCKS} of {len(blocks)}):")
    for r in blocks[:BLOCKS]:
        inside = np.nonzero(run == r)[0]
        start, end = int(addresses[inside[0]]), int(addresses[inside[-1]]) + 4
        print(f"  {start:#x}-{end:#x}  {len(inside):6} numbers   {places.where(start)[1]}")
    return found


# ---------------------------------------------------------------- the 3 ways to run it


def find():
    total = sum(end - start for start, end in regions)
    print(f"looking in {len(regions)} memory regions, {total / 1e6:.0f} MB")

    one = moment(1, "stand in front of the TV, the arrow over it - DON'T touch it yet")
    print("   photographing the whole memory twice...")
    photo = {at: read_words(at, size) for at, size in pieces()}
    time.sleep(GAP)
    still = {}
    for at, size in pieces():
        again = read_words(at, size)
        if len(again) == len(photo[at]):
            still[at] = photo[at] == again
    one.append(look())
    print(f"   ok, {sum(int(s.sum()) for s in still.values()) * 4 / 1e6:.0f} MB held still")

    two = moment(2, "use the TV (walk in + LMB), click the text away, stay where you are")
    addresses, values_1 = [], []
    for at, size in pieces():
        if at not in still:
            continue
        now = read_words(at, size)
        if len(now) != len(photo[at]):
            continue
        hit = np.nonzero(still[at] & (now != photo[at]))[0]
        if len(hit):
            before = np.clip(hit - 1, 0, len(now) - 1)
            after = np.clip(hit + 1, 0, len(now) - 1)
            addresses.append(at + hit.astype(np.int64) * 4)
            values_1.append(np.stack([photo[at][before], photo[at][hit], photo[at][after]], axis=1))
    del photo, still  # ~300 MB back
    if not addresses:
        raise SystemExit("   nothing changed at all?")
    addresses = np.concatenate(addresses)
    values_1 = np.concatenate(values_1).astype(np.int64)
    values_2, held = around(addresses)
    keep = held & (values_2[:, 1] != values_1[:, 1])
    addresses, values = addresses[keep], [values_1[keep], values_2[keep]]
    two.append(look())
    print(f"   {len(addresses)} numbers changed when you used the TV")

    three = moment(3, "walk to the round thing (the arrow is over it now), stand next to it - DON'T use it yet")
    values_3, held = around(addresses)
    keep = held & (values_3[:, 1] == values[1][:, 1])
    addresses, values = addresses[keep], [v[keep] for v in values] + [values_3[keep]]
    three.append(look())
    print(f"   {len(addresses)} of them did NOT change while you walked")

    four = moment(4, "use it (LMB), click the text away, stay where you are")
    values_4, held = around(addresses)
    keep = held & (values_4[:, 1] != values[2][:, 1])
    addresses, values = addresses[keep], np.stack([v[keep] for v in values] + [values_4[keep]])
    four.append(look())
    print(f"   {len(addresses)} of them changed again when you used the round thing")

    moments = [one, two, three, four]
    save(moments, addresses, values)  # first save, then print (printing a lot can take a moment)
    print(f"   saved in {NPZ_FILE}")
    found = analyse(addresses, values, [s for shots in moments for s in shots][::-1], static_regions)
    with open(JSON_FILE, "w") as f:
        json.dump(found[:WATCH], f, indent=1)
    print(f"\nthe best {WATCH} are in {JSON_FILE} - live: python -m helpers_for_me.arrow_find --watch")


def save(moments, addresses, values):
    arrays = {"addresses": addresses, "values": values, "statics": np.array(static_regions, dtype=np.int64)}
    for m, shots in enumerate(moments, 1):
        for i, shot in enumerate(shots):
            cards = sorted(shot["cards"])
            key = f"m{m}_{i}"
            arrays[key + "_cards"] = np.array(cards, dtype=np.uint32)
            for part, name, size in ((0, "_card", RECORD), (1, "_folder", INSTANCE)):
                data = b"".join(shot["cards"][c][part] for c in cards)
                arrays[key + name] = np.frombuffer(data, dtype=np.uint8).reshape(len(cards), size)
            arrays[key + "_table"] = np.array(sorted(shot["table"]), dtype=np.uint32)
            arrays[key + "_you"] = np.array(shot["you"] or (0.0, 0.0))
    np.savez_compressed(NPZ_FILE, **arrays)


def again():
    """The results of the last run again, from arrow_find.npz (the game doesn't have to run)."""
    try:
        saved = np.load(NPZ_FILE)
    except OSError:
        raise SystemExit(f"no {NPZ_FILE} yet - run it without --again first")
    shots = []
    for key in sorted(k[: -len("_cards")] for k in saved.files if k.endswith("_cards")):
        cards = saved[key + "_cards"].tolist()
        entries = zip(saved[key + "_card"], saved[key + "_folder"])
        shots.append({"cards": {c: (a.tobytes(), b.tobytes()) for c, (a, b) in zip(cards, entries)}})
    statics = [tuple(r) for r in saved["statics"].tolist()]
    found = analyse(saved["addresses"], saved["values"], shots[::-1], statics)
    with open(JSON_FILE, "w") as f:
        json.dump(found[:WATCH], f, indent=1)


def watch():
    try:
        with open(JSON_FILE) as f:
            found = json.load(f)[:WATCH]
    except (OSError, ValueError):
        raise SystemExit(f"no {JSON_FILE} yet - run it without --watch first")
    if not found:
        raise SystemExit(f"{JSON_FILE} is empty - nothing was found")
    print("go on in the game (the stairs, the car, the next level, the briefcase...) - Ctrl+C = end")
    print("which number changes every time the arrow moves to the next thing - and only then?\n")
    while True:
        lines = []
        you = look()["you"]
        lines.append(f"you ({you[0]:4.0f},{you[1]:4.0f})" if you else "you ?          ")
        for i, c in enumerate(found):
            address = int(c["address"], 16)
            try:
                data = os.pread(mem, 12, address - 4)
            except OSError:
                data = b""
            if len(data) < 12:
                now = "?"
            else:
                now = f"{u32(data, 4):#10x}"
                names = [name for name, _ in c["ways"]]
                if "float" in names:
                    now += f"  float {struct.unpack_from('<f', data, 4)[0]:g}"
                if "double" in names:
                    now += f"  double {f64(data, 4):g}"
                elif "double@-4" in names:
                    now += f"  double {f64(data, 0):g}"
            lines.append(f"[{i:2}] {c['address']}  {now:40}  was {way_text(*c['ways'][0])}")
        print("\n".join(line + "    " for line in lines))
        print(f"\033[{len(lines)}A", end="", flush=True)  # back up, to draw over the same lines next time
        time.sleep(0.3)


if "--again" in sys.argv:
    again()
    raise SystemExit
mem, regions, static_regions = attach()
try:
    watch() if "--watch" in sys.argv else find()
except KeyboardInterrupt:
    print("\n" * (WATCH + 2) if "--watch" in sys.argv else "")
