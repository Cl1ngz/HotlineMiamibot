# https://github.com/Cl1ngz/HotlineMiamibot
# bot/share.py - what the bot is doing: the status line, and a small file for tools/radar.py
import json
import os
import time

# what the bot is doing, for tools/radar.py (the same name is in tools/radar.py) - rewritten this often
NOW_FILE = "/tmp/hmbot_now.json"
SHARE_EVERY = 0.1


def status(text):
    """One line at the bottom of the terminal that keeps being overwritten."""
    print(f"{text:60}", end="\r", flush=True)


def share(plan, eyes, legs):
    """Tell tools/radar.py what the bot is doing: a small file, written whole (the radar never reads half of it)."""
    data = {
        "time": time.time(),
        "text": plan.text,
        "goal": plan.goal,
        "path": legs.path,
        "arrow": eyes.arrow,
        "came_by": eyes.came_by,
        "target": eyes.spots.get(eyes.target),
        # the danger map: the cells a gunman sees (16 x 16, core/path.py)
        "fire": list(eyes.fire),
    }
    with open(NOW_FILE + ".tmp", "w") as f:
        json.dump(data, f)
    os.replace(
        NOW_FILE + ".tmp", NOW_FILE
    )  # the swap is instant: the radar sees the old file or the new one
