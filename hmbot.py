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
import math
import signal
import sys
import time
from dataclasses import dataclass, field

from core import lockon
from core.enemies import find_aim, find_me_card, is_enemy, load_rules
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
from core.legs import hold, keys_toward, next_point
from core.memory import (
    X_OFF,
    Y_OFF,
    attach,
    open_rw,
    read_double,
    read_kind,
    table_cards,
)
from core.path import blocked_cells, find_path
from core.shelf import Shelf
from core.stairs import find_car, find_stairs
from core.walls import can_see, fake_door_boxes, real_walls, wall_lines
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
# card +0x10 of an enemy knocked out on the floor: a swing does nothing to him, SPACE finishes him
KNOCKED = 0x16
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
# you just used the stairs (they went off under your feet): don't walk back onto them for this long
# (coming down with the briefcase, the stairs stay lit and the 2 new enemies come ~3 s later)
STAIRS_AGAIN = 5.0
# "under your feet": the stairs went off while you were this close to them
ON_STAIRS = 32
# seconds between two searches for the way
REPLAN = 0.5
# your card +0xA0 when your hands are empty: at rest / punching
EMPTY_HANDS = (0x1, 0x85)
# this close to a weapon -> right click picks it up (the press test worked at 13)
GRAB_REACH = 10
# after a right click wait this long: +0xA0 changes a moment later, and a 2nd click would THROW the weapon
GRAB_COOLDOWN = 0.5
# the goal is this close and you can see it -> walk straight there, no path (the path ends in the
# MIDDLE of a 16x16 cell - up to 11 away from the weapon, too far to pick it up)
STRAIGHT = 32

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
    # when you last used the stairs (-math.inf = never)
    stairs_used_at: float = -math.inf
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


@dataclass
class Legs:
    """The way we walk and the keys we hold."""

    path: list | None = None
    next_plan: float = 0  # when to search for the way again
    held: set = field(default_factory=set)  # walking keys we hold now


@dataclass
class Plan:
    """What we want THIS frame. decide() makes a new one every frame."""

    grab: tuple | None = None  # (x, y) to pick up with the right button
    goal: tuple | None = None  # (x, y) where the legs go
    close_enough: float = REACH  # this close to the goal - stop walking
    text: str = ""  # the status line


# --- small helpers ---


def status(text):
    """One line at the bottom of the terminal that keeps being overwritten."""
    print(f"{text:60}", end="\r", flush=True)


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
    """Wait until you're in a level."""
    while not (find_aim(mem)):
        print(
            "waiting for the crosshair to be visible...",
            end="\r",
            flush=True,
        )
        time.sleep(0.2)
    print()


def click(hands, now):
    """A plain left click: press it now - let_go() lets go of it after HOLD.
    For sitting on an enemy (pause): your card is hidden then, so there's no hand to watch.
    """
    press_left(mem, mem_rw)
    hands.release_at = now + HOLD
    hands.next_swing = now + COOLDOWN


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
        hands.rest_hand = None  # (no swing came in SWING_WAIT - stop waiting for it)
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
    if now >= eyes.next_scan:
        records = shelf.records
        eyes.enemies = {r for r in shelf.cards if is_enemy(shelf, r, rules)}
        if now >= eyes.next_walls:
            # every wall and sofa ONCE: a list of (xy, box) pairs
            walls = real_walls(shelf, records, shelf.cards)
            # the positions -> the lines you can't see through
            eyes.lines = wall_lines([xy for xy, box in walls])
            # the boxes (+ the fake doors) -> the cells you can't stand in
            boxes = [box for xy, box in walls] + fake_door_boxes(shelf, records)
            eyes.blocked = blocked_cells(boxes)
            eyes.next_walls = now + WALLS_EVERY
        stairs = find_stairs(shelf, records)
        # the stairs WERE lit and went off while you stood on them -> you just used them
        if (
            eyes.stairs is not None
            and stairs is None
            and math.dist(eyes.you, eyes.stairs) < ON_STAIRS
        ):
            eyes.stairs_used_at = now
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
    eyes.you = (read_double(shelf, me + X_OFF), read_double(shelf, me + Y_OFF))
    eyes.hand = read_kind(shelf, me, 0, 0xA0)

    # only cards that are STILL enemies right now - a shell or a body drops out at once
    eyes.still = [card for card in eyes.enemies if is_enemy(shelf, card, rules)]
    # (visible_enemies wants the cards that are alive - that's exactly eyes.still now)
    eyes.spots = lockon.visible_enemies(
        shelf, eyes.still, set(eyes.still), eyes.you, eyes.lines
    )
    eyes.threats = {
        card: xy
        for card, xy in eyes.spots.items()
        if read_kind(shelf, card, 0, 0x10) != KNOCKED
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
        eyes.target is not None and read_kind(shelf, eyes.target, 0, 0x10) == KNOCKED
    )
    eyes.hidden = where(shelf, eyes.still)


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
    if eyes.car is not None:
        # the chapter is done: drive away (beats any stairs - some stay lit)
        return Plan(
            goal=eyes.car,
            close_enough=0,
            text=f"TO THE CAR {math.dist(eyes.car, you):3.0f} away",
        )
    if eyes.stairs is not None:
        # you just used the stairs: don't walk straight back onto them
        since = now - eyes.stairs_used_at
        if since < STAIRS_AGAIN:
            return Plan(
                text=f"JUST USED THE STAIRS - waiting {STAIRS_AGAIN - since:.1f} s"
            )
        # floor clear: go to GO!
        return Plan(
            goal=eyes.stairs,
            close_enough=0,
            text=f"TO THE STAIRS {math.dist(eyes.stairs, you):3.0f} away",
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
                hands.space_up_at = now + HOLD
                hands.next_swing = now + COOLDOWN
                hands.mounted_until = now + MOUNTED_FOR
        elif (
            far < REACH
            and hands.release_at is None
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


def walk(plan, eyes, legs, now):
    """The legs: walk to plan.goal - straight when it's close and you can see it, else along the path."""
    you, goal = eyes.you, plan.goal
    keys = set()
    if goal is not None and math.dist(goal, you) > plan.close_enough:
        if math.dist(goal, you) < STRAIGHT and can_see(you, goal, eyes.lines):
            keys = keys_toward(you, goal)  # the last bit: straight there, no path
        else:
            if now >= legs.next_plan:
                legs.path = find_path(you, goal, eyes.blocked)
                legs.next_plan = now + REPLAN
            if legs.path is not None:
                point = next_point(legs.path, you)
                if point is not None:
                    keys = keys_toward(you, point)
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
        eyes.next_scan = 0  # look at the new floor right away
        eyes.next_walls = 0  # a new floor: new walls right away
        status(f"{err} (paused)")
        time.sleep(0.2)
    legs.held = hold(mem, mem_rw, set(), legs.held)


def wait_frame(eyes, now):
    """Wait for the next frame - and keep the crosshair on the target meanwhile."""
    frame_end = now + 1 / FPS
    while time.monotonic() < frame_end:
        if eyes.target is not None:
            look_at(mem, mem_rw, eyes.spots[eyes.target])
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
if not rules:
    raise SystemExit(
        "no enemy rules yet - add one: python -m tools.enemy_tool look, then save N"
    )
stop_at = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else math.inf

eyes, hands, legs = Eyes(), Hands(), Legs()
slowest = 0
try:
    wait_for_game(mem)
    while time.monotonic() < stop_at:
        now = time.monotonic()
        let_go(hands, now)
        try:
            see(eyes, now)
        except OSError as err:
            pause(err, eyes, hands, legs, now)
            # only the loop can skip the rest of the frame - see() can't
            continue
        plan = decide(eyes, hands, now)
        act(plan, eyes, hands, now)
        walk(plan, eyes, legs, now)
        status(plan.text)

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
