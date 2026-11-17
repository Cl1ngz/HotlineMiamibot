# https://github.com/Cl1ngz/HotlineMiamibot
# bot/act.py - the buttons: aim, swing, SPACE, the right button, clicking dialogues away
import math

from core.hands import (
    KEY_SPACE,
    key_down,
    key_up,
    look_at,
    press_left,
    press_right,
    release_left,
    release_right,
)

from . import game
from .config import EMPTY_HANDS, GRAB_REACH, MOVED_A_BIT, REACH

# seconds to hold a button (SPACE, the right button, and the left one while sitting on an enemy)
HOLD = 0.15
# seconds between two SPACE presses / two clicks while sitting on an enemy
COOLDOWN = 0.25
READY = {
    0x1: 0.35,  # fists
    0x13: 0.45,  # Baseball Bat
    0x6D: 0.20,  # knife
    0x16: 0.35,  # golf club
    0xF: 0.40,  # lead pipe
    0x16C: 0.35,  # the briefcase (one swing 0.27 s)
}
# unknow weapon not measured yet = slowest one
READY_UNKNOWN = 0.45
# hold left button this amount if no swing then let go anyway dialog or smt
SWING_WAIT = 0.6
# after holding LMB with no swing: keep it UP this long, so the game sees the next press as a new one
RELEASE_GAP = 0.15
# SPACE works only when you stand  ON him: the game took it at 28-32
EXECUTE_REACH = 30
# after space u sit on him game hides your card and u finish him with the left button: 2 seconds is enough
MOUNTED_FOR = 2.0
# press x seconds early agains charging enemy (press -> hit takes ~1 frame 0.03-0.04s)
SWING_LEAD = 0.04
# a door between you and the enemy: through a CLOSED door he's never closer than ~32 (the log: 32-34), so
# closer than this the door must be open already (eyes.doors is read only every WALLS_EVERY) - swing then
DOOR_SWING = 30
# nothing to do this long (a dialogue, the score screen, a title card): tap the left button to go on
IDLE_CLICK_AFTER = 1.5
# one tap every this many seconds
IDLE_CLICK_EVERY = 0.5
# after a right click wait this long: +0xA0 changes a moment later, and a 2nd click would THROW the weapon
GRAB_COOLDOWN = 0.5
# the game executes on the PRESS of SPACE, not while it's held (tested by hand) - so short taps, often:
# the moment the enemy can be finished (~0.4 s after he falls), a tap comes within EXEC_EVERY
EXEC_TAP = 0.05
EXEC_EVERY = 0.1
# ...and from this close tap LMB on it (the TV stops you ~20 away from its middle)
USE_REACH = 24
# seconds between two LMB taps while using something (also clicks the text away)
USE_EVERY = 0.3
# empty hands: this many LMB taps did nothing -> try the right button (a thing to TAKE)
USE_LEFT = 3
# the goal moved this far: a new thing to use (the arrow bobs ~3, a new thing is much further)
NEW_USE = 20
# you want to walk but haven't moved more than MOVED_A_BIT for this long: a dialogue holds you - click it away
STUCK_TAP_AFTER = 0.5


def click(hands, now):
    """A plain left click: press it now - let_go() lets go of it after HOLD.
    For sitting on an enemy (pause): your card is hidden then, so there's no hand to watch.
    """
    press_left(game.mem, game.mem_rw)
    hands.release_at = now + HOLD
    hands.next_swing = now + COOLDOWN


def idle_tap(hands, now):
    """Nothing to do (a dialogue, the score screen, a title card...): after IDLE_CLICK_AFTER, tap LMB now and then."""
    if hands.idle_since is None:
        hands.idle_since = now
    elif (
        now - hands.idle_since > IDLE_CLICK_AFTER
        and hands.release_at is None
        and now >= hands.next_swing
    ):
        click(hands, now)
        hands.next_swing = now + IDLE_CLICK_EVERY


def start_swing(hands, eyes, now):
    """Press the left button and HOLD it until the swing starts (swing_started() sees your hand change).
    The game swings the moment the weapon is ready - if the button is down then."""
    press_left(game.mem, game.mem_rw)
    hands.rest_hand = eyes.hand
    hands.release_at = now + SWING_WAIT


def swing_started(hands, eyes, now):
    """Has the swing we hold the button for started? Then let go, and note when the weapon is ready again."""
    if hands.rest_hand is not None and eyes.hand != hands.rest_hand:
        release_left(game.mem, game.mem_rw)
        hands.release_at = None
        hands.ready_at = now + READY.get(hands.rest_hand, READY_UNKNOWN)
        hands.at_rest = hands.rest_hand
        hands.rest_hand = None


def let_go(hands, now):
    """Let go of every button whose time is up."""
    if hands.release_at is not None and now >= hands.release_at:
        release_left(game.mem, game.mem_rw)
        hands.release_at = None
        if hands.rest_hand is not None:
            # we held it for a swing that never came: stay up a moment, so the next press is a NEW press
            hands.next_swing = now + RELEASE_GAP
        hands.rest_hand = None
    if hands.space_up_at is not None and now >= hands.space_up_at:
        key_up(game.mem, game.mem_rw, KEY_SPACE)
        hands.space_up_at = None
    if hands.right_up_at is not None and now >= hands.right_up_at:
        release_right(game.mem, game.mem_rw)
        hands.right_up_at = None


def act(plan, eyes, hands, now):
    """The buttons: aim at the target and hit him, right click what the plan wants to grab."""
    swing_started(hands, eyes, now)
    if eyes.target is not None:
        xy = eyes.spots[eyes.target]
        look_at(game.mem, game.mem_rw, xy)
        far = math.dist(xy, eyes.you)
        if eyes.lying:
            # on the floor: stand on him and press SPACE (like a click: hold a moment, then let go)
            if (
                far < EXECUTE_REACH
                and hands.space_up_at is None
                and now >= hands.next_swing
            ):
                key_down(game.mem, game.mem_rw, KEY_SPACE)
                # let go of SPACE after 0.05 s
                hands.space_up_at = now + EXEC_TAP
                # the next tap after 0.1 s
                hands.next_swing = now + EXEC_EVERY
                hands.mounted_until = now + MOUNTED_FOR
        elif (
            far < REACH + max(0.0, eyes.closing) * SWING_LEAD
            and hands.release_at is None
            and now >= hands.next_swing
            and (now >= hands.ready_at or eyes.hand == hands.at_rest)
            and (not eyes.behind_door or far < DOOR_SWING)
        ):
            start_swing(hands, eyes, now)

    if plan.grab is not None and (
        math.dist(plan.grab, eyes.you) < GRAB_REACH
        and hands.right_up_at is None
        and now >= hands.next_grab
    ):
        press_right(game.mem, game.mem_rw)
        hands.right_up_at = now + HOLD
        hands.next_grab = now + GRAB_COOLDOWN
    if plan.use:
        look_at(
            game.mem, game.mem_rw, plan.goal
        )  # the crosshair on it - a throw flies there
        if hands.use_goal is None or math.dist(plan.goal, hands.use_goal) > NEW_USE:
            # a new thing to use: start with the left button again
            hands.use_goal, hands.use_taps = plan.goal, 0
        if (
            math.dist(plan.goal, eyes.you) <= USE_REACH
            and hands.release_at is None
            and hands.right_up_at is None
            and now >= hands.next_swing
        ):
            if eyes.hand in EMPTY_HANDS and hands.use_taps >= USE_LEFT:
                # empty hands and LMB did nothing USE_LEFT times: maybe it's to be TAKEN (the shop) - the right button
                press_right(game.mem, game.mem_rw)
                hands.right_up_at = now + HOLD
            else:
                # the TV, the round thing, the briefcase into the dumpster, a dialogue
                click(hands, now)
            hands.use_taps += 1
            hands.next_swing = now + USE_EVERY
    else:
        hands.use_goal = None
    # a dialogue stops the whole game (the text after the TV, the round thing, a talk in a level...):
    # you want to walk, but neither you nor any enemy you see moves -> click the text away.
    # (stuck at a wall in a fight is different: you stand, but the enemies keep coming)
    wants_to_walk = (
        plan.goal is not None and math.dist(plan.goal, eyes.you) > plan.close_enough
    )
    someone_moved = math.dist(eyes.you, hands.still_at) > MOVED_A_BIT or any(
        math.dist(xy, hands.still_spots.get(card, xy)) > MOVED_A_BIT
        for card, xy in eyes.spots.items()
    )
    if not wants_to_walk or someone_moved:
        # start counting again from here
        hands.still_at, hands.still_spots, hands.still_since = (
            eyes.you,
            dict(eyes.spots),
            now,
        )
    elif (
        now - hands.still_since > STUCK_TAP_AFTER
        and hands.release_at is None
        and now >= hands.next_swing
    ):
        # everything has stood still for a while: a dialogue - click it on
        click(hands, now)
        hands.next_swing = now + USE_EVERY
    # nothing to do (no goal, or already standing at it) and no enemy: a dialogue, the score screen - tap LMB
    if (plan.goal is None or not wants_to_walk) and eyes.target is None:
        idle_tap(hands, now)
    else:
        hands.idle_since = None
