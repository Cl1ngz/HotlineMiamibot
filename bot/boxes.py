# https://github.com/Cl1ngz/HotlineMiamibot
# bot/boxes.py - what lives between frames, kept in 3 boxes (+ the Plan, made new every frame)
#
# every function gets only the boxes it may change:
#   Eyes   what we know about the floor    <- see(), pause()
#   Hands  the buttons and their timers    <- let_go(), act(), pause()
#   Legs   the way and the WASD keys        <- walk(), pause()
import math
from dataclasses import dataclass, field

from .config import REACH


@dataclass
class Eyes:
    """What the bot knows about the floor. see() fills it, pause() forgets the floor."""

    # when to do the slow part again
    next_scan: float = 0
    next_walls: float = 0
    # the slow part (every SCAN_EVERY / WALLS_EVERY seconds)

    # every enemy card we know of
    enemies: set = field(default_factory=set)

    # wall lines - what you can't see through
    lines: list = field(default_factory=list)

    # cells your middle can't stand in (walls, sofas, fake doors)
    blocked: set = field(default_factory=set)

    # (x, y) of melee weapons lying on the floor
    weapons: list = field(default_factory=list)

    # (x, y) of the level's things to take (the briefcase...)
    goals: list = field(default_factory=list)

    # (x, y) of the stairs with GO! on
    stairs: tuple | None = None

    # (x, y) of the car when the chapter is done
    car: tuple | None = None

    # this floor's name from its walls (core/scenes.py)
    scene: str = ""

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

    you: tuple = (0, 0)

    # your card +0xA0: what you hold (EMPTY_HANDS = nothing)
    hand: int = 0

    # cards that are enemies RIGHT NOW (a body drops out at once)
    still: list = field(default_factory=list)

    # {card: (x, y)} of those you can see
    spots: dict = field(default_factory=dict)

    # {card: (x, y)} of all of them, also behind walls
    hidden: dict = field(default_factory=dict)

    # the one lockon aims at (always one of spots)
    target: int | None = None

    # the target is knocked out on the floor
    lying: bool = False
    # a door lies between you and the target: a swing only hits the door - walk INTO it, it swings open
    behind_door: bool = False

    # {card: (x, y)} of those you see that are NOT lying - they can hit you
    threats: dict = field(default_factory=dict)

    # how fast the target runs at you (px/s, his own steps; >0 = toward you)
    closing: float = 0.0

    # last frame's spots - to see how they move
    last_spots: dict = field(default_factory=dict)
    last_seen_at: float = 0.0


@dataclass
class Hands:
    """The buttons: when to let them go, when they may be pressed again."""

    # let go of the left button, SPACE, right button
    release_at: float | None = None
    space_up_at: float | None = None
    right_up_at: float | None = None

    # left click / SPACE again not before this
    next_swing: float = 0

    # right click again not before this
    next_grab: float = 0

    # until when we think you're sitting on an enemy
    mounted_until: float = 0

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
    # when to search for the way again
    next_plan: float = 0

    # when the way was searched last (before you arrived on this floor = search again)
    planned_at: float = -math.inf

    # walking keys we hold now
    held: set = field(default_factory=set)

    # cell -> until when it's blocked: things we bumped into
    learned: dict = field(default_factory=dict)

    # where you were when you started pushing toward the path point
    pushed_from: tuple = (
        0,
        0,
    )
    # pushed since and when
    pushed_since: float = 0

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

    # (x, y) to pick up with the right button
    grab: tuple | None = None

    # (x, y) where the legs go
    goal: tuple | None = None
    close_enough: float = REACH

    # at the goal tap LMB on it (what arrow points at)
    use: bool = False

    # status line
    text: str = ""
