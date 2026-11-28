# https://github.com/Cl1ngz/HotlineMiamibot
# bot/decide.py - decide(): what we want this frame, a Plan. Looks only at Eyes (and Hands) - never at the game
import math

from core.danger import corner, cover
from core.path import cell_of, walk_steps
from core.walls import can_see
from core.weapons import choose_weapon, held_rank

from . import game
from .boxes import Plan
from .config import EMPTY_HANDS, GRAB_REACH, GUN_RANGE, GUN_RANK, REACH, THROW_RANGE

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
# an arrow still there after this many taps at what it points at (act.py: LMB, then RMB) isn't ours to use -
# leave it on this floor (the logs: an arrow at (261, 150) on two floors, the bot went back and forth)
ARROW_TRIES = 8
SAME_ARROW = 24  # an arrow this close to a left one points at the same thing
# a better weapon this many steps (16 each) of WALKING away, nobody in sight: swap - a chance on the way, not a trip
SWAP_STEPS = 10
# someone in sight: a gun this much closer than him (0.5 = half his distance) is still worth grabbing first
GUN_BEFORE = 0.5
# this much ammo or less: a gun lying around (full) beats yours - swap when nobody's in sight
LOW_AMMO = 1
# with a gun: walk up to this far from the enemy, then stand and shoot (a bit inside act.py's GUN_RANGE)
SHOOT_FROM = 0.8 * GUN_RANGE
MISSES = 2
# no loaded gun and a gunman sees you: closer than this run at him (the logs: he shoots ~0.3 s after he sees
# you, you run ~180/s), further - throw what you hold at him (it knocks him down), or hide
CLOSE_IN = 80
# a gunman behind a wall: wait round the corner of his room this long for him to come, then go in anyway
# (some never move). A sitter never comes - no waiting for him
AMBUSH_WAIT = 3.0
CORNER_NEAR = 12  # this close to the corner = you're there
# no loaded gun and a gunman sees you: out of his sight first (the logs, level 4: 13 deaths fighting a knife guy
# in the middle of the room while a Double Barrel 60-110 away watched) - unless one without a gun is this close
# (he hits you while you walk away). In cover stand this long: the ones without a gun come to you there
FIGHT_NEAR = 50
HOLD_COVER = 1.5

# the gunman we wait for by his corner, and since when we stand there (inf = not there yet) - kept between
# frames, like lockon.target
waiting_for = None
waiting_since = math.inf
hold_until = 0.0  # in cover until then (HOLD_COVER after the last HIDING)
left_arrows = []  # (floor, xy) of the arrows we tapped ARROW_TRIES times for nothing


# ↖  ↑ ↗
# ← you →  8 directions, steps 24
# ↙  ↓  ↘
def back_off_point(you, threats, blocked, lines):
    """Where to step back while the weapon gets ready, or None (a wall or a corner behind you).
    Of 8 directions with BACK_ROOM free: the one that leaves you furthest from the closest enemy.
    """
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


def can_reach(eyes, xy, now):
    """Did walk() find a way there lately (or never try)? Not: behind glass, a door that never opens."""
    return eyes.no_way.get(cell_of(xy), 0) < now


def waited(card, there, now):
    """Have we waited AMBUSH_WAIT by this gunman's corner? there = we stand at it now (the clock starts)."""
    global waiting_for, waiting_since
    if waiting_for != card:
        waiting_for, waiting_since = card, math.inf
    if there:
        waiting_since = min(waiting_since, now)
    return now - waiting_since > AMBUSH_WAIT


def decide(eyes, hands, now):
    """What we want this frame -> a Plan. Looks at eyes (and hands: when the weapon is ready), never at the game.
    The first that fits wins: a weapon (empty hands) or the level goal (floor clear), the enemy you see,
    an enemy behind a wall, the red arrow, the car, the stairs, a shown spot."""
    global hold_until
    you = eyes.you
    # a loaded gun (ammo None = can't read it now: loaded)
    armed = eyes.gun and eyes.ammo != 0
    target_xy = eyes.spots.get(eyes.target)
    if target_xy is not None and not armed and not can_reach(eyes, target_xy, now):
        target_xy = None  # behind glass, no way round: a gun shoots through it, a bat doesn't - someone else
    weapons = [w for w in eyes.weapons if can_reach(eyes, w[:2], now)]
    enemy_far = math.dist(target_xy, you) if target_xy is not None else math.inf
    time_left = hands.ready_at - now if hands.ready_at > now else 0

    grab = None
    if eyes.gun:
        # ammo None = can't read it now: keep the gun. Almost empty: any gun lying around is better
        if eyes.ammo == 0:
            held = 0
        elif eyes.ammo is not None and eyes.ammo <= LOW_AMMO:
            held = GUN_RANK - 1
        else:
            held = GUN_RANK
    else:
        held = 0 if eyes.hand in EMPTY_HANDS else held_rank(eyes.hand, game.names)
    if held == 0:
        # empty hands: any weapon closer than the enemy
        grab = choose_weapon(
            [(x, y) for x, y, rank in weapons], you, enemy_far, eyes.lines
        )
    elif held is not None:
        # a weapon in hand: a better one a few steps of WALKING away (not "in sight": by a wall in-sight flips
        # on and off as you walk, and the bot turned back and forth). Someone in sight: only a gun, and only
        # if it's much closer than him - grab it, then shoot him
        for x, y, rank in sorted(weapons, key=lambda w: math.dist(w[:2], you)):
            if (
                rank > held
                and (
                    target_xy is None
                    or (
                        rank >= GUN_RANK
                        and math.dist((x, y), you) < enemy_far * GUN_BEFORE
                    )
                )
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

    # who sees you: the gunmen and the sitters whose sight has your cell (glass hides you - they don't shoot
    # through it). No loaded gun: he shoots before you get to him
    seen_by = [
        card for card, (his, cells) in eyes.sight.items() if cell_of(you) in cells
    ]
    gunmen = [card for card in seen_by if card in eyes.shooters]
    target_sees = eyes.target in seen_by
    if not armed and seen_by:
        if target_sees and not eyes.lying and CLOSE_IN < enemy_far < THROW_RANGE:
            if not eyes.gun and held:
                # throw what you hold at him: it knocks him down
                return Plan(
                    goal=target_xy,
                    close_enough=THROW_RANGE,
                    throw=True,
                    text=f"THROWING at a gunman {enemy_far:3.0f} away",
                )
        # out of their sight: the ones without a gun follow you there, fight them where nobody shoots you.
        # Not when: one without a gun is about to hit you, the gunman is close (run at him, below), it's the
        # gunman we waited for (we go in at him now), only a sitter sees you (he never comes - you go to him)
        melee_close = (
            target_xy is not None and not target_sees and enemy_far < FIGHT_NEAR
        )
        gunman_close = target_sees and enemy_far <= CLOSE_IN
        went_in = waiting_for in gunmen and now - waiting_since > AMBUSH_WAIT
        if gunmen and not (melee_close or gunman_close or went_in):
            spot = cover(you, eyes.fire, eyes.blocked)
            if spot is not None:
                hold_until = now + HOLD_COVER
                return Plan(
                    goal=spot,
                    close_enough=0,
                    text=f"HIDING from {len(gunmen)} gunman(s)",
                )
    if (
        not armed
        and now < hold_until
        and not (target_xy is not None and enemy_far < FIGHT_NEAR)
    ):
        # in cover: let them come here (act() still swings at anyone in reach)
        return Plan(text=f"HOLDING cover, {hold_until - now:.1f} s")

    if target_xy is not None:
        if eyes.behind_door and not eyes.lying:
            # a closed door between you: a swing only hits the door - walk INTO it, it swings open
            # and knocks him down if he stands right behind it
            return Plan(
                goal=target_xy,
                close_enough=0,
                text=f"THROUGH THE DOOR to an enemy {enemy_far:3.0f} away",
            )
        if eyes.gun and eyes.ammo == 0 and not eyes.lying:
            # an empty gun only clicks: throw it at him (it knocks him down), then it's fists
            return Plan(
                goal=target_xy,
                close_enough=THROW_RANGE,
                throw=True,
                text=f"THROWING the empty gun at an enemy {enemy_far:3.0f} away",
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
        if eyes.gun and eyes.ammo != 0 and not eyes.lying:
            # a gun: no need to walk up to him - get within SHOOT_FROM and stand, act() fires.
            # A lying one can't be shot (bullets fly over him) - he gets executed like with fists.
            # Still up after MISSES shots: something's in the way (an open door) - walk up, act() fires on the way
            missed = hands.shot_at == eyes.target and hands.shots >= MISSES
            return Plan(
                goal=target_xy,
                close_enough=REACH if missed else SHOOT_FROM,
                text=f"SHOOTING at an enemy {enemy_far:3.0f} away, ammo {eyes.ammo}"
                + (", missed - closer" if missed else ""),
            )
        return Plan(
            goal=target_xy,
            close_enough=EXECUTE_WALK if eyes.lying else REACH,
            text=f"LOCKED on {'LYING' if eyes.lying else 'standing'} enemy "
            f"{enemy_far:3.0f} away ({len(eyes.spots)} in sight)",
        )

    if eyes.hidden:
        # no loaded gun: the ones without a gun first - a gunman shoots you before you get to him
        calm = {
            card: xy
            for card, xy in eyes.hidden.items()
            if card not in eyes.shooters and card not in eyes.sitters
        }
        pool = calm if calm and not armed else eyes.hidden
        # not the ones walk() found no way to (behind glass...) - unless there's nobody else
        pool = {
            card: xy for card, xy in pool.items() if can_reach(eyes, xy, now)
        } or pool
        card = min(pool, key=lambda card: math.dist(pool[card], you))
        goal = pool[card]
        if not armed and card in eyes.shooters:
            # a gunman behind a wall: walking in, he'd see you first - wait for him round the corner of his
            # room (he comes, or you go in from there: throwing distance, the shortest way in his sight)
            spot = corner(goal, eyes.fire, eyes.blocked)
            if spot is not None and can_reach(eyes, spot, now):
                there = math.dist(spot, you) <= CORNER_NEAR
                if not waited(card, there, now):
                    if not there:
                        return Plan(
                            goal=spot,
                            close_enough=CORNER_NEAR,
                            text=f"TO THE CORNER by a gunman {math.dist(goal, you):3.0f} away",
                        )
                    return Plan(
                        goal=spot,
                        close_enough=CORNER_NEAR,
                        text=f"WAITING by the corner for a gunman, "
                        f"{AMBUSH_WAIT - (now - waiting_since):.1f} s",
                    )
            return Plan(
                goal=goal,
                text=f"GOING IN at a gunman behind a wall {math.dist(goal, you):3.0f} away",
            )
        return Plan(
            goal=goal,
            text=f"HUNTING an enemy behind a wall {math.dist(goal, you):3.0f} away",
        )
    arrow = eyes.arrow
    if arrow is not None and (
        not can_reach(eyes, arrow, now)
        or any(
            floor == eyes.scene and math.dist(arrow, xy) < SAME_ARROW
            for floor, xy in left_arrows
        )
    ):
        arrow = None  # no way there, or tapped for nothing: the car, the stairs...
    if (
        arrow is not None
        and hands.use_goal is not None
        and math.dist(hands.use_goal, arrow) < SAME_ARROW
        and hands.use_taps >= ARROW_TRIES
    ):
        left_arrows.append((eyes.scene, arrow))
        print(f"\nTHE ARROW at {arrow} stays after {ARROW_TRIES} taps - leaving it")
        arrow = None
    if arrow is not None:
        return Plan(
            goal=arrow,
            close_enough=ARROW_WALK,
            use=True,
            text=f"TO THE ARROW {math.dist(arrow, you):3.0f} away",
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
