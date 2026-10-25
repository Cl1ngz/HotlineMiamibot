# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/find_mouse.py - where does the engine keep the mouse position? (the "notebook")
#
# write_aim showed the game puts the crosshair's X back every frame: crosshair.x = mouse x.
# So somewhere the game keeps the mouse x and y, and they hold EXACTLY the crosshair's X and Y at every moment.
#   round 1:   every double in the game's memory that equals the crosshair's X (and Y) right now
#   round 2+:  you move the mouse, the crosshair moves - keep only the places that moved with it
#
#   python -m helpers_for_me.find_mouse        (be in a level; move the mouse DIAGONALLY, then LET GO when told)
import numpy as np

from core.enemies import RECORD, find_aim, find_aim_card
from core.memory import X_OFF, Y_OFF, attach, read_double, take_snapshot, wait

ROUNDS = 6  # at most this many rounds
MIN_ROUNDS = 3  # always move the mouse at least twice - a place only counts if it FOLLOWED the mouse
ENOUGH = 5  # after that, stop early when this few places are left (per axis)
AXES = {"x": X_OFF, "y": Y_OFF}


def crosshair(mem, card):
    """{"x": crosshair X, "y": crosshair Y} right now."""
    return {axis: read_double(mem, card + offset) for axis, offset in AXES.items()}


mem, regions, static_regions = attach()
find_aim(mem)  # warm-up: find_aim has to see the crosshair move once to tell it from a frozen copy
wait("move the mouse a little, then LET GO of it", 3)
card = find_aim_card(mem)
if card is None:
    raise SystemExit("no crosshair - are you in a level?")
now = crosshair(mem, card)

# round 1: look through ALL the game's writable memory for doubles that hold exactly the crosshair's X / Y
print(f"round 1: crosshair at {now['x']}, {now['y']} - looking for every double that holds exactly these...")
candidates = {"x": set(), "y": set()}
for start, data in take_snapshot(mem, regions).items():
    for shift in (0, 4):  # doubles usually start every 8 bytes - check the spots in between too, just in case
        count = (len(data) - shift) // 8
        values = np.frombuffer(data, dtype="<f8", count=count, offset=shift)
        for axis in AXES:
            for i in np.flatnonzero(values == now[axis]):
                address = start + shift + int(i) * 8
                # the crosshair card holds them itself - we know those already, they're not the notebook
                if not card <= address < card + RECORD:
                    candidates[axis].add(address)
print(f"  {len(candidates['x'])} places hold the X, {len(candidates['y'])} hold the Y")


def keep_going(round_number):
    if round_number > ROUNDS or not (candidates["x"] or candidates["y"]):
        return False
    return round_number <= MIN_ROUNDS or max(len(places) for places in candidates.values()) > ENOUGH


# round 2+: the mouse moves, the notebook moves with it - everything else drops out
round_number = 2
while keep_going(round_number):
    wait(f"round {round_number}: move the mouse DIAGONALLY somewhere else, then LET GO of it", 3)
    new = crosshair(mem, card)
    if new["x"] == now["x"] or new["y"] == now["y"]:
        print("  the crosshair didn't move on both axes - move the mouse diagonally, further")
        continue
    now = new
    for axis in AXES:
        still = set()
        for address in candidates[axis]:
            try:
                if read_double(mem, address) == now[axis]:
                    still.add(address)
            except OSError:
                continue  # that memory is gone
        candidates[axis] = still
    print(f"round {round_number}: crosshair at {now['x']:.1f}, {now['y']:.1f} - "
          f"{len(candidates['x'])} places followed the X, {len(candidates['y'])} followed the Y")
    round_number += 1


def where(address):
    return "FIXED address (inside the game file)" if any(s <= address < e for s, e in static_regions) else ""


print(f"\ncrosshair at {now['x']:.1f}, {now['y']:.1f}")
for axis in AXES:
    print(f"places that follow the mouse {axis.upper()}:")
    for address in sorted(candidates[axis]):
        print(f"  {address:#x}   {read_double(mem, address):8.1f}   {where(address)}")
    if not candidates[axis]:
        print("  none")
print("\nLook at the addresses: is any Y place close to the X place 0x2845858? How far (in hex)?")
