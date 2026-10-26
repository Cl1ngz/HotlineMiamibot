# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/check_chains.py - which saved chains STILL lead to the look (e.g. after you died)?
#
# find_path saved every chain it found to chains_<target>.json. The look holds exactly the crosshair's X
# (and Y) whenever the mouse stands still - so a chain that still works ends at a double equal to the crosshair.
# This follows every saved chain NOW and prints the ones that end at the crosshair's X (or Y).
#
#   python -m helpers_for_me.check_chains chains_2845858.json x     (chains to the look X)
#   python -m helpers_for_me.check_chains chains_2845808.json y     (chains to the look Y)
#   be in a level; move the mouse when told, then LET GO of it
import json
import sys

from core.enemies import find_aim, find_me_card
from core.memory import attach, read_double, read_u32, wait

if len(sys.argv) < 3 or sys.argv[2] not in ("x", "y"):
    raise SystemExit("usage: python -m helpers_for_me.check_chains chains_2845858.json x")
with open(sys.argv[1]) as f:
    saved = json.load(f)
axis = 0 if sys.argv[2] == "x" else 1

mem, regions, static_regions = attach()


def follow(chain):
    """Where this chain ends right now (None if a link on the way is junk)."""
    *offsets, last = chain
    try:
        if saved["start"] == "me":
            here = find_me_card(mem)
            if here is None:
                return None
        else:
            here = read_u32(mem, saved["start"])
        for offset in offsets:
            here = read_u32(mem, here + offset)
        return here + last
    except OSError:
        return None


find_aim(mem)  # warm-up
wait("move the mouse a little, then LET GO of it", 3)
aim = find_aim(mem)
if aim is None:
    raise SystemExit("no crosshair - are you in a level?")
wanted = aim[axis]
print(f"crosshair {'XY'[axis]} = {wanted!r}   (saved for {saved['target']:#x}, {len(saved['chains'])} chains)\n")

hits = {}
for chain in saved["chains"]:
    end = follow(chain)
    if end is None:
        continue
    try:
        if read_double(mem, end) == wanted:
            hits.setdefault(end, []).append(chain)
    except OSError:
        continue

if not hits:
    raise SystemExit("no saved chain ends at the crosshair's value any more")
for end, chains in hits.items():
    print(f"{end:#x} holds the crosshair's {'XY'[axis]} - reached by {len(chains)} chain(s), e.g.:")
    for chain in chains[:5]:
        print(f"   {chain}")
