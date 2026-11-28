# https://github.com/Cl1ngz/HotlineMiamibot
# bot/boxes.py - what lives between frames: Eyes (see), Hands (let_go, act), Legs (walk) - pause() clears them
# Plan = what we want THIS frame, decide() makes a new one every frame
import math
from dataclasses import dataclass, field

from core.danger import line_rows

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
    # our empty guns: where they lie (never pick them up again), and the one that just left the hand
    # (frame, when) - it lands a moment later; the guns on the floor at the last scan {(x, y, frame)}
    empty_guns: list = field(default_factory=list)
    lost_gun: tuple | None = None
    floor_guns: set = field(default_factory=set)
    # weapons walk() couldn't get to (pushed at them, didn't move): where they lie - skipped on this floor
    out_of_reach: list = field(default_factory=list)
    # {cell: until when} goals walk() found no way to (behind glass, a door that never opens) - decide() leaves them
    no_way: dict = field(default_factory=dict)
    goals: list = field(default_factory=list)
    stairs: tuple | None = None
    car: tuple | None = None
    # this floor: its name, its wall count (changes = a new floor), its doors (real and fake), what the arrow
    # points at, when you came, the stairs you came by (they lead back)
    scene: str = ""
    wall_cards: int = -1
    # the cards that are walls or doors (see.py: found once a floor, then only those are read)
    box_cards: list = field(default_factory=list)
    area: tuple | None = (
        None  # the floor's box in cells - the ways stay in it (core/path.py area_of)
    )
    doors: list = field(default_factory=list)
    arrow: tuple | None = None
    arrow_seen_at: float = (
        -math.inf
    )  # when the arrow was found last (see.py keeps it ARROW_KEEP)
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
    you_seen_at: float = (
        -math.inf
    )  # when see() last found you (every shot hides your card for a frame)
    # enemies right now, {card: (x, y)} of those you see, and of all of them (also behind walls)
    still: list = field(default_factory=list)
    spots: dict = field(default_factory=dict)
    hidden: dict = field(default_factory=dict)
    # the target (one of spots): is he lying, is a door between you (walk INTO it)
    target: int | None = None
    gunmen: dict = field(
        default_factory=dict
    )  # {card: (x, y)} the standing ones you see with a gun
    lying: bool = False
    behind_door: bool = False
    # seen and not lying = can hit you; how fast the target runs at you (px/s, >0 = toward you)
    threats: dict = field(default_factory=dict)
    closing: float = 0.0
    # last frame's spots and when - to see how they move
    last_spots: dict = field(default_factory=dict)
    last_seen_at: float = 0.0
    # the danger map: {card: (x, y)} of the standing gunmen and the sitters (weapon unknown), seen or not,
    # what each one sees {card: (his cell, {cells})}, all those cells together, the wall lines for numpy
    shooters: dict = field(default_factory=dict)
    sitters: dict = field(default_factory=dict)
    sight: dict = field(default_factory=dict)
    fire: set = field(default_factory=set)
    crossfire: set = field(default_factory=set)  # the cells two or more of them see
    line_rows: object = field(default_factory=lambda: line_rows([]))


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
    # gun presses in a row that fired nothing (no fire picture) - tells an empty gun when the ammo can't be read
    dry_presses: int = 0
    # the guy we shoot at and how many shots he got - a hit kills, so more = something's in the way
    shot_at: int | None = None
    shots: int = 0
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
    bumps: dict = field(
        default_factory=dict
    )  # (floor, cell) -> how many times we bumped into it
    # (floor, door box) -> how many pushes in vain, and when the last one was counted
    door_tries: dict = field(default_factory=dict)
    door_tried_at: dict = field(default_factory=dict)
    # the arrival the legs know about (a copy of eyes.arrived_at) and where you stood then
    arrived_at: float = -math.inf
    arrived_from: tuple = (0, 0)
    reaches: bool = True  # the last way found gets to the goal
    # going straight at a close goal: from where and since when you haven't moved, no straight until then
    straight_from: tuple = (0, 0)
    straight_since: float = 0
    straight_off: float = 0
    # the weapon we're by (closer than walk.py's STRAIGHT) and since when (too long = you can't get it)
    grab_at: tuple | None = None
    grab_since: float = 0


@dataclass
class Plan:
    """What we want THIS frame. decide() makes a new one every frame."""

    grab: tuple | None = None  # (x, y) to pick up with the right button
    # where the legs go, and how close is close enough
    goal: tuple | None = None
    close_enough: float = REACH
    use: bool = False  # at the goal tap LMB on it (what the arrow points at)
    # throw what you hold at the target once he's in THROW_RANGE (an empty gun, a bat at a gunman)
    throw: bool = False
    text: str = ""  # the status line
