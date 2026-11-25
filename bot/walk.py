# https://github.com/Cl1ngz/HotlineMiamibot
# bot/walk.py - the legs: walk to plan.goal along a path, learn what we bump into, find the fake doors
import math

from core.legs import hold, keys_toward, next_point
from core.path import blocked_cells, cell_of, find_path
from core.scenes import save_doors
from core.walls import can_see, door_at

from . import game
from .config import MOVED_A_BIT

STAIRS_SIZE = (
    16  # walk around lit stairs that aren't the goal (stepping on them = another floor)
)
REPLAN = 0.5  # seconds between two searches for the way
# the goal this close and you can see it: straight there, no path (the path ends in the MIDDLE of a 16x16
# cell - up to 11 from the weapon, too far to pick it up)
STRAIGHT = 32
# holding the keys along the path but not moving this long: a bump into something the walls don't know
# (a bin, a car) - that cell is blocked for FORGET_AFTER (a dialogue stops you too, so not for ever)
BUMP_AFTER = 0.4
FORGET_AFTER = 8
# the same cell bumped again on this floor (after it was forgotten, after a death): something solid the walls
# don't know (a railing, a counter) - blocked this long, so the bot doesn't learn it again on every try
SOLID_FOR = 120
# just arrived (a new floor, a restart): the game holds you still ~2 s, pushing then is no bump -
# bumps count again once you've moved from the arrival spot, or after SETTLE
SETTLE = 3
# a door pushed this many times on a floor that never opened = a fake one, a wall for good (doors.json)
# (not after one push: a dialogue stops you at a real door too); two bumps closer than DOOR_AGAIN = one try
DOOR_TRIES = 2
DOOR_AGAIN = 4


def fake_door(eyes, legs, door):
    """We pushed this door DOOR_TRIES times and it never opened: a wall for good - now, and on every next visit."""
    legs.learned.update({cell: math.inf for cell in blocked_cells([door])})
    saved = game.fake_doors.setdefault(eyes.scene, [])
    if list(door) not in saved:
        saved.append(list(door))
        save_doors(game.fake_doors)
    print(
        f"\nFAKE DOOR at {door} - it never opens, remembered for this floor ({eyes.scene})"
    )


def walk(plan, eyes, legs, now):
    """The legs: walk to plan.goal - straight when it's close and you can see it, else along the path."""
    you, goal = eyes.you, plan.goal
    if legs.scene != eyes.scene:
        # another floor: the last one's bumps aren't here (the door tries stay - they're kept per floor)
        legs.learned.clear()
        legs.scene = eyes.scene
    if legs.arrived_at != eyes.arrived_at:
        # just arrived: remember where - until you move from here the game may be holding you still
        legs.arrived_at, legs.arrived_from = eyes.arrived_at, you
    settled = (
        math.dist(you, legs.arrived_from) > MOVED_A_BIT
        or now - legs.arrived_at > SETTLE
    )
    keys = set()
    point = None  # the path point we push toward this frame (None = not walking along a path)
    if goal is not None and math.dist(goal, you) > plan.close_enough:
        if math.dist(goal, you) < STRAIGHT and can_see(you, goal, eyes.lines):
            keys = keys_toward(you, goal)  # the last bit: straight there, no path
        else:
            if now >= legs.next_plan or legs.planned_at < eyes.arrived_at:
                # forget the old bumps, walk around the rest
                legs.learned = {
                    cell: until for cell, until in legs.learned.items() if until > now
                }
                avoid = eyes.blocked
                # lit stairs that aren't the goal: walk around them
                if eyes.stairs is not None and goal != eyes.stairs:
                    x, y = eyes.stairs
                    box = (
                        x - STAIRS_SIZE,
                        y - STAIRS_SIZE,
                        x + STAIRS_SIZE,
                        y + STAIRS_SIZE,
                    )
                    avoid = avoid | blocked_cells([box])
                legs.path = find_path(you, goal, avoid | set(legs.learned))
                # the bumps (not the fake doors - they stay for ever, until = inf)
                bumps = {
                    cell for cell, until in legs.learned.items() if until != math.inf
                }
                if bumps and cell_of(legs.path[-1]) != cell_of(goal):
                    # the goal can't be reached - because of the bumps? A bump may make you walk AROUND
                    # something, never cut the goal off (a frozen game looks like a bump too): forget them
                    free = find_path(you, goal, avoid | (set(legs.learned) - bumps))
                    if cell_of(free[-1]) == cell_of(goal):
                        legs.path = free
                        legs.learned = {
                            cell: until
                            for cell, until in legs.learned.items()
                            if cell not in bumps
                        }
                        print(
                            "\nthe bumps cut the goal off - forgot them, taking the way through"
                        )
                legs.next_plan = now + REPLAN
                legs.planned_at = now
            if legs.path is not None:
                point = next_point(legs.path, you)
                if point is None:
                    # the end of the path (the cell closest to the goal): the last bit straight at the goal
                    point = goal
                keys = keys_toward(you, point)
            else:
                keys = keys_toward(you, goal)
    # bumped into something? walking along the path, but you haven't moved for BUMP_AFTER
    if point is None or point == goal or math.dist(you, legs.pushed_from) > MOVED_A_BIT:
        legs.pushed_from, legs.pushed_since = (
            you,
            now,
        )  # not pushing, or moving fine: count again
    elif now - legs.pushed_since > BUMP_AFTER and settled:
        # that cell is blocked for a while - for long if we bumped into it before on this floor
        spot = (eyes.scene, cell_of(point))
        legs.bumps[spot] = legs.bumps.get(spot, 0) + 1
        legs.learned[cell_of(point)] = now + (
            FORGET_AFTER if legs.bumps[spot] == 1 else SOLID_FOR
        )
        door = door_at(you, eyes.doors)
        if door is not None:
            tried = (
                eyes.scene,
                door,
            )  # this door on THIS floor (the same spot on another floor = another door)
            if now - legs.door_tried_at.get(tried, -math.inf) > DOOR_AGAIN:
                # a new try at a door that didn't open: count it - the DOOR_TRIES-th makes it a fake
                legs.door_tried_at[tried] = now
                legs.door_tries[tried] = legs.door_tries.get(tried, 0) + 1
                if legs.door_tries[tried] >= DOOR_TRIES:
                    fake_door(eyes, legs, door)
        # a new way right now, around it
        legs.next_plan = now
        legs.pushed_from, legs.pushed_since = you, now
        print(f"\nBUMPED into something at {point} - going around it")
    legs.held = hold(game.mem, game.mem_rw, keys, legs.held)
