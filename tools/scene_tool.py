# https://github.com/Cl1ngz/HotlineMiamibot
# tools/scene_tool.py - show the bot where to walk on a floor where nothing tells it (core/scenes.py)
#
# Be on that floor (the bot not running), then:
#   python -m tools.scene_tool              the name of THIS floor, and every spot saved so far
#   python -m tools.scene_tool save         put the crosshair on the spot (3 s) - saved for THIS floor
#   python -m tools.scene_tool remove       forget the spot of THIS floor
#
# After a save hmbot walks there on this floor (when there's nothing else to do) and taps LMB - the talk goes on.
import sys

from core.enemies import find_aim
from core.memory import attach, wait
from core.scenes import load_scenes, save_scenes, scene_id
from core.shelf import Shelf
from core.walls import real_walls

args = sys.argv[1:]
if args not in ([], ["save"], ["remove"]):
    raise SystemExit("usage: python -m tools.scene_tool [save | remove]")

mem, regions, static_regions = attach()
shelf = Shelf(mem)
if not shelf.records:
    raise SystemExit("no table - are you on a floor?")
walls = real_walls(shelf, shelf.records, shelf.cards)
here = scene_id(walls)
spots = load_scenes()
print(f"this floor: {here}   ({len(walls)} walls)")

if args == ["save"]:
    find_aim(mem)  # warm-up: find_aim has to see the crosshair once
    wait("put the crosshair where the bot should walk, and keep it there", 3)
    aim = find_aim(mem)
    if aim is None:
        raise SystemExit("no crosshair - move the mouse in the game and try again")
    spots[here] = [round(aim[0]), round(aim[1])]
    save_scenes(spots)
    print(f"saved: on {here} the bot walks to {spots[here][0]},{spots[here][1]}")
elif args == ["remove"]:
    if spots.pop(here, None) is None:
        raise SystemExit("nothing saved for this floor")
    save_scenes(spots)
    print(f"removed the spot of {here}")
else:
    if not spots:
        print("no spots saved yet")
    for name, (x, y) in spots.items():
        print(f"  {name}: walk to {x},{y}" + ("   <- this floor" if name == here else ""))
