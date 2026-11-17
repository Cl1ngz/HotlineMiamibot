# https://github.com/Cl1ngz/HotlineMiamibot
# bot/see.py - see(): read everything the bot needs from the game into Eyes, once a frame
import math

from core import lockon
from core.enemies import find_me_card, is_enemy
from core.memory import X_OFF, Y_OFF, read_double, read_kind, table_cards, where
from core.path import blocked_cells
from core.scenes import scene_id
from core.shelf import Shelf
from core.stairs import find_car, find_stairs
from core.walls import WALL, crosses_box, door_boxes, real_walls, wall_lines
from core.weapons import find_goals, find_weapons

from . import game

# seconds between the slow part: finding enemies, weapons, stairs, the car
SCAN_EVERY = 0.25
# walls, sofas and fake doors never move - look for them less often
WALLS_EVERY = 2.0
# card +0x10 of an enemy knocked out
# (0x16 the usual ones, 0x12b the one outside by the dumpster - the game puts a red arrow over him)
KNOCKED = (0x16, 0x12B)
# an execution takes 1 s, and an enemy runs ~180 in that time: no SPACE while someone stands closer than this
EXEC_SAFE = 200
# a standing enemy this close: aim at the NEAREST one, whoever we aimed at before
# (two run at you - the one who gets there first is the one to hit first)
NEAREST_FIRST = 120
# measure his run over this long (every frame is too jumpy: the bot can read the same game frame twice)
CLOSING_EVERY = 0.1
# the stairs that light up this soon after you came to a floor, this close to you, are the ones you came by:
# they lead BACK, so they're never a goal (until they go off and light up again - then the floor is done)
ARRIVAL_TIME = 1.5
ARRIVAL_NEAR = 64
# you moved this far in one frame: a new floor (stairs, car) or the floor starting again after a death
JUMP = 100
# someone dropped out of the enemies (died, stood up, got knocked down): his NEW card can be on the shelf
# only, not in the table - so look at the whole shelf EVERY frame for this long, not only every SCAN_EVERY
RESCAN_FOR = 0.2


def see(eyes, now):
    """Read everything the bot needs from the game into eyes.
    Raises OSError when there's no player: the menu, a new floor, or you sit on an enemy.
    """
    # a new photo of the game's memory for THIS frame - every read below goes through it
    shelf = Shelf(game.mem)
    # the enemies from the whole shelf: every SCAN_EVERY - and EVERY frame for a moment after someone dropped out
    if now >= eyes.next_scan or now < eyes.rescan_until:
        eyes.enemies = {r for r in shelf.cards if is_enemy(shelf, r, game.rules)}
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
                tuple(box) for box in game.fake_doors.get(scene, [])
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
            if game.names.get(frame, {}).get("kind") == "melee"
        ]
        eyes.goals = find_goals(shelf, shelf.cards)
        eyes.next_scan = now + SCAN_EVERY
    # table cards that aren't known enemies yet: new ones AND ones that just became enemies
    # (a sitting enemy stands up) - check them NOW instead of waiting for the next scan
    cards = table_cards(shelf)
    for card in cards - eyes.enemies:
        if is_enemy(shelf, card, game.rules):
            eyes.enemies.add(card)

    me = find_me_card(shelf)
    if me is None:
        raise OSError("no player found")
    #  you moved far in one frame -> a new floor (stairs, car), or the floor starting again after a death
    you = (read_double(shelf, me + X_OFF), read_double(shelf, me + Y_OFF))
    if math.dist(you, eyes.you) > JUMP:
        eyes.arrived_at = now
    eyes.you = you
    eyes.hand = read_kind(shelf, me, 0, 0xA0)

    # only cards that are STILL enemies right now - a shell or a body drops out at once
    eyes.still = [card for card in eyes.enemies if is_enemy(shelf, card, game.rules)]
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
    # someone standing is close: the NEAREST one, whoever we aimed at before (lockon keeps its target until
    # another is clearly closer - two side by side, and the other one gets there first)
    near = {
        card: xy
        for card, xy in eyes.threats.items()
        if math.dist(xy, eyes.you) < NEAREST_FIRST
    }
    if near:
        nearest = min(near, key=lambda card: math.dist(near[card], eyes.you))
        pick = {nearest: near[nearest]}
    else:
        # an empty dict counts as False: "danger or eyes.spots" = danger if there is any, else everyone
        pick = danger or eyes.spots
    eyes.target = lockon.choose_target(shelf, pick, eyes.you, game.rules)
    eyes.lying = (
        eyes.target is not None and read_kind(shelf, eyes.target, 0, 0x10) in KNOCKED
    )
    # a real door between you and the target (the fake ones are walls already)
    eyes.behind_door = eyes.target is not None and any(
        crosses_box(eyes.you, eyes.spots[eyes.target], box)
        for box in eyes.doors
        if list(box) not in game.fake_doors.get(eyes.scene, [])
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
    eyes.arrow = None if eyes.still else game.watch.update(now)
