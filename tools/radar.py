# https://github.com/Cl1ngz/HotlineMiamibot
# tools/radar.py - a live mini-map of the floor, drawn straight from the game's memory, in the corner of your
# screen on top of the game (clicks go through it). It sees the floor the same way the bot does: one Shelf photo
# per frame, the walls and the enemies from the whole shelf.
#
#   top strip        = what the bot is doing right now (hmbot.py writes it to NOW_FILE)
#   red circle       = you
#   green circle     = your crosshair (not every scene has one)
#   orange square    = an enemy you can see, an outline = behind a wall, an orange X = knocked out
#   grey lines       = walls, the way the bot understands them
#   + plus signs     = weapons on the floor (blue melee, pink gun, white throw, grey not named yet)
#   yellow diamond   = the level's goal (the briefcase...)
#   G green          = stairs with GO! on          B grey = the stairs you came by (they lead back)
#   C cyan           = the car, ready to go
#   red triangle     = what the red arrow points at
#   cyan cross, dots = the bot's goal and the way it walks there   (thin cyan line = its target)
#   grey / yellow dots = things still where the floor started / things that moved
#
#   python -m tools.radar             on Hyprland's top layer, in the bottom-right corner
#   python -m tools.radar --window    in a normal window
import json
import math
import signal
import sys
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from core.enemies import find_aim, find_me_card, is_enemy, load_rules  # noqa: E402
from core.memory import (
    X_OFF,
    Y_OFF,
    attach,
    read_double,  # noqa: E402
    read_kind,
    table_cards,
)
from core.shelf import Shelf  # noqa: E402
from core.stairs import find_car, find_stairs  # noqa: E402
from core.walls import can_see, real_walls, wall_lines  # noqa: E402
from core.weapons import find_goals, find_weapons, load_names  # noqa: E402

SIZE = 420  # the map part, in pixels
MARGIN = 15  # empty space inside the radar's edge
TOP = 24  # strip at the top: what the bot is doing
TEXT = 22  # strip at the bottom: the numbers
# what the bot is doing - hmbot.py writes it here (the same name is in hmbot.py)
NOW_FILE = "/tmp/hmbot_now.json"
# older than this = the bot isn't running (or is stuck)
BOT_OLD = 1.0
SCAN_EVERY = 0.25  # the whole shelf (enemies, weapons, stairs, the car) this often - like the bot
WALLS_EVERY = 2.0  # walls never move - read them this often
NEW_FLOOR_JUMP = (
    100  # you moved this far between two frames: a new floor - start the map over
)
KNOCKED = (0x16, 0x12B)
# weapon kind -> colour (r, g, b from 0 to 1); weapons nobody named yet get GREY
KIND_COLOURS = {
    "melee": (0.3, 0.75, 1.0),  # light blue - walk up and hit
    "gun": (1.0, 0.3, 0.85),  # pink - shoots from far, has ammo
    "throw": (0.95, 0.95, 0.95),  # white - throw it and your hands are empty
}
GREY = (0.8, 0.8, 0.8)

names = load_names()  # weapon frame -> {"name": "Lead Pipe", "kind": "melee"}
rules = load_rules()  # what counts as an enemy (tools/enemy_tool.py)
mem, regions, static_regions = attach()

# kept between frames
floor = {
    "bounds": None,  # [min_x, min_y, max_x, max_y] of the floor (only ever grows)
    "start": set(),  # where the table's things stood on the first frame of this floor
    "you": None,  # you, last frame
    "walls": [],  # (xy, box) of every wall piece
    "lines": [],  # the wall lines (what you can't see through)
    "walls_at": 0,  # when the walls were read
    "scan_at": 0,  # when the whole shelf was looked at
    "enemy_cards": set(),
    "weapons": [],
    "goals": [],
    "stairs": None,
    "car": None,
}


def new_floor():
    floor.update(
        bounds=None,
        start=set(),
        walls=[],
        lines=[],
        walls_at=0,
        scan_at=0,
        enemy_cards=set(),
    )


def read_bot():
    """What the bot wrote last (a dict), or None if it isn't running."""
    try:
        with open(NOW_FILE) as f:
            bot = json.load(f)
    except (OSError, ValueError):
        return None
    if time.time() - bot.get("time", 0) > BOT_OLD:
        return None
    return bot


def look():
    """Everything the radar draws, from one photo of the game's memory. Raises OSError (no player...).
    The slow part (the whole shelf) only every SCAN_EVERY, like the bot - the radar mustn't slow the bot down.
    """
    shelf = Shelf(mem)
    records = shelf.records
    if not records:
        raise OSError("nothing on the floor (menu / loading)")
    me = find_me_card(shelf)
    if me is None:
        raise OSError("no player found")
    you = (read_double(shelf, me + X_OFF), read_double(shelf, me + Y_OFF))
    if floor["you"] is not None and math.dist(you, floor["you"]) > NEW_FLOOR_JUMP:
        new_floor()
    floor["you"] = you

    now = time.monotonic()
    if now - floor["walls_at"] > WALLS_EVERY:
        floor["walls"] = real_walls(shelf, records, shelf.cards)
        floor["lines"] = wall_lines([xy for xy, box in floor["walls"]])
        floor["walls_at"] = now
    if now - floor["scan_at"] > SCAN_EVERY:
        floor["enemy_cards"] = {
            card for card in shelf.cards if is_enemy(shelf, card, rules)
        }
        floor["weapons"] = find_weapons(shelf, shelf.cards)
        floor["goals"] = find_goals(shelf, shelf.cards)
        floor["stairs"] = find_stairs(shelf, records)
        floor["car"] = find_car(shelf, records, shelf.cards)
        floor["scan_at"] = now
    # every frame: new enemies in the table (one quick read), and where every enemy is now
    for card in table_cards(shelf) - floor["enemy_cards"]:
        if is_enemy(shelf, card, rules):
            floor["enemy_cards"].add(card)
    enemies = []
    for card in list(floor["enemy_cards"]):
        if not is_enemy(
            shelf, card, rules
        ):  # died / got up: gone from the list until the next scan finds him
            floor["enemy_cards"].discard(card)
            continue
        try:
            xy = (read_double(shelf, card + X_OFF), read_double(shelf, card + Y_OFF))
            enemies.append((xy, read_kind(shelf, card, 0, 0x10) in KNOCKED))
        except OSError:
            continue

    try:
        aim = find_aim(shelf)
    except OSError:
        aim = None
    # the table's things near you (far away = junk values)
    things = [
        xy
        for xy in records.values()
        if abs(xy[0] - you[0]) < 1500 and abs(xy[1] - you[1]) < 1500
    ]
    return {
        "you": you,
        "aim": aim,
        "enemies": enemies,
        "lines": floor["lines"],
        "walls": [xy for xy, box in floor["walls"]],
        "weapons": floor["weapons"],
        "goals": floor["goals"],
        "stairs": floor["stairs"],
        "car": floor["car"],
        "things": things,
    }


def grow_bounds(points):
    for x, y in points:
        if floor["bounds"] is None:
            floor["bounds"] = [x, y, x, y]
        b = floor["bounds"]
        floor["bounds"] = [min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)]


def text(cr, x, y, words, colour=(1, 1, 1), size=13):
    cr.set_source_rgb(*colour)
    cr.set_font_size(size)
    cr.move_to(x, y)
    cr.show_text(words)


def on_draw(widget, cr):
    # see-through dark background
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0.75)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.select_font_face("monospace")
    width = widget.get_allocated_width()
    height = widget.get_allocated_height()

    # the top strip: what the bot is doing
    bot = read_bot()
    if bot is None:
        text(cr, MARGIN, 17, "bot: not running", (0.6, 0.6, 0.6), 12)
    else:
        text(cr, MARGIN, 17, "bot: " + bot.get("text", ""), (0.4, 1, 1), 12)

    try:
        seen = look()
    except OSError as err:
        new_floor()
        text(cr, MARGIN, TOP + 20, str(err))
        return

    you = seen["you"]
    grow_bounds(seen["walls"] + [you] + [xy for xy, knocked in seen["enemies"]])
    if not floor["start"]:
        floor["start"] = set(seen["things"])

    # game units -> radar pixels: squeeze the floor into the space we have
    min_x, min_y, max_x, max_y = floor["bounds"]
    room_w = width - 2 * MARGIN
    room_h = height - 2 * MARGIN - TOP - TEXT
    zoom = min(room_w / max(max_x - min_x, 1), room_h / max(max_y - min_y, 1))

    def to_radar(xy):
        return MARGIN + (xy[0] - min_x) * zoom, TOP + MARGIN + (xy[1] - min_y) * zoom

    # walls: grey lines
    cr.set_source_rgb(0.45, 0.45, 0.5)
    cr.set_line_width(2)
    for a, b in seen["lines"]:
        cr.move_to(*to_radar(a))
        cr.line_to(*to_radar(b))
    cr.stroke()

    # the table's things: grey = still where the floor started, yellow = moved
    for xy in seen["things"]:
        if xy == you:
            continue
        sx, sy = to_radar(xy)
        if xy in floor["start"]:
            cr.set_source_rgb(0.4, 0.4, 0.4)
        else:
            cr.set_source_rgb(1, 0.85, 0.1)
        cr.rectangle(sx - 1.5, sy - 1.5, 3, 3)
        cr.fill()

    # weapons on the floor: plus signs coloured by kind
    cr.set_line_width(1.5)
    for x, y, frame in seen["weapons"]:
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            continue  # junk outside the floor
        cr.set_source_rgb(*KIND_COLOURS.get(names.get(frame, {}).get("kind"), GREY))
        sx, sy = to_radar((x, y))
        cr.move_to(sx - 3, sy)
        cr.line_to(sx + 3, sy)
        cr.move_to(sx, sy - 3)
        cr.line_to(sx, sy + 3)
        cr.stroke()

    # the level's goal (the briefcase): yellow diamond
    cr.set_source_rgb(1, 0.9, 0.2)
    for xy in seen["goals"]:
        sx, sy = to_radar(xy)
        cr.move_to(sx, sy - 6)
        cr.line_to(sx + 6, sy)
        cr.line_to(sx, sy + 6)
        cr.line_to(sx - 6, sy)
        cr.close_path()
        cr.fill()

    # stairs with GO!: G (or B in grey: the ones you came by - the bot tells us which)
    came_by = bot.get("came_by") if bot else None
    if seen["stairs"] is not None:
        sx, sy = to_radar(seen["stairs"])
        back = came_by is not None and math.dist(came_by, seen["stairs"]) < 1
        text(
            cr,
            sx - 4,
            sy + 5,
            "B" if back else "G",
            (0.6, 0.6, 0.6) if back else (0.2, 1, 0.3),
            15,
        )
    # the car, ready: C
    if seen["car"] is not None:
        sx, sy = to_radar(seen["car"])
        text(cr, sx - 4, sy + 5, "C", (0.2, 0.9, 1), 15)

    # the red arrow (the bot found it): a red triangle pointing down at the thing
    arrow = bot.get("arrow") if bot else None
    if arrow is not None:
        sx, sy = to_radar(arrow)
        cr.set_source_rgb(1, 0.15, 0.2)
        cr.move_to(sx - 6, sy - 12)
        cr.line_to(sx + 6, sy - 12)
        cr.line_to(sx, sy - 2)
        cr.close_path()
        cr.fill()

    # enemies: orange squares (an outline behind a wall), an X when knocked out
    cr.set_source_rgb(1, 0.45, 0)
    cr.set_line_width(1.5)
    for xy, knocked in seen["enemies"]:
        sx, sy = to_radar(xy)
        if knocked:
            cr.move_to(sx - 4, sy - 4)
            cr.line_to(sx + 4, sy + 4)
            cr.move_to(sx + 4, sy - 4)
            cr.line_to(sx - 4, sy + 4)
            cr.stroke()
            continue
        cr.rectangle(sx - 4, sy - 4, 8, 8)
        if can_see(you, xy, seen["lines"]):
            cr.fill()
        else:
            cr.stroke()

    # the bot: its way (dots), its goal (cross), a thin line to its target
    if bot is not None:
        cr.set_source_rgb(0.2, 0.9, 1)
        for xy in bot.get("path") or []:
            sx, sy = to_radar(xy)
            cr.rectangle(sx - 1, sy - 1, 2, 2)
        cr.fill()
        if bot.get("goal") is not None:
            sx, sy = to_radar(bot["goal"])
            cr.set_line_width(2)
            cr.move_to(sx - 6, sy - 6)
            cr.line_to(sx + 6, sy + 6)
            cr.move_to(sx + 6, sy - 6)
            cr.line_to(sx - 6, sy + 6)
            cr.stroke()
        if bot.get("target") is not None:
            cr.set_line_width(1)
            cr.move_to(*to_radar(you))
            cr.line_to(*to_radar(bot["target"]))
            cr.stroke()

    # you: red circle
    sx, sy = to_radar(you)
    cr.set_source_rgb(1, 0.15, 0.15)
    cr.set_line_width(3)
    cr.arc(sx, sy, 8, 0, 2 * math.pi)
    cr.stroke()

    # crosshair: green circle and a thin line from you to it
    aim = seen["aim"]
    if aim is not None:
        ax, ay = to_radar(aim)
        cr.set_source_rgb(0.2, 1, 0.2)
        cr.set_line_width(1)
        cr.move_to(sx, sy)
        cr.line_to(ax, ay)
        cr.stroke()
        cr.set_line_width(2)
        cr.arc(ax, ay, 5, 0, 2 * math.pi)
        cr.stroke()

    # the raw numbers, to compare with the bot / the blackbox
    standing = sum(1 for xy, knocked in seen["enemies"] if not knocked)
    aim_text = f"{aim[0]:4.0f},{aim[1]:4.0f}" if aim else "   -"
    text(
        cr,
        MARGIN,
        height - 8,
        f"you {you[0]:4.0f},{you[1]:4.0f}  aim {aim_text}  enemies {standing}"
        f"+{len(seen['enemies']) - standing} down  walls {len(seen['walls'])}",
        size=12,
    )


def tick():
    area.queue_draw()  # "please redraw" -> GTK calls on_draw
    return True  # keep the timer running


def reload_rules():
    global rules
    rules = (
        load_rules()
    )  # a new rule from tools/enemy_tool.py shows up without restarting the radar
    return True


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C quits

    win = Gtk.Window(title="HMBot radar")
    win.set_default_size(SIZE, SIZE + TOP + TEXT)

    if "--window" not in sys.argv:
        # put it on Hyprland's top layer, in the bottom-right corner, over the fullscreen game
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell

        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(
            win, GtkLayerShell.Edge.BOTTOM, True
        )  # change BOTTOM / RIGHT
        GtkLayerShell.set_anchor(
            win, GtkLayerShell.Edge.RIGHT, True
        )  # to TOP / LEFT to move it
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.BOTTOM, 20)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.RIGHT, 20)
        GtkLayerShell.set_keyboard_mode(
            win, GtkLayerShell.KeyboardMode.NONE
        )  # never steal the keyboard

    win.set_size_request(SIZE, SIZE + TOP + TEXT)
    win.set_app_paintable(True)
    visual = win.get_screen().get_rgba_visual()  # allows see-through pixels
    if visual:
        win.set_visual(visual)

    area = Gtk.DrawingArea()
    area.connect("draw", on_draw)
    win.add(area)
    win.connect("destroy", Gtk.main_quit)
    GLib.timeout_add(33, tick)  # redraw ~30 times per second
    GLib.timeout_add(1000, reload_rules)  # re-read the enemy rules once per second
    win.show_all()
    if "--window" not in sys.argv:
        win.input_shape_combine_region(
            cairo.Region()
        )  # empty click area = clicks go to the game
    Gtk.main()
