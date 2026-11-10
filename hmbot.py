# https://github.com/Cl1ngz/HotlineMiamibot
# hmbot.py - the bot: one loop that sees, decides and acts, every frame
#
#   python hmbot.py         run until Ctrl+C
#   python hmbot.py 30      stop by itself after 30 seconds
#
# every frame:   let_go -> see -> decide -> act -> walk -> wait_frame
#   see()      reads the game into Eyes             (OSError = no player -> pause() instead)
#   decide()   looks ONLY at Eyes and returns a Plan (never reads or writes the game)
#   act()      the buttons (Hands)
#   walk()     the legs (Legs)
#
# what lives between frames is kept in 3 boxes, and every function gets only the boxes it may change:
#   Eyes   what we know about the floor    <- see(), pause()
#   Hands  the buttons and their timers    <- let_go(), act(), pause()
#   Legs   the way and the WASD keys        <- walk(), pause()
import faulthandler
import json
import math
import os
import signal
import sys
import time
from dataclasses import dataclass, field

from core import lockon
from core.arrow import ArrowWatch
from core.enemies import find_aim, find_me_card, is_enemy, load_rules
from core.hands import (KEY_SPACE, find_button, find_look, key_down, key_up,
                        look_at, press_left, press_right, release_left,
                        release_right)
from core.legs import hold, keys_toward, next_point
from core.memory import (X_OFF, Y_OFF, attach, open_rw, read_double, read_kind,
                         table_cards)
from core.path import blocked_cells, cell_of, find_path
from core.scenes import load_doors, load_scenes, save_doors, scene_id
from core.shelf import Shelf
from core.stairs import find_car, find_stairs
from core.walls import (WALL, can_see, door_boxes, fake_door_boxes, real_walls,
                        wall_lines)
from core.weapons import find_goals, find_weapons, load_names

FPS = 60  # the game runs at 60 frames per second, no point going faster
# seconds between the slow part: finding enemies, weapons, stairs, the car
SCAN_EVERY = 0.25
# walls, sofas and fake doors never move - look for them less often
WALLS_EVERY = 2.0
# an enemy this close gets hit
REACH = 35
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
# a weapon nobody measured yet: as slow as the slowest one
READY_UNKNOWN = 0.45
# hold the left button at most this long - if no swing came by then, let go (enemy gone, something else)
SWING_WAIT = 0.6
# no swing came in SWING_WAIT (a dialogue froze the game, the enemy stepped away): keep the button UP this long
# before pressing again - the game must SEE it go up, or it never notices a new press
# (in the tutorial the text then moved on only once every ~4 s)
RELEASE_GAP = 0.15
# card +0x10 of an enemy knocked out on the floor: a swing does nothing to him, SPACE finishes him
# (0x16 the usual ones, 0x12b the one outside by the dumpster - the game puts a red arrow over him)
KNOCKED = (0x16, 0x12B)
# SPACE works only when you stand (almost) ON him: the game took it at 28-32, never at 34-35
EXECUTE_REACH = 30
# so walk up this close to a lying enemy - closer than EXECUTE_REACH, or you stop right at the edge
EXECUTE_WALK = 16
# after SPACE you sit on him: the game hides your card (no player found) and you finish him with the LEFT button
# seconds after SPACE we keep hitting even without seeing you
MOUNTED_FOR = 2.0
# an execution takes 1 s, and an enemy runs ~180 in that time: no SPACE while someone stands closer than this
EXEC_SAFE = 200
# how fast an enemy runs (blackbox: ~3 units a frame)
ENEMY_SPEED = 180
# back off this far at a time - less than STRAIGHT, so the legs walk straight there
BACK_STEP = 24
# an enemy running at you faster than this (his own steps, px/s) is CHARGING: don't run into him - meet him
# standing (he runs ~180; running into him doubles the speed you meet at, and in the logs he always hit first)
CHARGE_SPEED = 60
# ...when he's this close (further away: walk on, he may still turn)
MEET_FAR = 150
# from the press to the hit takes about this long: against a charger press when he's this many seconds of his
# run further than REACH (the 3 deaths on the metro's floor 2: LMB at 24-31, dead one frame later)
SWING_LEAD = 0.15
# measure his run over this long (every frame is too jumpy: the bot can read the same game frame twice)
CLOSING_EVERY = 0.1
# the stairs that light up this soon after you came to a floor, this close to you, are the ones you came by:
# they lead BACK, so they're never a goal (until they go off and light up again - then the floor is done)
ARRIVAL_TIME = 1.5
ARRIVAL_NEAR = 64
# you moved this far in one frame: a new floor (stairs, car) or the floor starting again after a death
JUMP = 100
# the legs keep away from lit stairs that aren't the goal (stepping on them = another floor)
STAIRS_SIZE = 16
# someone dropped out of the enemies (died, stood up, got knocked down): his NEW card can be on the shelf
# only, not in the table - so look at the whole shelf EVERY frame for this long, not only every SCAN_EVERY
RESCAN_FOR = 0.2
# nothing to do for this long (a dialogue, the score screen, a title card): tap the left button to go on
IDLE_CLICK_AFTER = 1.5
# ...one tap every this many seconds
IDLE_CLICK_EVERY = 0.5
# seconds between two searches for the way
REPLAN = 0.5
# your card +0xA0 when your hands are empty: at rest / punching
EMPTY_HANDS = (0x1, 0x85)
# this close to a weapon -> right click picks it up (the press test worked at 13)
GRAB_REACH = 10
# after a right click wait this long: +0xA0 changes a moment later, and a 2nd click would THROW the weapon
GRAB_COOLDOWN = 0.5
# the game executes on the PRESS of SPACE, not while it's held (tested by hand) - so short taps, often:
# the moment the enemy can be finished (~0.4 s after he falls), a tap comes within EXEC_EVERY
EXEC_TAP = 0.05
EXEC_EVERY = 0.1
# the goal is this close and you can see it -> walk straight there, no path (the path ends in the
# MIDDLE of a 16x16 cell - up to 11 away from the weapon, too far to pick it up)
STRAIGHT = 32
# the red arrow: walk this close to what it points at...
ARROW_WALK = 8
# a spot shown with tools/scene_tool.py: walk this close to it (then stand there and tap LMB - the talk goes on)
SPOT_WALK = 8
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
MOVED_A_BIT = 2

# holding the keys along the path but not moving for this long: we bumped into something the walls don't know
# (a bin, a car...) - remember that cell as blocked and find a new way (before STUCK_TAP_AFTER swings at it)
BUMP_AFTER = 0.4
# ...and forget it after this long (a dialogue also stops you - it shouldn't block a cell for ever)
FORGET_AFTER = 8
# just arrived (a restart after a death, a new floor): the game holds you still for ~2 s, and pushing then
# is no bump. Bumps count again once you've moved from the arrival spot, or after SETTLE (you really stand at something)
SETTLE = 3
# you're this close to a door's box when you bump: it's that door you pushed (a door is a 4 x 32 plank)
DOOR_NEAR = 12
# pushed a door this many times on a floor and it never opened: a fake one - a wall there, for good (doors.json).
# Not after one push: a dialogue freezes the game and stops you at a real door too
DOOR_TRIES = 2
# two bumps at the same door closer than this are ONE try (one push, or one dialogue that froze the game)
DOOR_AGAIN = 4
# what the bot is doing, for tools/radar.py (the same name is in tools/radar.py) - rewritten this often
NOW_FILE = "/tmp/hmbot_now.json"
SHARE_EVERY = 0.1
# at the start wait this long for the crosshair (find_look picks the look chain by it)
LOOK_WAIT = 3

# mem, mem_rw, rules and names are set ONCE at the start (bottom of the file) and never change,
# so every function below just uses them - like FPS


# --- the boxes ---


@dataclass
class Eyes:
    """What the bot knows about the floor. see() fills it, pause() forgets the floor."""

    # when to do the slow part again
    next_scan: float = 0
    next_walls: float = 0
    # the slow part (every SCAN_EVERY / WALLS_EVERY seconds)
    enemies: set = field(default_factory=set)  # every enemy card we know of
    lines: list = field(default_factory=list)  # wall lines - what you can't see through
    blocked: set = field(
        default_factory=set
    )  # cells your middle can't stand in (walls, sofas, fake doors)
    weapons: list = field(
        default_factory=list
    )  # (x, y) of melee weapons lying on the floor
    goals: list = field(
        default_factory=list
    )  # (x, y) of the level's things to take (the briefcase...)
    stairs: tuple | None = None  # (x, y) of the stairs with GO! on
    car: tuple | None = None  # (x, y) of the car when the chapter is done
    scene: str = ""  # this floor's name from its walls (core/scenes.py)
    # how many wall cards the table had at the last scan (it changes = a new floor)
    wall_cards: int = -1
    # boxes of every door on this floor, real and fake (walls.door_boxes)
    doors: list = field(default_factory=list)
    # (x, y) of what the red arrow points at (looked for only when no enemy is left)
    arrow: tuple | None = None
    # when you came to this floor (a jump: the stairs, the car, a restart after dying)
    arrived_at: float = -math.inf
    # (x, y) of the lit stairs you came by - they lead back (None = not by stairs, or they went off since)
    came_by: tuple | None = None
    # until when the enemies are looked for on the whole shelf every frame
    rescan_until: float = 0
    # every frame
    you: tuple = (0, 0)
    hand: int = 0  # your card +0xA0: what you hold (EMPTY_HANDS = nothing)
    still: list = field(
        default_factory=list
    )  # cards that are enemies RIGHT NOW (a body drops out at once)
    spots: dict = field(default_factory=dict)  # {card: (x, y)} of those you can see
    hidden: dict = field(
        default_factory=dict
    )  # {card: (x, y)} of all of them, also behind walls
    target: int | None = None  # the one lockon aims at (always one of spots)
    lying: bool = False  # the target is knocked out on the floor
    # {card: (x, y)} of those you see that are NOT lying - they can hit you
    threats: dict = field(default_factory=dict)
    # how fast the target runs at you (px/s, his own steps; >0 = toward you)
    closing: float = 0.0
    last_spots: dict = field(
        default_factory=dict
    )  # last frame's spots - to see how they move
    last_seen_at: float = 0.0


@dataclass
class Hands:
    """The buttons: when to let them go, when they may be pressed again."""

    release_at: float | None = None  # let go of the left button
    space_up_at: float | None = None  # let go of SPACE
    right_up_at: float | None = None  # let go of the right button
    next_swing: float = 0  # left click / SPACE again not before this
    next_grab: float = 0  # right click again not before this
    mounted_until: float = 0  # until when we think you're sitting on an enemy
    # your hand sprite when we pressed the left button for a swing (None = not waiting for a swing)
    rest_hand: int | None = None
    # when the weapon takes the next swing
    ready_at: float = 0
    # your hand sprite when the weapon is at rest (remembered at the last swing) - when the hand shows it
    # again, the swing animation is over and we may press again (the game swings once the weapon is ready)
    at_rest: int | None = None
    # since when the bot has had nothing to do (None = it has something to do)
    idle_since: float | None = None
    # while you want to walk: where you and the enemies you see stood, and since when (a dialogue stops them all)
    still_at: tuple = (0, 0)
    still_spots: dict = field(default_factory=dict)
    still_since: float = 0
    # the thing we're using now, and how many taps it got (they start again for a new thing)
    use_goal: tuple | None = None
    use_taps: int = 0


@dataclass
class Legs:
    """The way we walk and the keys we hold."""

    path: list | None = None
    next_plan: float = 0  # when to search for the way again
    planned_at: float = (
        -math.inf
    )  # when the way was searched last (before you arrived on this floor = search again)
    held: set = field(default_factory=set)  # walking keys we hold now
    learned: dict = field(
        default_factory=dict
    )  # cell -> until when it's blocked: things we bumped into
    # where you were when you started pushing toward the path point
    pushed_from: tuple = (
        0,
        0,
    )
    pushed_since: float = 0  # ...and when
    # the floor `learned` is about (another floor - forget it, the floors lie one above the other)
    scene: str = ""
    # door box -> how many times we pushed it on this floor in vain
    door_tries: dict = field(default_factory=dict)
    # door box -> when we last counted a try at it
    door_tried_at: dict = field(default_factory=dict)
    # the arrival the legs know about (a copy of eyes.arrived_at) and where you stood then
    arrived_at: float = -math.inf
    arrived_from: tuple = (0, 0)


@dataclass
class Plan:
    """What we want THIS frame. decide() makes a new one every frame."""

    grab: tuple | None = None  # (x, y) to pick up with the right button
    goal: tuple | None = None  # (x, y) where the legs go
    close_enough: float = REACH  # this close to the goal - stop walking
    use: bool = False  # at the goal: tap LMB on it (what the arrow points at)
    text: str = ""  # the status line


# --- small helpers ---


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
    }
    with open(NOW_FILE + ".tmp", "w") as f:
        json.dump(data, f)
    os.replace(
        NOW_FILE + ".tmp", NOW_FILE
    )  # the swap is instant: the radar sees the old file or the new one


def where(mem, cards):
    """{card: (x, y)} of these cards - seen or behind a wall."""
    spots = {}
    for card in cards:
        try:
            spots[card] = (
                read_double(mem, card + X_OFF),
                read_double(mem, card + Y_OFF),
            )
        except OSError:
            continue
    return spots


def choose_weapon(weapons, you, enemy_far, lines):
    """The weapon to go for, (x, y), or None.
    Only weapons you can see, and only if the nearest one is closer than the enemy (enemy_far = math.inf: no enemy).
    """
    seen = [xy for xy in weapons if can_see(you, xy, lines)]
    if not seen:
        return None
    nearest = min(seen, key=lambda xy: math.dist(xy, you))
    if math.dist(nearest, you) > enemy_far:
        return None
    return nearest


def away_from(you, enemy, step):
    """The point `step` away from you, straight AWAY from the enemy."""
    dist = math.dist(you, enemy)
    if dist == 0:
        return you
    return (
        you[0] + (you[0] - enemy[0]) / dist * step,
        you[1] + (you[1] - enemy[1]) / dist * step,
    )


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


def click(hands, now):
    """A plain left click: press it now - let_go() lets go of it after HOLD.
    For sitting on an enemy (pause): your card is hidden then, so there's no hand to watch.
    """
    press_left(mem, mem_rw)
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
    press_left(mem, mem_rw)
    hands.rest_hand = eyes.hand
    hands.release_at = now + SWING_WAIT


def swing_started(hands, eyes, now):
    """Has the swing we hold the button for started? Then let go, and note when the weapon is ready again."""
    if hands.rest_hand is not None and eyes.hand != hands.rest_hand:
        release_left(mem, mem_rw)
        hands.release_at = None
        hands.ready_at = now + READY.get(hands.rest_hand, READY_UNKNOWN)
        hands.at_rest = hands.rest_hand
        hands.rest_hand = None


# --- one frame, step by step ---


def let_go(hands, now):
    """Let go of every button whose time is up."""
    if hands.release_at is not None and now >= hands.release_at:
        release_left(mem, mem_rw)
        hands.release_at = None
        if hands.rest_hand is not None:
            # we held it for a swing that never came: stay up a moment, so the next press is a NEW press
            hands.next_swing = now + RELEASE_GAP
        hands.rest_hand = None
    if hands.space_up_at is not None and now >= hands.space_up_at:
        key_up(mem, mem_rw, KEY_SPACE)
        hands.space_up_at = None
    if hands.right_up_at is not None and now >= hands.right_up_at:
        release_right(mem, mem_rw)
        hands.right_up_at = None


def see(eyes, now):
    """Read everything the bot needs from the game into eyes.
    Raises OSError when there's no player: the menu, a new floor, or you sit on an enemy.
    """
    # a new photo of the game's memory for THIS frame - every read below goes through it
    shelf = Shelf(mem)
    # the enemies from the whole shelf: every SCAN_EVERY - and EVERY frame for a moment after someone dropped out
    if now >= eyes.next_scan or now < eyes.rescan_until:
        eyes.enemies = {r for r in shelf.cards if is_enemy(shelf, r, rules)}
    if now >= eyes.next_scan:
        records = shelf.records
        # the stairs take you to a new floor WITHOUT a pause (the floors lie one above the other), so the walls
        # must be read again at once, not up to WALLS_EVERY later - with the old walls the way leads you straight
        # back onto the stairs. Counting the wall cards in the table is cheap, so it's done every scan
        wall_cards = sum(
            1 for card in records if read_kind(shelf, card, 0, 0x14) == WALL
        )
        if wall_cards != eyes.wall_cards:
            eyes.wall_cards = wall_cards
            eyes.next_walls = 0
        if now >= eyes.next_walls:
            # every wall and sofa ONCE: a list of (xy, box) pairs
            walls = real_walls(shelf, records, shelf.cards)
            # the same walls -> the same name. A NEW name = you're on a new floor (the stairs, the car, a new level)
            scene = scene_id(walls)
            if scene != eyes.scene:
                eyes.arrived_at = now
            eyes.scene = scene
            # the positions -> the lines you can't see through
            eyes.lines = wall_lines([xy for xy, box in walls])
            # the boxes (+ the fake doors) -> the cells you can't stand in
            # every door, real or fake - which one never opens, only pushing it tells (walk() finds out)
            eyes.doors = door_boxes(shelf, shelf.cards)
            # the boxes (+ the doors we know never open on this floor) -> the cells you can't stand in
            boxes = [box for xy, box in walls] + [
                tuple(box) for box in fake_doors.get(scene, [])
            ]
            eyes.blocked = blocked_cells(boxes)
            eyes.next_walls = now + WALLS_EVERY
        stairs = find_stairs(shelf, records)
        # the stairs you came by - lit right after you arrived, right next to you: they lead BACK
        if (
            stairs is not None
            and now - eyes.arrived_at < ARRIVAL_TIME
            and math.dist(eyes.you, stairs) < ARRIVAL_NEAR
        ):
            eyes.came_by = stairs
        if stairs is None:
            # they went off (enemies came, or you came close): when they light up again, the floor is done
            eyes.came_by = None
        eyes.stairs = stairs
        eyes.car = find_car(shelf, records, shelf.cards)
        eyes.weapons = [
            (x, y)
            for x, y, frame in find_weapons(shelf, shelf.cards)
            if names.get(frame, {}).get("kind") == "melee"
        ]
        eyes.goals = find_goals(shelf, shelf.cards)
        eyes.next_scan = now + SCAN_EVERY
    # table cards that aren't known enemies yet: new ones AND ones that just became enemies
    # (a sitting enemy stands up) - check them NOW instead of waiting for the next scan
    cards = table_cards(shelf)
    for card in cards - eyes.enemies:
        if is_enemy(shelf, card, rules):
            eyes.enemies.add(card)

    me = find_me_card(shelf)
    if me is None:
        raise OSError("no player found")
    # NEW: you moved far in one frame -> a new floor (stairs, car), or the floor starting again after a death
    you = (read_double(shelf, me + X_OFF), read_double(shelf, me + Y_OFF))
    if math.dist(you, eyes.you) > JUMP:
        eyes.arrived_at = now
    eyes.you = you
    eyes.hand = read_kind(shelf, me, 0, 0xA0)

    # only cards that are STILL enemies right now - a shell or a body drops out at once
    eyes.still = [card for card in eyes.enemies if is_enemy(shelf, card, rules)]
    # someone dropped out (died, stood up, got knocked down): his new card can be on the shelf only -
    # look at the whole shelf every frame for a moment
    if len(eyes.still) < len(eyes.enemies):
        eyes.rescan_until = now + RESCAN_FOR
    # (visible_enemies wants the cards that are alive - that's exactly eyes.still now)
    eyes.spots = lockon.visible_enemies(
        shelf, eyes.still, set(eyes.still), eyes.you, eyes.lines
    )
    eyes.threats = {
        card: xy
        for card, xy in eyes.spots.items()
        if read_kind(shelf, card, 0, 0x10) not in KNOCKED
    }
    # standing enemies that could reach you during an execution: fight THEM first, the lying one waits
    danger = {
        card: xy
        for card, xy in eyes.threats.items()
        if math.dist(xy, eyes.you) < EXEC_SAFE
    }
    # an empty dict counts as False: "danger or eyes.spots" = danger if there is any, else everyone
    eyes.target = lockon.choose_target(shelf, danger or eyes.spots, eyes.you, rules)
    eyes.lying = (
        eyes.target is not None and read_kind(shelf, eyes.target, 0, 0x10) in KNOCKED
    )
    # how fast the target runs at you - his own steps over the last CLOSING_EVERY, not yours
    if now - eyes.last_seen_at >= CLOSING_EVERY:
        eyes.closing = 0.0
        if eyes.target in eyes.last_spots:
            (x0, y0), (x1, y1) = eyes.last_spots[eyes.target], eyes.spots[eyes.target]
            far = math.dist((x1, y1), eyes.you)
            if far > 0:
                # his step, measured along the line from him to you, per second
                eyes.closing = (
                    ((x1 - x0) * (eyes.you[0] - x1) + (y1 - y0) * (eyes.you[1] - y1))
                    / far
                    / (now - eyes.last_seen_at)
                )
        eyes.last_spots, eyes.last_seen_at = dict(eyes.spots), now
    eyes.hidden = where(shelf, eyes.still)
    # the red arrow - only when nobody is left (in a fight it's not needed, and it costs a little every frame)
    eyes.arrow = None if eyes.still else watch.update(now)


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
        # back off: he stands, the weapon isn't ready yet, and he'll be in reach before it is
        if (
            not eyes.lying
            and time_left > 0
            and enemy_far < REACH + ENEMY_SPEED * time_left
        ):
            return Plan(
                goal=away_from(you, target_xy, BACK_STEP),
                close_enough=0,
                text=f"BACKING OFF {enemy_far:3.0f} away, ready in {time_left:.2f} s",
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
    spot = scenes.get(eyes.scene)
    if spot is not None:
        return Plan(
            goal=tuple(spot),
            close_enough=SPOT_WALK,
            text=f"TO THE SHOWN SPOT {math.dist(spot, you):3.0f} away",
        )
    return Plan(text="no enemy in sight")


def act(plan, eyes, hands, now):
    """The buttons: aim at the target and hit him, right click what the plan wants to grab."""
    swing_started(hands, eyes, now)
    if eyes.target is not None:
        xy = eyes.spots[eyes.target]
        look_at(mem, mem_rw, xy)
        far = math.dist(xy, eyes.you)
        if eyes.lying:
            # on the floor: stand on him and press SPACE (like a click: hold a moment, then let go)
            if (
                far < EXECUTE_REACH
                and hands.space_up_at is None
                and now >= hands.next_swing
            ):
                key_down(mem, mem_rw, KEY_SPACE)
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
        ):
            start_swing(hands, eyes, now)

    if plan.grab is not None:
        if (
            math.dist(plan.grab, eyes.you) < GRAB_REACH
            and hands.right_up_at is None
            and now >= hands.next_grab
        ):
            press_right(mem, mem_rw)
            hands.right_up_at = now + HOLD
            hands.next_grab = now + GRAB_COOLDOWN
    if plan.use:
        look_at(mem, mem_rw, plan.goal)  # the crosshair on it - a throw flies there
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
                press_right(mem, mem_rw)
                hands.right_up_at = now + HOLD
            else:
                click(
                    hands, now
                )  # the TV, the round thing, the briefcase into the dumpster, a dialogue
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


def door_at(you, doors):
    """The door you stand at (its box), or None: you're within DOOR_NEAR of its box."""
    for left, top, right, bottom in doors:
        if (
            left - DOOR_NEAR < you[0] < right + DOOR_NEAR
            and top - DOOR_NEAR < you[1] < bottom + DOOR_NEAR
        ):
            return (left, top, right, bottom)
    return None


def fake_door(eyes, legs, door):
    """We pushed this door DOOR_TRIES times and it never opened: a wall for good - now, and on every next visit."""
    legs.learned.update({cell: math.inf for cell in blocked_cells([door])})
    saved = fake_doors.setdefault(eyes.scene, [])
    if list(door) not in saved:
        saved.append(list(door))
        save_doors(fake_doors)
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
                bumps = {cell for cell, until in legs.learned.items() if until != math.inf}
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
                        print("\nthe bumps cut the goal off - forgot them, taking the way through")
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
            tried = (eyes.scene, door)  # this door on THIS floor - the same spot on another floor is another door
            if now - legs.door_tried_at.get(tried, -math.inf) > DOOR_AGAIN:
                # a NEW try at a door that didn't open (not the same push again): count it - the DOOR_TRIES-th is a fake
                legs.door_tried_at[tried] = now
                legs.door_tries[tried] = legs.door_tries.get(tried, 0) + 1
                if legs.door_tries[tried] >= DOOR_TRIES:
                    fake_door(eyes, legs, door)
        legs.next_plan = now  # a new way right now, around it
        legs.pushed_from, legs.pushed_since = you, now
        print(f"\nBUMPED into something at {point} - going around it")
    legs.held = hold(mem, mem_rw, keys, legs.held)


def pause(err, eyes, hands, legs, now):
    """No player this frame. Sitting on an enemy -> keep hitting. Anything else -> forget the floor and wait."""
    if now < hands.mounted_until:
        # sitting on him: we can't see you, but we know what's going on - keep hitting
        if hands.release_at is None and now >= hands.next_swing:
            click(hands, now)
        status("MOUNTED - hitting")
        time.sleep(1 / FPS)  # not 0.2 s like a pause - every frame counts here
    else:
        lockon.reset()  # menu / new floor: forget the old target
        eyes.stairs = None  # new floor: the old stairs are not ours any more
        eyes.car = None
        legs.learned.clear()  # new floor: the things we bumped into are not here
        eyes.next_scan = 0  # look at the new floor right away
        eyes.next_walls = 0  # a new floor: new walls right away
        status(f"{err} (paused)")
        idle_tap(
            hands, now
        )  # the score screen / a title card: no player, nothing else to do - tap through it
        time.sleep(0.2)
    legs.held = hold(mem, mem_rw, set(), legs.held)


def wait_frame(eyes, now):
    """Wait for the next frame - and keep the crosshair on the target meanwhile."""
    frame_end = now + 1 / FPS
    aim = eyes.target is not None
    while time.monotonic() < frame_end:
        if aim:
            try:
                look_at(mem, mem_rw, eyes.spots[eyes.target])
            except OSError:
                aim = False  # can't write right now - stop for this frame, the next one tries again
        time.sleep(0.002)  # don't burn CPU while waiting for the next frame


# --- start ---

mem, regions, static_regions = attach()
mem_rw = open_rw()
# stuck? in another terminal:  kill -USR1 $(pgrep -f hmbot.py)   -> where it is right now goes to stuck.txt
stuck_file = open("stuck.txt", "w")
faulthandler.register(signal.SIGUSR1, file=stuck_file)
rules = load_rules()
# weapon frame -> {"name": ..., "kind": ...}
names = load_names()
# floor name -> [x, y] of the spot to walk to (tools/scene_tool.py)
scenes = load_scenes()
# floor name -> boxes of the doors that never open there (walk() learns them by pushing)
fake_doors = load_doors()
# the red arrow: a little search every frame (core/arrow.py)
watch = ArrowWatch(mem, regions)
if not rules:
    raise SystemExit(
        "no enemy rules yet - add one: python -m tools.enemy_tool look, then save N"
    )
stop_at = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else math.inf

eyes, hands, legs = Eyes(), Hands(), Legs()
slowest = 0
next_share = 0  # when to tell the radar again
try:
    wait_for_game(mem)
    pick_look()
    pick_button()
    watch.search_all()
    print(f"the arrow lists: {len(watch.blocks)} memory block(s)")
    while time.monotonic() < stop_at:
        now = time.monotonic()
        let_go(hands, now)
        try:
            see(eyes, now)
        except OSError as err:
            pause(err, eyes, hands, legs, now)
            if now >= next_share:
                share(Plan(text=f"{err} (paused)"), eyes, legs)
                next_share = now + SHARE_EVERY
            # only the loop can skip the rest of the frame - see() can't
            continue
        plan = decide(eyes, hands, now)
        try:
            act(plan, eyes, hands, now)
            walk(plan, eyes, legs, now)
        except OSError as err:
            # a write didn't reach the game: the look chain may lead somewhere else now - pick it again
            if find_look(mem, find_aim(mem)) is None:
                status(f"can't write to the game: {err}")
            time.sleep(1 / FPS)
            continue
        status(plan.text)
        if now >= next_share:
            share(plan, eyes, legs)
            next_share = now + SHARE_EVERY

        # ms spent on see + decide + act + walk in this loop
        work = (time.monotonic() - now) * 1000
        slowest = max(slowest, work)
        if work > 1000 / FPS:
            print(f"\nslow loop: {work:.1f} ms")
        wait_frame(eyes, now)
except KeyboardInterrupt:
    pass
finally:
    print("\nbye!")
    release_left(mem, mem_rw)
    release_right(mem, mem_rw)
    key_up(mem, mem_rw, KEY_SPACE)
    hold(mem, mem_rw, set(), legs.held)
    print(f"slowest loop: {slowest:.1f} ms")
