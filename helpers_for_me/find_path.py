# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/find_path.py - is there a chain of links from a FIXED address to a place we found?
#
# The game finds its own things like this: start in a locker with a fixed address (inside the game file),
# take the link from it, go some lockers further, take the next link... (like read_kind, but several times).
# If such a chain ends right at the click byte, the bot can find the byte at every start - no searching.
# This starts at the fixed locker 0xbb0d68, follows every link it meets (up to DEPTH links deep, looking
# OFFSETS bytes into every object) and prints every chain that lands at most NEAR bytes before the target.
#
# With "me" it starts at YOUR CARD instead (found by find_me in every life) - for things that belong to your
# character: such a chain moves together with you when you die and come back.
#
#   python -m helpers_for_me.find_path 0x181cc29      (the click byte from find_click 0x80, from THIS game run)
#   python -m helpers_for_me.find_path 0x2845858 me   (start at your card - e.g. for the look)
# Every chain found is also saved to chains_<target>.json - check_chains tests them later (e.g. after you die).
import json
import os
import sys

from core.enemies import find_me_card
from core.memory import attach, read_u32

START = 0xBB0D68  # the fixed locker the game itself uses (we saw it in the code after GetFocus)
DEPTH = 3  # how many links deep
OFFSETS = 0x1000  # how far into every object to look for links
NEAR = 0x2000  # a chain counts if it lands this close BEFORE the target (the rest is the last offset)
MAX_OBJECTS = 30000  # don't look into more objects than this on one level (it grows fast)

if len(sys.argv) < 2:
    raise SystemExit("usage: python -m helpers_for_me.find_path 0x181cc29   (the place you want to reach)")
target = int(sys.argv[1], 16)
from_me = len(sys.argv) > 2 and sys.argv[2] == "me"

mem, regions, static_regions = attach()
if from_me:
    card = find_me_card(mem)
    if card is None:
        raise SystemExit("can't find you - are you in a level?")


def looks_like_link(value):
    """A number that points into the game's memory (and so could be a link)."""
    return any(start <= value < end for start, end in regions)


def links_in(address, size=OFFSETS):
    """(offset, link) for every 4-byte spot in the object at this address that looks like a link."""
    try:
        data = os.pread(mem, size, address)
    except OSError:
        return []
    found = []
    for offset in range(0, len(data) - 3, 4):
        value = int.from_bytes(data[offset : offset + 4], "little")
        if looks_like_link(value):
            found.append((offset, value))
    return found


paths = []
# every step: (where we are now, the offsets that got us here)
if from_me:
    level = [(card, [])]  # start inside your card itself
    start_text = f"your card {card:#x}"
else:
    level = [(read_u32(mem, START), [])]  # start at what the fixed locker links to
    start_text = f"[{START:#x}]"
seen = set()
for depth in range(1, DEPTH + 1):
    next_level = []
    for here, steps in level:
        if here in seen:
            continue
        seen.add(here)
        # your card is only 0xB8 bytes long - past that are other cards, not yours
        size = 0xB8 if from_me and depth == 1 else OFFSETS
        for offset, link in links_in(here, size):
            if 0 <= target - link < NEAR:
                paths.append(steps + [offset, target - link])
            next_level.append((link, steps + [offset]))
    print(f"depth {depth}: looked into {len(level)} objects, {len(paths)} chain(s) found so far")
    if len(next_level) > MAX_OBJECTS:
        print(f"  ({len(next_level)} objects for the next level - only the first {MAX_OBJECTS} are checked)")
        next_level = next_level[:MAX_OBJECTS]
    level = next_level

if not paths:
    raise SystemExit(f"no chain from {start_text} to {target:#x} within {DEPTH} links")
save_file = f"chains_{target:x}.json"
with open(save_file, "w") as f:
    json.dump({"start": "me" if from_me else START, "target": target, "chains": paths}, f)
print(f"\nall {len(paths)} chains saved to {save_file}")
print(f"\nchains from {start_text} to {target:#x} (shortest first):")
for path in sorted(paths, key=len)[:15]:
    links, last = path[:-1], path[-1]
    text = start_text + "".join(f" -> +{offset:#x}" for offset in links) + f"  then +{last:#x}"
    print(f"  {text}")
