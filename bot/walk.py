# https://github.com/Cl1ngz/HotlineMiamibot
# bot/walk.py - the legs: walk to plan.goal along a path, learn what we bump into, find the fake doors
import math

from core.legs import hold, keys_toward, next_point
from core.path import blocked_cells, cell_of, find_path
from core.scenes import save_doors
from core.walls import can_see, door_at

from . import game
from .config import MOVED_A_BIT

# the legs keep away from lit stairs that aren't the goal (stepping on them = another floor)
STAIRS_SIZE = 16
# seconds between two searches for the way
REPLAN = 0.5
# the goal is this close and you can see it -> walk straight there, no path (the path ends in the
# MIDDLE of a 16x16 cell - up to 11 away from the weapon, too far to pick it up)
STRAIGHT = 32
# holding the keys along the path but not moving for this long: we bumped into something the walls don't know
# (a bin, a car...) - remember that cell as blocked and find a new way (before STUCK_TAP_AFTER swings at it)
BUMP_AFTER = 0.4
# and forget it after this long (a dialogue also stops you - it shouldn't block a cell for ever)
FORGET_AFTER = 8
# just arrived (a restart after a death, a new floor): the game holds you still for ~2 s, and pushing then
# is no bump. Bumps count again once you've moved from the arrival spot, or after SETTLE (you really stand at something)
SETTLE = 3
# pushed a door this many times on a floor and it never opened: a fake one - a wall there, for good (doors.json).
# Not after one push: a dialogue freezes the game and stops you at a real door too
DOOR_TRIES = 2
# two bumps at the same door closer than this are ONE try (one push, or one dialogue that froze the game)
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
        # another floor: what we bumped into on the last one isn't here (the floors lie one above the other)
        # (the door tries stay: they're counted per floor, so a retry after a death still counts)
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
                # forget the old bumps, walk around the rest - the walls don't know those things
                legs.learned = {
                    cell: until for cell, until in legs.learned.items() if until > now
                }
                avoid = eyes.blocked
                # lit stairs that aren't the goal: stepping on them takes you to another floor - walk around them
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
                    # the goal can't be reached. Because of the bumps? A bump may make you walk AROUND
                    # something, but never cut the goal off: a frozen game (the start of a level, a dialogue)
                    # looks like a bump too. Without the bumps there's a way: forget them and take it
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
                    # (the dumpster: the path ends ~26 away, LMB needs 24)
                    point = goal
                keys = keys_toward(you, point)
            else:
                # find_path always gives a way now - this is just in case
                keys = keys_toward(you, goal)
    # bumped into something? walking along the path, but you haven't moved for BUMP_AFTER
    # (pushing at the goal itself - the dumpster - is as close as it gets: nothing to learn there)
    if point is None or point == goal or math.dist(you, legs.pushed_from) > MOVED_A_BIT:
        legs.pushed_from, legs.pushed_since = (
            you,
            now,
        )  # not pushing, or moving fine: start counting again
    elif now - legs.pushed_since > BUMP_AFTER and settled:
        # that cell is blocked for a while
        legs.learned[cell_of(point)] = now + FORGET_AFTER
        door = door_at(you, eyes.doors)
        if door is not None:
            tried = (
                eyes.scene,
                door,
            )  # this door on THIS floor - the same spot on another floor is another door
            if now - legs.door_tried_at.get(tried, -math.inf) > DOOR_AGAIN:
                # a NEW try at a door that didn't open (not the same push again): count it - the DOOR_TRIES-th is a fake
                legs.door_tried_at[tried] = now
                legs.door_tries[tried] = legs.door_tries.get(tried, 0) + 1
                if legs.door_tries[tried] >= DOOR_TRIES:
                    fake_door(eyes, legs, door)
        legs.next_plan = now  # a new way right now, around it
        legs.pushed_from, legs.pushed_since = you, now
        print(f"\nBUMPED into something at {point} - going around it")
    legs.held = hold(game.mem, game.mem_rw, keys, legs.held)
