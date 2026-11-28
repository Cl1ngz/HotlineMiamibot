# https://github.com/Cl1ngz/HotlineMiamibot
# bot/see.py - see(): everything the bot needs from the game into Eyes, once a frame
import math
from collections import Counter

from core import lockon
from core.danger import line_rows, seen_cells
from core.enemies import find_me_card, is_enemy, shelf_cards
from core.memory import X_OFF, Y_OFF, read_double, read_kind, table_cards, where
from core.path import area_of, blocked_cells, cell_of
from core.scenes import scene_id
from core.shelf import Shelf
from core.stairs import find_car, find_stairs
from core.walls import (
    WALL,
    box_cards,
    crosses_box,
    door_boxes,
    pane_lines,
    real_walls,
    wall_lines,
    window_boxes,
)
from core.weapons import (
    enemy_gun,
    find_goals,
    find_weapons,
    gun_frame,
    held_gun,
    read_ammo,
)

from . import game
from .config import GUN_RANK

SCAN_EVERY = 0.25  # the slow part: enemies, weapons, stairs, the car
WALLS_EVERY = 2.0  # walls, sofas and fake doors never move
# card +0x10 of a knocked out enemy (0x12b = the one by the dumpster, with the red arrow over him)
KNOCKED = (0x16, 0x12B)
# card +0x14 of an enemy sitting (rule 2): his weapon shows only when he gets up - and then he shoots within ~0.4 s
# if it's a gun (level 3: 8 deaths to one man by the TV), so the bot counts every sitter as one
SITTING = 0xA6
# an execution takes 1 s and an enemy runs ~180 in that time: no SPACE while someone stands closer
EXEC_SAFE = 200
# a standing enemy this close: aim at the NEAREST one (of two running at you, the first one there gets hit first)
NEAREST_FIRST = 120
# a gun in hand: the gunmen you see come first - unless one without a gun is this close (he hits first)
MELEE_FIRST = 60
CLOSING_EVERY = 0.1  # measure his run over this long (every frame is too jumpy: the same game frame read twice)
# stairs lit this soon after you came, this close to you, are the ones you came by - they lead BACK
ARRIVAL_TIME = 1.5
ARRIVAL_NEAR = 64
# our empty gun lands this long after it left the hand (thrown ~1 s) - a new gun of its kind by then = it
LANDS_IN = 2.0
SAME_SPOT = 10  # a gun this close to where our empty one lies is that one
JUMP = 100  # you moved this far in one frame: a new floor, or the floor again after a death
# the arrow isn't found in some frames (the logs: to the arrow, to the stairs, to the arrow... every second):
# keep where it pointed this long
ARROW_KEEP = 2.0
# someone dropped out of the enemies: his NEW card can be on the shelf only - look at all of it this long
RESCAN_FOR = 0.2
# nobody left that we know of: look this many cards around the table, not the usual AROUND (64) - after a
# restart the last enemies and the car can lie further (the bot didn't see who killed it, then not the car)
WIDE = 1024


def sort_weapons(eyes, floor, now):
    """eyes.weapons [(x, y, rank)] from the weapons on the floor [(x, y, frame)]: melee with its rank, guns with
    GUN_RANK - but not where our empty gun lies, and not a gun we don't know in the hand (no "hand" in
    weapon_names.json: the bot couldn't tell it's a gun)."""
    guns = {
        (round(x), round(y), frame)
        for x, y, frame in floor
        if game.names.get(frame, {}).get("kind") == "gun"
    }
    if eyes.lost_gun is not None and now - eyes.lost_gun[1] > LANDS_IN:
        eyes.lost_gun = None
    if eyes.lost_gun is not None:
        # a gun of its kind that wasn't on the floor at the last scan = ours, landed
        eyes.empty_guns += [
            (x, y)
            for x, y, frame in guns - eyes.floor_guns
            if frame == eyes.lost_gun[0]
        ]
    eyes.floor_guns = guns
    eyes.weapons = []
    for x, y, frame in floor:
        if any(math.dist((x, y), xy) < SAME_SPOT for xy in eyes.out_of_reach):
            continue  # walk() pushed at it and couldn't get there (it lies on a counter, in a wall's edge)
        info = game.names.get(frame, {})
        if info.get("kind") == "melee":
            eyes.weapons.append((x, y, info.get("rank", 0)))
        elif (
            info.get("kind") == "gun"
            and info.get("hand")
            and not any(math.dist((x, y), xy) < SAME_SPOT for xy in eyes.empty_guns)
        ):
            eyes.weapons.append((x, y, GUN_RANK))


def see(eyes, now):
    """Read everything the bot needs from the game into eyes.
    Raises OSError when there's no player: the menu, a new floor, or you sit on an enemy.
    """
    # one photo of the game's memory for THIS frame - every read below goes through it
    shelf = Shelf(game.mem)
    # enemies from the whole shelf: every SCAN_EVERY, and EVERY frame for a moment after someone dropped out
    if now >= eyes.next_scan or now < eyes.rescan_until:
        scan_cards = (
            shelf.cards if eyes.still else shelf_cards(shelf, shelf.records, WIDE)
        )
        found = {r for r in scan_cards if is_enemy(shelf, r, game.rules)}
        # the ones we already follow stay, even when they're outside the usual shelf
        eyes.enemies = found | {r for r in eyes.still if is_enemy(shelf, r, game.rules)}
    if now >= eyes.next_scan:
        records = shelf.records
        # the stairs take you to a new floor with NO pause, so a new wall count = read the walls now
        # (with the old ones the way leads you straight back onto the stairs)
        wall_cards = sum(
            1 for card in records if read_kind(shelf, card, 0, 0x14) == WALL
        )
        if wall_cards != eyes.wall_cards:
            eyes.wall_cards = wall_cards
            eyes.next_walls = 0
            # another floor, maybe: look for its walls and doors again
            eyes.box_cards = []
        if now >= eyes.next_walls:
            # which cards are walls and doors: the slow search (~15 ms) over the shelf WIDE around the table,
            # once a floor - at the end of a level the table moves away and the usual window held only half
            # the walls (63 of 115 by the metro car). Every WALLS_EVERY only those cards are read (~0.2 ms)
            if not eyes.box_cards:
                eyes.box_cards = box_cards(shelf, shelf_cards(shelf, records, WIDE))
            # every wall and sofa once, as (xy, box) - a new floor name = you just came
            walls = real_walls(shelf, records, eyes.box_cards)
            scene = scene_id(walls)
            if scene != eyes.scene:
                eyes.arrived_at = now
                eyes.empty_guns = []
                eyes.out_of_reach = []
                eyes.arrow = None  # the last floor's arrow
            eyes.scene = scene
            # lines you can't see through, every door (real or fake - pushing tells, walk() does it),
            # cells you can't stand in (walls + glass + the doors we know never open here). Glass isn't in the
            # lines: you see and shoot through it
            eyes.lines = wall_lines([xy for xy, box in walls])
            eyes.area = area_of([xy for xy, box in walls])  # the box the ways stay in
            eyes.doors = door_boxes(shelf, eyes.box_cards)
            windows = window_boxes(shelf, eyes.box_cards)
            # what the gunmen can't see through: walls AND glass (you shoot through glass, they don't)
            eyes.line_rows = line_rows(eyes.lines + pane_lines(windows))
            boxes = (
                [box for xy, box in walls]
                + windows
                + [tuple(box) for box in game.fake_doors.get(scene, [])]
            )
            blocked = blocked_cells(boxes)
            if blocked != eyes.blocked:
                eyes.sight = {}  # other walls or glass: what the gunmen see, again
            eyes.blocked = blocked
            eyes.next_walls = now + WALLS_EVERY
        # stairs lit right after you came, right next to you = the ones you came by; when they go off and
        # light up again, the floor is done
        stairs = find_stairs(shelf, records)
        if (
            stairs is not None
            and now - eyes.arrived_at < ARRIVAL_TIME
            and math.dist(eyes.you, stairs) < ARRIVAL_NEAR
        ):
            eyes.came_by = stairs
        if stairs is None:
            eyes.came_by = None
        eyes.stairs = stairs
        eyes.car = find_car(shelf, records, scan_cards)
        sort_weapons(eyes, find_weapons(shelf, shelf.cards), now)
        eyes.goals = find_goals(shelf, shelf.cards)
        eyes.next_scan = now + SCAN_EVERY
    # every frame: table cards that just became enemies (new, or a sitting one stood up) - now, not next scan
    cards = table_cards(shelf)
    for card in cards - eyes.enemies:
        if is_enemy(shelf, card, game.rules):
            eyes.enemies.add(card)

    # you - moved far in one frame = you just came (a new floor, or again after a death)
    me = find_me_card(shelf)
    if me is None:
        raise OSError("no player found")
    you = (read_double(shelf, me + X_OFF), read_double(shelf, me + Y_OFF))
    if math.dist(you, eyes.you) > JUMP:
        eyes.arrived_at = now
    eyes.you = you
    eyes.you_seen_at = now
    old_gun, old_ammo = gun_frame(eyes.hand, game.names), eyes.ammo
    eyes.hand = read_kind(shelf, me, 0, 0xA0)
    # the ammo stays from the last gun after you throw it - it means something only with a gun in hand
    eyes.gun = held_gun(eyes.hand, game.names)
    if not eyes.gun:
        eyes.ammo = None
    else:
        # the links to the ammo can't always be read (None) - keep the last number then
        ammo = read_ammo(shelf)
        if ammo is not None:
            eyes.ammo = ammo
    # an empty gun just left your hand - thrown, or swapped for another weapon (one of its own kind too: then
    # the ammo jumps up): it'll lie somewhere, empty
    if (
        old_ammo == 0
        and old_gun is not None
        and (gun_frame(eyes.hand, game.names) != old_gun or eyes.ammo)
    ):
        eyes.lost_gun = (old_gun, now)

    # still = enemies RIGHT NOW (a body drops out at once); someone dropped out -> rescan the shelf for a moment
    eyes.still = [card for card in eyes.enemies if is_enemy(shelf, card, game.rules)]
    if len(eyes.still) < len(eyes.enemies):
        eyes.rescan_until = now + RESCAN_FOR
    # who you see, who of them stands (can hit you), who stands close enough to reach you during an execution
    eyes.spots = lockon.visible_enemies(shelf, eyes.still, eyes.you, eyes.lines)
    eyes.threats = {
        card: xy
        for card, xy in eyes.spots.items()
        if read_kind(shelf, card, 0, 0x10) not in KNOCKED
    }
    danger = {
        card: xy
        for card, xy in eyes.threats.items()
        if math.dist(xy, eyes.you) < EXEC_SAFE
    }
    # everyone who can shoot you, seen or behind a wall: standing with a gun, or sitting (weapon unknown)
    eyes.hidden = where(shelf, eyes.still)
    eyes.shooters, eyes.sitters = {}, {}
    for card, xy in eyes.hidden.items():
        if read_kind(shelf, card, 0, 0x14) == SITTING:
            eyes.sitters[card] = xy
        elif read_kind(shelf, card, 0, 0x10) not in KNOCKED and enemy_gun(
            read_kind(shelf, card, 0, 0xA0), game.names
        ):
            eyes.shooters[card] = xy
    # the danger map: what each of them sees (again only when he stepped into another cell)
    sight = {}
    changed = len(eyes.shooters) + len(eyes.sitters) != len(eyes.sight)  # one died
    for card, xy in {**eyes.shooters, **eyes.sitters}.items():
        old = eyes.sight.get(card)
        if old is not None and old[0] == cell_of(xy):
            sight[card] = old
        else:
            sight[card] = (cell_of(xy), seen_cells(xy, eyes.line_rows, eyes.blocked))
            changed = True
    eyes.sight = sight
    if changed:
        # the cells somebody sees, and the cells two or more see (a gun shoots one of them first, not two)
        seen_by = Counter(cell for his_cell, cells in sight.values() for cell in cells)
        eyes.fire = set(seen_by)
        eyes.crossfire = {cell for cell, men in seen_by.items() if men > 1}
    # the standing ones you see with a gun (his picture shows it) who see you too - not through glass: they
    # shoot you from afar (one behind glass you shoot, he doesn't - the bot leaves him for later)
    eyes.gunmen = {
        card: xy
        for card, xy in eyes.threats.items()
        if card in eyes.shooters and cell_of(eyes.you) in sight[card][1]
    }
    # who to aim at: someone standing close -> the nearest one, else the dangerous ones, else everyone you see
    # (an empty dict counts as False). The gunmen first, gun in hand or not (with one: shoot them first,
    # without: decide() throws at them or hides - walking at them is a bullet)
    near = {
        card: xy
        for card, xy in eyes.threats.items()
        if math.dist(xy, eyes.you) < NEAREST_FIRST
    }
    melee_close = any(
        math.dist(xy, eyes.you) < MELEE_FIRST
        for card, xy in near.items()
        if card not in eyes.gunmen
    )
    if eyes.gunmen and not melee_close:
        pick = eyes.gunmen
    elif near:
        nearest = min(near, key=lambda card: math.dist(near[card], eyes.you))
        pick = {nearest: near[nearest]}
    else:
        # a loaded gun kills a standing one with one click from afar: them first, the lying ones wait
        shoot = eyes.threats if eyes.gun and eyes.ammo != 0 else {}
        pick = danger or shoot or eyes.spots
    eyes.target = lockon.choose_target(pick, eyes.you)
    eyes.lying = (
        eyes.target is not None and read_kind(shelf, eyes.target, 0, 0x10) in KNOCKED
    )
    # a real door between you and the target (the fake ones are walls already)
    eyes.behind_door = eyes.target is not None and any(
        crosses_box(eyes.you, eyes.spots[eyes.target], box)
        for box in eyes.doors
        if list(box) not in game.fake_doors.get(eyes.scene, [])
    )
    # how fast the target runs at you: his step along the line from him to you, per second (not your steps)
    if now - eyes.last_seen_at >= CLOSING_EVERY:
        eyes.closing = 0.0
        if eyes.target in eyes.last_spots:
            (x0, y0), (x1, y1) = eyes.last_spots[eyes.target], eyes.spots[eyes.target]
            far = math.dist((x1, y1), eyes.you)
            if far > 0:
                eyes.closing = (
                    ((x1 - x0) * (eyes.you[0] - x1) + (y1 - y0) * (eyes.you[1] - y1))
                    / far
                    / (now - eyes.last_seen_at)
                )
        eyes.last_spots, eyes.last_seen_at = dict(eyes.spots), now
    # the red arrow only when nobody is left (not needed in a fight, and it costs a little every frame)
    arrow = None if eyes.still else game.watch.update(now)
    if arrow is not None:
        eyes.arrow, eyes.arrow_seen_at = arrow, now
    elif eyes.still or now - eyes.arrow_seen_at > ARROW_KEEP:
        eyes.arrow = None
