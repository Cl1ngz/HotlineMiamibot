# https://github.com/Cl1ngz/HotlineMiamibot
# bot/walk.py - the legs: walk to plan.goal along a path, learn what we bump into, find the fake doors
import math

from core.legs import hold, keys_toward, next_point
from core.path import CELL, blocked_cells, cell_of, find_path
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
# going straight at a close goal and not moving for BUMP_AFTER: something the walls don't know is in the way
# (the logs: 2 s holding A at (200, 229), then dead) - learn its cell like a bump, take the path this long
STRAIGHT_OFF = 1.0
# the way doesn't get to the goal (it's behind glass, a door that never opens): decide() leaves it this long
NO_WAY_FOR = 5
# this long closer than STRAIGHT to a weapon and it's still not yours: it lies where you can't get (a counter,
# a wall's edge - the logs: 20 s pushing D at an M16 15 away, 8 bumps round a gun by a wall) - leave it
GRAB_TRY = 2.0
# a cell a gunman sees (eyes.fire) costs like this many free ones - the way goes round his sight if that's
# not much longer, and comes into it as late as it can. With a loaded gun only the cells two of them see
# (eyes.crossfire): you shoot one first (~0.1 s, he needs ~0.3), not two - a shotgun pumps 0.4 s
FIRE_COST = 6


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
    straight = False  # going straight at the goal this frame (no path)
    if goal is not None and math.dist(goal, you) > plan.close_enough:
        if (
            math.dist(goal, you) < STRAIGHT
            and can_see(you, goal, eyes.lines)
            and now >= legs.straight_off
        ):
            keys = keys_toward(you, goal)  # the last bit: straight there, no path
            straight = True
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
                fire = eyes.crossfire if eyes.gun and eyes.ammo != 0 else eyes.fire
                legs.path = find_path(
                    you,
                    goal,
                    avoid | set(legs.learned),
                    costly=fire,
                    extra=FIRE_COST,
                    area=eyes.area,
                )
                # the bumps (not the fake doors - they stay for ever, until = inf)
                bumps = {
                    cell for cell, until in legs.learned.items() if until != math.inf
                }
                if bumps and cell_of(legs.path[-1]) != cell_of(goal):
                    # the goal can't be reached - because of the bumps? A bump may make you walk AROUND
                    # something, never cut the goal off (a frozen game looks like a bump too): forget them
                    free = find_path(
                        you,
                        goal,
                        avoid | (set(legs.learned) - bumps),
                        costly=fire,
                        extra=FIRE_COST,
                        area=eyes.area,
                    )
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
                # no way to the goal (the way ends at the cell closest to it): tell decide() to leave it a while
                legs.reaches = cell_of(legs.path[-1]) == cell_of(goal)
                if not legs.reaches:
                    eyes.no_way[cell_of(goal)] = now + NO_WAY_FOR
                legs.next_plan = now + REPLAN
                legs.planned_at = now
            if legs.path is not None:
                point = next_point(legs.path, you)
                if point is None and legs.reaches:
                    # the end of the path (the goal's cell): the last bit straight at the goal
                    point = goal
                # (the end of a way that doesn't get there: stand - pushing on goes into the glass for ever)
                keys = keys_toward(you, point) if point is not None else set()
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
    # going straight at the goal and not moving: the same, for the cell one step toward it
    if not straight or math.dist(you, legs.straight_from) > MOVED_A_BIT:
        legs.straight_from, legs.straight_since = you, now
    elif now - legs.straight_since > BUMP_AFTER and settled:
        far = math.dist(goal, you)
        step = (
            you[0] + (goal[0] - you[0]) / far * CELL,
            you[1] + (goal[1] - you[1]) / far * CELL,
        )
        legs.learned[cell_of(step)] = now + FORGET_AFTER
        legs.straight_off = now + STRAIGHT_OFF
        legs.next_plan = now
        legs.straight_from, legs.straight_since = you, now
        print(f"\nBUMPED going straight at {goal} - taking the way round")
    # by a weapon for GRAB_TRY and it's still lying there (pushing at it, bumping round it, pressing too far)
    if (
        plan.grab is None
        or plan.grab != legs.grab_at
        or math.dist(plan.grab, you) > STRAIGHT
    ):
        legs.grab_at, legs.grab_since = plan.grab, now
    elif now - legs.grab_since > GRAB_TRY:
        eyes.out_of_reach.append(plan.grab)
        legs.grab_at, legs.grab_since = None, now
        print(f"\nCAN'T GET the weapon at {plan.grab} - leaving it")
    legs.held = hold(game.mem, game.mem_rw, keys, legs.held)
