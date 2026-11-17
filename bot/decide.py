# https://github.com/Cl1ngz/HotlineMiamibot
# bot/decide.py - decide(): what we want this frame, a Plan. Looks only at Eyes (and Hands) - never at the game
import math

from core.path import cell_of
from core.walls import can_see
from core.weapons import choose_weapon

from . import game
from .boxes import Plan
from .config import EMPTY_HANDS, GRAB_REACH, REACH

# so walk up this close to a lying enemy - closer than EXECUTE_REACH, or you stop right at the edge
EXECUTE_WALK = 16
# how fast an enemy runs
ENEMY_SPEED = 180
# back off this far at a time - less than STRAIGHT, so the legs walk straight there
BACK_STEP = 24
# an enemy running at you faster than this (his own steps, px/s) is CHARGING: don't run into him - meet him
# standing (he runs ~180; running into him doubles the speed you meet at, and in the logs he always hit first)
CHARGE_SPEED = 60
# ...when he's this close (further away: walk on, he may still turn)
MEET_FAR = 150
# backing off: a step only where there's this much free room (no wall, no sofa) - never back into a wall
BACK_ROOM = 48
# the red arrow: walk this close to what it points at...
ARROW_WALK = 8
# a spot shown with tools/scene_tool.py: walk this close to it (then stand there and tap LMB - the talk goes on)
SPOT_WALK = 8


def back_off_point(you, threats, blocked, lines):
    """Where to step back to while the weapon gets ready - or None: no room (a wall or a corner behind you).
    Of 8 directions, the one with BACK_ROOM free room that leaves you furthest from the closest enemy:
    straight back when there's room, along the wall when there isn't."""
    closest_now = min(math.dist(you, xy) for xy in threats)
    best, best_far = None, closest_now
    for i in range(8):
        dx, dy = math.cos(i * math.pi / 4), math.sin(i * math.pi / 4)
        step = (you[0] + dx * BACK_STEP, you[1] + dy * BACK_STEP)
        room = (you[0] + dx * BACK_ROOM, you[1] + dy * BACK_ROOM)
        if (
            cell_of(step) in blocked
            or cell_of(room) in blocked
            or not can_see(you, room, lines)
        ):
            # a wall there - no room to step back
            continue
        far = min(
            math.dist(step, xy) for xy in threats
        )  # the closest enemy after the step
        if far > best_far:
            best, best_far = step, far
    # None = every free step takes you closer to someone: cornered
    return best


def decide(eyes, hands, now):
    """What we want this frame -> a Plan. Only looks at eyes (and in hands, when the weapon is ready),
    never at the game.
    First come first served: a weapon (empty hands) or the level goal (floor clear),
    then the enemy you see, then an enemy behind a wall, then the car, then the stairs.
    """
    you = eyes.you
    target_xy = eyes.spots.get(eyes.target)
    enemy_far = math.dist(target_xy, you) if target_xy is not None else math.inf
    time_left = hands.ready_at - now if hands.ready_at > now else 0

    grab = None
    if eyes.hand in EMPTY_HANDS:
        grab = choose_weapon(eyes.weapons, you, enemy_far, eyes.lines)
    if grab is None and eyes.goals and not eyes.still:
        # the floor is clear: take the level's goal, wherever it lies - the right button swaps it for the weapon
        grab = min(eyes.goals, key=lambda xy: math.dist(xy, you))
    if grab is not None:
        return Plan(
            grab=grab,
            goal=grab,
            close_enough=GRAB_REACH,
            text=f"GRABBING {math.dist(grab, you):3.0f} away",
        )

    if target_xy is not None:
        if eyes.behind_door and not eyes.lying:
            # a closed door between you: a swing only hits the door (then the weapon isn't ready, you back off,
            # come back, hit the door again...) - walk INTO the door: it swings open, and knocks him down
            # if he stands right behind it
            return Plan(
                goal=target_xy,
                close_enough=0,
                text=f"THROUGH THE DOOR to an enemy {enemy_far:3.0f} away",
            )
        # back off: he stands, the weapon isn't ready yet, and he'll be in reach before it is
        if (
            not eyes.lying
            and time_left > 0
            and enemy_far < REACH + ENEMY_SPEED * time_left
        ):
            threats = list(eyes.threats.values()) or [target_xy]
            back = back_off_point(you, threats, eyes.blocked, eyes.lines)
            if back is not None:
                return Plan(
                    goal=back,
                    close_enough=0,
                    text=f"BACKING OFF {enemy_far:3.0f} away, ready in {time_left:.2f} s",
                )
            # no room behind you: running into the wall is the end - stand, the swing comes the moment it's ready
            return Plan(
                text=f"CORNERED {enemy_far:3.0f} away, ready in {time_left:.2f} s - standing"
            )
        if not eyes.lying and eyes.closing > CHARGE_SPEED and enemy_far < MEET_FAR:
            # he runs at you: stand and let him come into your swing (act() presses early enough)
            return Plan(
                text=f"MEETING a charging enemy {enemy_far:3.0f} away, {eyes.closing:3.0f}/s"
            )
        return Plan(
            goal=target_xy,
            close_enough=EXECUTE_WALK if eyes.lying else REACH,
            text=f"LOCKED on {'LYING' if eyes.lying else 'standing'} enemy "
            f"{enemy_far:3.0f} away ({len(eyes.spots)} in sight)",
        )

    if eyes.hidden:
        goal = min(eyes.hidden.values(), key=lambda xy: math.dist(xy, you))
        return Plan(
            goal=goal,
            text=f"HUNTING an enemy behind a wall {math.dist(goal, you):3.0f} away",
        )
    if eyes.arrow is not None:
        return Plan(
            goal=eyes.arrow,
            close_enough=ARROW_WALK,
            use=True,
            text=f"TO THE ARROW {math.dist(eyes.arrow, you):3.0f} away",
        )
    if eyes.car is not None:
        # the chapter is done: drive away (beats any stairs - some stay lit)
        return Plan(
            goal=eyes.car,
            close_enough=0,
            text=f"TO THE CAR {math.dist(eyes.car, you):3.0f} away",
        )
    # floor clear: go to GO! - but never to the stairs you came by, they lead back
    if eyes.stairs is not None and eyes.stairs != eyes.came_by:
        return Plan(
            goal=eyes.stairs,
            close_enough=0,
            text=f"TO THE STAIRS {math.dist(eyes.stairs, you):3.0f} away",
        )
    # a floor we were shown a spot on (tools/scene_tool.py), and nothing else to do: walk there
    spot = game.scenes.get(eyes.scene)
    if spot is not None:
        return Plan(
            goal=tuple(spot),
            close_enough=SPOT_WALK,
            text=f"TO THE SHOWN SPOT {math.dist(spot, you):3.0f} away",
        )
    return Plan(text="no enemy in sight")
