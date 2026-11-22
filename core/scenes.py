# https://github.com/Cl1ngz/HotlineMiamibot
# core/scenes.py - a name for every floor from its walls, and what the bot remembers per floor
# scene_id(walls) -> "3fa9c1d2", scenes.json: a spot to walk to (scene_tool), doors.json: fake doors (walk)
import hashlib
import json
import os

SCENES_FILE = "scenes.json"  # floor name -> [x, y]: walk there when there's nothing else to do (the masks' room)
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
