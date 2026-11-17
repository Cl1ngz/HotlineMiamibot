# https://github.com/Cl1ngz/HotlineMiamibot
# bot/game.py - the things set ONCE at the start and used by every part of the bot
#
# Use them as game.mem, game.rules... - NOT "from bot.game import mem": that copies the value it has at the
# moment of the import (None), and never sees the real one load() puts here later.
import time

from core.arrow import ArrowWatch
from core.enemies import find_aim, find_me_card, load_rules
from core.hands import find_button, find_look
from core.memory import attach, open_rw
from core.scenes import load_doors, load_scenes
from core.weapons import load_names

# at the start wait this long for the crosshair (find_look picks the look chain by it)
LOOK_WAIT = 3

mem = None  # the game's memory (read)
mem_rw = None  # the game's memory (write)
rules = None  # the enemy rules (addresses.json)
# weapon frame -> {"name": ..., "kind": ...}
names = None
# floor name -> [x, y] of the spot to walk to (tools/scene_tool.py)
scenes = None
# floor name -> boxes of the doors that never open there (walk() learns them by pushing)
fake_doors = None
# the red arrow: a little search every frame (core/arrow.py)
watch = None


def load():
    """Attach to the game and read the files - once, at the start."""
    global mem, mem_rw, rules, names, scenes, fake_doors, watch
    mem, regions, _static_regions = attach()
    mem_rw = open_rw()
    rules = load_rules()
    names = load_names()
    scenes = load_scenes()
    fake_doors = load_doors()
    watch = ArrowWatch(mem, regions)
    if not rules:
        raise SystemExit(
            "no enemy rules yet - add one: python -m tools.enemy_tool look, then save N"
        )


def get_ready():
    """Wait for your character, find this launch's chains, list the arrow's memory blocks."""
    wait_for_game(mem)
    pick_look()
    pick_button()
    watch.search_all()
    print(f"the arrow lists: {len(watch.blocks)} memory block(s)")


def wait_for_game(mem):
    """Wait until your character is there: a level, the apartment, the shop... (not every scene has a crosshair)"""
    while find_me_card(mem) is None:
        print("waiting for your character...", end="\r", flush=True)
        time.sleep(0.2)
    print()


def pick_look():
    """Find the look chain for this launch (core/hands.py find_look) - by the crosshair, so wait for it a moment."""
    find_aim(mem)  # warm-up: find_aim has to see the crosshair once
    give_up = time.monotonic() + LOOK_WAIT
    while time.monotonic() < give_up:
        aim = find_aim(mem)
        if aim is not None:
            chain = find_look(mem, aim)
            if chain is None:
                raise SystemExit(
                    "no look chain fits this launch - run python -m helpers_for_me.look_find"
                )
            print("look: [GAME]" + "".join(f" -> +{offset:#x}" for offset in chain))
            return
        print("waiting for the crosshair...", end="\r", flush=True)
        time.sleep(0.2)
    # no crosshair in this scene: the first chain that can be read at all (a guess - checked again if a write fails)
    chain = find_look(mem, None)
    print(f"look: a guess, no crosshair - {chain}")


def pick_button():
    """Find the mouse button chain for this launch (core/hands.py find_button)."""
    chain, sure = find_button(mem)
    if chain is None:
        raise SystemExit(
            "no button chain can be read in this launch - run python -m helpers_for_me.button_find"
        )
    note = "" if sure else "  (a guess - no mouse GUID found inside)"
    print("button: [GAME]" + "".join(f" -> +{offset:#x}" for offset in chain) + note)
