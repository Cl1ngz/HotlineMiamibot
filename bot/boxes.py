# https://github.com/Cl1ngz/HotlineMiamibot
# bot/boxes.py - what lives between frames: Eyes (see), Hands (let_go, act), Legs (walk) - pause() clears them
# Plan = what we want THIS frame, decide() makes a new one every frame
import math
from dataclasses import dataclass, field

from .config import REACH


@dataclass
class Eyes:
    """What the bot knows about the floor. see() fills it, pause() forgets the floor."""

    # when to do the slow part again (SCAN_EVERY / WALLS_EVERY)
    next_scan: float = 0
    next_walls: float = 0
    # the slow part: enemy cards, wall lines, cells you can't stand in, melee weapons, goals (the briefcase),
    # the stairs with GO!, the ready car
    enemies: set = field(default_factory=set)
    lines: list = field(default_factory=list)
    blocked: set = field(default_factory=set)
    weapons: list = field(default_factory=list)
    goals: list = field(default_factory=list)
    stairs: tuple | None = None
    car: tuple | None = None
    # this floor: its name, its wall count (changes = a new floor), its doors (real and fake), what the arrow
    # points at, when you came, the stairs you came by (they lead back)
    scene: str = ""
    wall_cards: int = -1
    doors: list = field(default_factory=list)
    arrow: tuple | None = None
    arrived_at: float = -math.inf
    came_by: tuple | None = None
    rescan_until: float = (
        0  # until when enemies are looked for on the whole shelf every frame
    )
    # every frame: you, what you hold (your card +0xA0), is it a gun, its ammo (None = no gun / can't read)
    you: tuple = (0, 0)
    hand: int = 0
    gun: bool = False
    ammo: int | None = None
    # enemies right now, {card: (x, y)} of those you see, and of all of them (also behind walls)
    still: list = field(default_factory=list)
    spots: dict = field(default_factory=dict)
    hidden: dict = field(default_factory=dict)
    # the target (one of spots): is he lying, is a door between you (walk INTO it)
    target: int | None = None
    lying: bool = False
    behind_door: bool = False
    # seen and not lying = can hit you; how fast the target runs at you (px/s, >0 = toward you)
    threats: dict = field(default_factory=dict)
    closing: float = 0.0
    # last frame's spots and when - to see how they move
    last_spots: dict = field(default_factory=dict)
    last_seen_at: float = 0.0


@dataclass
class Hands:
    """The buttons: when to let them go, when they may be pressed again."""

    # when to let go of the left button, SPACE, the right button
    release_at: float | None = None
    space_up_at: float | None = None
    right_up_at: float | None = None
    # not before this: the next left click / SPACE, the next right click
    next_swing: float = 0
    next_grab: float = 0
    mounted_until: float = 0  # until when we think you sit on an enemy
    # a swing: your hand when we pressed (None = not waiting), when the weapon is ready again, and the hand
    # at rest - when the hand shows it again the swing is over and we may press again
    rest_hand: int | None = None
    ready_at: float = 0
    at_rest: int | None = None
    idle_since: float | None = (
        None  # since when there's nothing to do (None = there is)
    )
    # while you want to walk: where you and the enemies stood, and since when (a dialogue stops them all)
    still_at: tuple = (0, 0)
    still_spots: dict = field(default_factory=dict)
    still_since: float = 0
    # the thing we're tapping LMB on now and how many taps it got (they start again for a new thing)
    use_goal: tuple | None = None
    use_taps: int = 0


@dataclass
class Legs:
    """The way we walk and the keys we hold."""

    # the way, when to search it again, when it was searched last (before you arrived = search again)
    path: list | None = None
    next_plan: float = 0
    planned_at: float = -math.inf
    held: set = field(default_factory=set)  # WASD keys held now
    learned: dict = field(
        default_factory=dict
    )  # cell -> until when it's blocked (we bumped into it)
    # pushing toward the path point: from where and since when
    pushed_from: tuple = (0, 0)
    pushed_since: float = 0
    scene: str = ""  # the floor `learned` is about (another floor = forget it)
    # (floor, door box) -> how many pushes in vain, and when the last one was counted
    door_tries: dict = field(default_factory=dict)
    door_tried_at: dict = field(default_factory=dict)
    # the arrival the legs know about (a copy of eyes.arrived_at) and where you stood then
    arrived_at: float = -math.inf
    arrived_from: tuple = (0, 0)


@dataclass
class Plan:
    """What we want THIS frame. decide() makes a new one every frame."""

    grab: tuple | None = None  # (x, y) to pick up with the right button
    # where the legs go, and how close is close enough
    goal: tuple | None = None
    close_enough: float = REACH
    use: bool = False  # at the goal tap LMB on it (what the arrow points at)
    throw: bool = False  # throw what you hold at the target (an empty gun) once he's in THROW_RANGE
    text: str = ""  # the status line
