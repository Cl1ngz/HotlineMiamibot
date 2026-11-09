# https://github.com/Cl1ngz/HotlineMiamibot
# core/scenes.py - a name for every floor, and the spots the bot was shown on them (a library)
#
# Some floors have nothing that tells the bot where to go: no enemy, no red arrow, no stairs, no car -
# the masks' room after the tutorial, where the talk starts only when you walk up to them.
# The same floor always has the same walls in the same places, so the walls give it a name that is the
# same every time you come back. tools/scene_tool.py saves a spot under that name, once - hmbot walks
# there by itself (and clicks the talk away) every time it's on that floor and has nothing else to do.
#
#   scene_id(walls)      ->  "3fa9c1d2"       (walls = real_walls(...): a list of (xy, box) pairs)
#   load_scenes()        ->  {name: [x, y]}   (from scenes.json)
#   save_scenes(spots)
import hashlib
import json
import os

SCENES_FILE = "scenes.json"
# floor name -> boxes of the doors that never open there (hmbot pushed them twice and they didn't)
DOORS_FILE = "doors.json"


def scene_id(walls):
    """A short name for this floor from its walls: the same walls -> the same name, every time you come here."""
    # the wall spots rounded to whole numbers, sorted (the game can list the same walls in another order)
    spots = sorted((round(x), round(y)) for (x, y), box in walls)
    return hashlib.md5(str(spots).encode()).hexdigest()[:8]


def load_scenes():
    """{floor name: [x, y]} of every spot the bot was shown - empty when nothing was saved yet."""
    if not os.path.exists(SCENES_FILE):
        return {}
    with open(SCENES_FILE) as f:
        return json.load(f)


def save_scenes(spots):
    with open(SCENES_FILE, "w") as f:
        json.dump(spots, f, indent=4)


def load_doors():
    """{floor name: [[left, top, right, bottom], ...]} of the doors that never open - empty when none yet."""
    if not os.path.exists(DOORS_FILE):
        return {}
    with open(DOORS_FILE) as f:
        return json.load(f)


def save_doors(doors):
    with open(DOORS_FILE, "w") as f:
        json.dump(doors, f, indent=4)
