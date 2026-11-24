# https://github.com/Cl1ngz/HotlineMiamibot
# bot/decide.py - decide(): what we want this frame, a Plan. Looks only at Eyes (and Hands) - never at the game
import math

from core.path import cell_of, walk_steps
from core.walls import can_see
from core.weapons import choose_weapon, held_rank

from . import game
from .boxes import Plan
from .config import EMPTY_HANDS, GRAB_REACH, REACH

EXECUTE_WALK = 16  # walk this close to a lying enemy - inside act.py's EXECUTE_REACH (30), not at its edge
ENEMY_SPEED = 180  # how fast an enemy runs
BACK_STEP = 24  # back off this far at a time - less than walk.py's STRAIGHT, so the legs go straight there
# an enemy running at you faster than this, this close: he's CHARGING - meet him standing
# (running into him doubles the speed you meet at, and in the logs he always hit first)
CHARGE_SPEED = 60
MEET_FAR = 150
BACK_ROOM = (
    48  # backing off: only where there's this much free room (never back into a wall)
)
# walk this close to what the red arrow points at / to a spot shown with tools/scene_tool.py (then tap LMB)
ARROW_WALK = 8
SPOT_WALK = 8
# a better weapon this many steps (16 each) of WALKING away, nobody in sight: swap - a chance on the way, not a trip
SWAP_STEPS = 10


# ↖  ↑ ↗
# ← you →  8 directions, steps 24
# ↙  ↓  ↘
def back_off_point(you, threats, blocked, lines):
    """Where to step back while the weapon gets ready, or None (a wall or a corner behind you).
    Of 8 directions with BACK_ROOM free: the one that leaves you furthest from the closest enemy."""
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
            continue  # a wall there
        far = min(
            math.dist(step, xy) for xy in threats
        )  # the closest enemy after the step
        if far > best_far:
            best, best_far = step, far
    # None = every free step takes you closer to someone: cornered
    return best


def decide(eyes, hands, now):
    """What we want this frame -> a Plan. Looks at eyes (and hands: when the weapon is ready), never at the game.
    The first that fits wins: a weapon (empty hands) or the level goal (floor clear), the enemy you see,
    an enemy behind a wall, the red arrow, the car, the stairs, a shown spot."""
    you = eyes.you
    target_xy = eyes.spots.get(eyes.target)
    enemy_far = math.dist(target_xy, you) if target_xy is not None else math.inf
    time_left = hands.ready_at - now if hands.ready_at > now else 0

    grab = None
    held = 0 if eyes.hand in EMPTY_HANDS else held_rank(eyes.hand, game.names)
    if held == 0:
        # empty hands: any weapon closer than the enemy
        grab = choose_weapon(
            [(x, y) for x, y, rank in eyes.weapons], you, enemy_far, eyes.lines
        )
    elif held is not None and target_xy is None:
        # a weapon in hand, nobody in sight: a better one a few steps of WALKING away. Not "in sight":
        # by a wall in-sight flips on and off as you walk, and the bot turned back and forth
        for x, y, rank in sorted(eyes.weapons, key=lambda w: math.dist(w[:2], you)):
            if (
                rank > held
                and walk_steps(you, (x, y), eyes.blocked, SWAP_STEPS) is not None
            ):
                grab = (x, y)
                break
    if grab is None and eyes.goals and not eyes.still:
        # floor clear: take the level's goal wherever it lies (the right button swaps it for the weapon)
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
            # a closed door between you: a swing only hits the door - walk INTO it, it swings open
            # and knocks him down if he stands right behind it
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
            # no room behind you: stand, the swing comes the moment the weapon is ready
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
