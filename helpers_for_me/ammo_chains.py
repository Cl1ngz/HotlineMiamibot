# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/ammo_chains.py - a chain of links from YOU (or the game file) to your ammo
#
# The ammo (a 4-byte whole number) sits on the heap: it's the same place for every gun you hold, but it moves
# between game starts. find_path goes forward from a start and only 3 links deep - too little here. This goes
# BACKWARDS from the ammo: who points at it (or a bit before it), who points at those, ... up to DEPTH links,
# and keeps every chain that starts in your card / folder or in the game file. Saved to ammo_chains.json.
#
#   python -m helpers_for_me.ammo_chains find 0x30fb308   the address from ammo_watch (the same game run!)
#   python -m helpers_for_me.ammo_chains find 0x30fb308 0x400 6
#                         the same, but every link at most 0x400 before the next place, up to 6 links back
#                         (fields of an object sit close - big jumps are mostly heap neighbours by chance)
#   python -m helpers_for_me.ammo_chains check            what every saved chain leads to NOW (and remember it)
#   python -m helpers_for_me.ammo_chains keep shot        after ONE shot: keep the chains that went down by 1
#   python -m helpers_for_me.ammo_chains keep 22          keep the chains that lead to 22 now (the number on screen)
# Do check + shoot + keep shot with a gun in hand on a new floor, after a death, after a game restart -
# the chains that survive everything are the ones the bot can trust.
import json
import os
import sys
from collections import Counter

import numpy as np

from core.enemies import INSTANCE, RECORD, find_me_card
from core.memory import attach, find_game, read_u32

FILE = "ammo_chains.json"
DEPTH = 4  # how many links back from the ammo
NEAR = 0x2000  # a link counts if it points at most this far before the next place
CHUNK = 4 << 20
MOST_PLACES = 200000  # don't follow more places than this on one level (it grows fast)
SHOW = 20


def all_regions():
    """Every writable piece of the game's memory - but no devices."""
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
    """[(piece start, its 4-byte numbers), ...] of all the writable memory."""
    pieces = []
    for start, end in all_regions():
        for at in range(start, end, CHUNK):
            try:
                data = os.pread(mem, min(CHUNK, end - at), at)
            except OSError:
                continue
            pieces.append((at, np.frombuffer(data, "<u4", len(data) // 4).astype(np.int64)))
    return pieces


def pointing_at(targets):
    """(places, targets, offsets): every place whose number is at most near before one of the targets."""
    targets = np.unique(np.asarray(targets, np.int64))
    places, hits, offsets = [], [], []
    for at, values in pieces:
        i = np.minimum(np.searchsorted(targets, values), len(targets) - 1)
        gap = targets[i] - values
        hit = np.nonzero((gap >= 0) & (gap <= near) & (values >= 0x10000))[0]
        places.append(at + 4 * hit)
        hits.append(targets[i[hit]])
        offsets.append(gap[hit])
    return np.concatenate(places), np.concatenate(hits), np.concatenate(offsets)


def root_of(place):
    """(start, first offsets) if the place is in your card / folder or the game file, else None."""
    if card <= place < card + RECORD:
        return "me", [place - card]
    if folder <= place < folder + INSTANCE:
        return "me", [0, place - folder]  # card +0 links to your folder
    if any(s <= place < e for s, e in static_regions):
        return place, []
    return None


def follow(chain):
    """Where a chain ends right now: start at your card (or read the fixed place), then link by link."""
    here = card if chain["start"] == "me" else read_u32(mem, chain["start"])
    for offset in chain["offsets"]:
        here = read_u32(mem, here + offset)
    return here + chain["last"]


def text(chain):
    start = "your card" if chain["start"] == "me" else f"[{chain['start']:#x}]"
    return start + "".join(f" -> +{o:#x}" for o in chain["offsets"]) + f"  then +{chain['last']:#x}"


def find(ammo):
    parent = {}  # place -> (the place its link leads to, offset)
    chains = []
    targets = [ammo]
    for depth in range(1, depth_most + 1):
        places, hits, offsets = pointing_at(targets)
        new = []
        for place, hit, offset in zip(places.tolist(), hits.tolist(), offsets.tolist()):
            if place in parent or place == ammo:
                continue
            parent[place] = (hit, offset)
            new.append(place)
            root = root_of(place)
            if root:
                start, first = root
                steps, here = [], place
                while here != ammo:
                    here, offset_here = parent[here]
                    steps.append(offset_here)
                chains.append({"start": start, "offsets": first + steps[:-1], "last": steps[-1]})
        print(f"depth {depth}: {len(new)} places link there, {len(chains)} chains so far")
        if len(new) > MOST_PLACES:
            print(f"  (only the first {MOST_PLACES} are followed further)")
            new = new[:MOST_PLACES]
        targets = new
        if not new:
            break
    # the same chain can be found twice (from your card +0 AND from inside your folder) - keep one
    chains = list({json.dumps(c, sort_keys=True): c for c in chains}.values())
    # found last time too (another floor / game start) = much surer
    try:
        with open(FILE) as f:
            before = {json.dumps(c, sort_keys=True) for c in json.load(f)["chains"]}
    except (OSError, ValueError, KeyError):
        before = set()
    for chain in chains:
        chain["again"] = json.dumps(chain, sort_keys=True) in before
    # found again first, then yours, then the shortest
    chains.sort(key=lambda c: (not c["again"], c["start"] != "me", len(c["offsets"])))
    for chain in chains:
        del chain["again"]
    again = sum(json.dumps(c, sort_keys=True) in before for c in chains)
    with open(FILE, "w") as f:
        json.dump({"ammo": ammo, "chains": chains[:2000]}, f)
    print(f"\n{len(chains)} chains saved to {FILE} ({again} of them were found last time too), the best:")
    for chain in chains[:SHOW]:
        mark = "  (again)" if json.dumps(chain, sort_keys=True) in before else ""
        print(f"  {text(chain)}{mark}")
    if not chains:
        print("  none - send me this output")


def ends(chains):
    """What every chain leads to now (None: a link on the way is junk)."""
    found = []
    for chain in chains:
        try:
            found.append(int.from_bytes(os.pread(mem, 4, follow(chain)), "little", signed=True))
        except (OSError, OverflowError):
            found.append(None)
    return found


def check(rule=None):
    """Show what the chains lead to now - with a rule, first keep only the chains that pass it."""
    with open(FILE) as f:
        saved = json.load(f)
    chains = saved["chains"]
    now = ends(chains)
    if rule is not None:
        before = saved.get("last") or [None] * len(chains)
        keep = [i for i, value in enumerate(now) if value is not None and rule(value, before[i])]
        if not keep:
            raise SystemExit(
                f"none of the {len(chains)} chains passed - nothing removed (a gun WITH ammo in hand? one real shot?)"
            )
        print(f"{len(chains)} -> {len(keep)} chains kept")
        chains, now = [chains[i] for i in keep], [now[i] for i in keep]
    with open(FILE, "w") as f:
        json.dump({**saved, "chains": chains, "last": now}, f)
    print(f"{len(chains)} chains - what they lead to now (most common first):")
    for value, count in Counter(now).most_common(8):
        print(f"  {count:5} chains -> {value}")
    print("\nthe best chains now:")
    for chain, value in list(zip(chains, now))[:SHOW]:
        print(f"  {str(value):>6}   {text(chain)}")


args = sys.argv[1:]
usage = "usage: python -m helpers_for_me.ammo_chains find 0x30fb308 [0x400 6] | check | keep shot | keep 22"
if not args or args[0] not in ("find", "check", "keep") or (args[0] == "keep" and len(args) != 2):
    raise SystemExit(usage)
if args[0] == "find" and not 2 <= len(args) <= 4:
    raise SystemExit(usage)
if args[0] == "keep" and not (args[1] == "shot" or args[1].isdigit()):
    raise SystemExit(usage)
mem, regions, static_regions = attach()
card = find_me_card(mem)
if card is None:
    raise SystemExit("can't find you - be in a level")
folder = read_u32(mem, card)
if args[0] == "find":
    near = int(args[2], 16) if len(args) > 2 else NEAR
    depth_most = int(args[3]) if len(args) > 3 else DEPTH
    print(f"taking a photo of the memory... (links at most {near:#x} before, up to {depth_most} links)")
    pieces = photo()
    find(int(args[1], 16))
elif args[0] == "check":
    check()
elif args[1] == "shot":
    check(lambda value, last: last is not None and value == last - 1)
else:
    check(lambda value, last: value == int(args[1]))
