# https://github.com/Cl1ngz/HotlineMiamibot
# radar.py - a live mini-map of the level, drawn straight from game memory,
# sitting in the corner of your screen on top of the game (clicks go through it).
#
#   red circle     = you            (the "player" address)
#   green circle   = your crosshair (the "crosshair" address)
#   orange squares = enemies you can see   (the "enemy" rules from obj_kinds.py)
#   orange outline = enemies behind a wall (the lock-on ignores these)
#   grey lines     = walls, the way the bot understands them (walls.py)
#   grey dots      = objects that haven't moved since the level started (walls, doors, guns on the floor)
#   yellow dots    = objects that moved (thrown weapons, opened doors, stuff glued to you...)
import math
import signal
import sys

import cairo
import gi

from enemies import find_aim, find_me

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from enemies import is_enemy, load_rules  # noqa: E402
from memory import read_double  # noqa: E402
from memory import attach, follow, load_address, table_records
from walls import can_see, find_walls, wall_lines  # noqa: E402

SIZE = 400  # radar size on screen, in pixels
MARGIN = 15  # empty space inside the radar's edge
TEXT = 22  # strip at the bottom for the numbers

mem, regions, static_regions = attach()
PLAYER = load_address("player")
CROSSHAIR = load_address("crosshair")
Y_OFFSET = load_address("y_offset")

# where every object was on the first frame of this level
start_positions = set()
# [min_x, min_y, max_x, max_y]: how big the level is (only ever grows)
bounds = None


rules = load_rules()  # what counts as an enemy (made by obj_kinds.py)


def read_xy(path):
    """Follow a saved path and read X, Y (Y sits Y_OFFSET bytes after X)."""
    x_addr = follow(mem, path)
    x, y = read_double(mem, x_addr), read_double(mem, x_addr + Y_OFFSET)
    if not (0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000):
        raise OSError("garbage position")  # menu / loading screen
    return x, y


def on_draw(widget, cr):
    global bounds, start_positions

    # see-through dark background
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0.75)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.select_font_face("monospace")
    cr.set_font_size(13)

    try:
        # you = read_xy(PLAYER)
        # aim = read_xy(CROSSHAIR)
        you = find_me(mem)
        aim = find_aim(mem, you)
        objects = table_records(mem)  # {record: (x, y)}
        if you is None:
            raise OSError("no playerfound")
        if aim is None:
            raise OSError("no crosshair found")
    except OSError as err:
        bounds, start_positions = None, set()  # forget the old level
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(MARGIN, MARGIN + 13)
        cr.show_text(str(err))
        return

    # keep only objects near you (drops the odd garbage value far away)
    objects = {
        r: (x, y)
        for r, (x, y) in objects.items()
        if abs(x - you[0]) < 1500 and abs(y - you[1]) < 1500
    }

    # first frame of a level: remember where everything is, and how big the level is
    if bounds is None:
        start_positions = set(objects.values())
        bounds = [you[0], you[1], you[0], you[1]]
    for x, y in list(objects.values()) + [you, aim]:
        bounds = [
            min(bounds[0], x),
            min(bounds[1], y),
            max(bounds[2], x),
            max(bounds[3], y),
        ]

    # game units -> radar pixels: squeeze the level into the space we have
    min_x, min_y, max_x, max_y = bounds
    width = widget.get_allocated_width() - 2 * MARGIN
    height = widget.get_allocated_height() - 2 * MARGIN - TEXT
    zoom = min(width / max(max_x - min_x, 1), height / max(max_y - min_y, 1))

    def to_radar(x, y):
        return MARGIN + (x - min_x) * zoom, MARGIN + (y - min_y) * zoom

    # walls: grey lines
    lines = wall_lines(find_walls(mem, objects, rules)) if rules else []
    cr.set_source_rgb(0.45, 0.45, 0.5)
    cr.set_line_width(2)
    for (x1, y1), (x2, y2) in lines:
        cr.move_to(*to_radar(x1, y1))
        cr.line_to(*to_radar(x2, y2))
    cr.stroke()

    # every object: grey if it's still where it started, yellow if it moved
    enemies = []
    for record, (x, y) in objects.items():
        if is_enemy(mem, record, rules):
            enemies.append((x, y))  # drawn last, so they're on top
            continue
        sx, sy = to_radar(x, y)
        if (x, y) in start_positions:
            cr.set_source_rgb(0.55, 0.55, 0.55)
        else:
            cr.set_source_rgb(1, 0.85, 0.1)
        cr.rectangle(sx - 2, sy - 2, 4, 4)
        cr.fill()

    # enemies: orange squares, just an outline if there's a wall between you and them
    cr.set_source_rgb(1, 0.45, 0)
    cr.set_line_width(1.5)
    for x, y in enemies:
        sx, sy = to_radar(x, y)
        cr.rectangle(sx - 4, sy - 4, 8, 8)
        if can_see(you, (x, y), lines):
            cr.fill()
        else:
            cr.stroke()

    # you: red circle
    sx, sy = to_radar(*you)
    cr.set_source_rgb(1, 0.15, 0.15)
    cr.set_line_width(3)
    cr.arc(sx, sy, 9, 0, 2 * math.pi)
    cr.stroke()

    # crosshair: green circle, plus a thin line from you to it
    ax, ay = to_radar(*aim)
    cr.set_source_rgb(0.2, 1, 0.2)
    cr.set_line_width(1)
    cr.move_to(sx, sy)
    cr.line_to(ax, ay)
    cr.stroke()
    cr.set_line_width(2)
    cr.arc(ax, ay, 6, 0, 2 * math.pi)
    cr.stroke()

    # the raw numbers, so you can compare with hmbot.py
    cr.set_source_rgb(1, 1, 1)
    cr.move_to(MARGIN, widget.get_allocated_height() - 8)
    cr.show_text(
        f"you {you[0]:4.0f},{you[1]:4.0f}  aim {aim[0]:4.0f},{aim[1]:4.0f}  enemies {len(enemies)}"
    )


def tick():
    area.queue_draw()  # "please redraw" -> GTK calls on_draw
    return True  # keep the timer running


def reload_rules():
    global rules
    rules = (
        load_rules()
    )  # so a new obj_kinds.py guess shows up without restarting the radar
    return True


signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C quits

win = Gtk.Window(title="HMBot radar")
win.set_default_size(SIZE, SIZE + TEXT)

if "--window" not in sys.argv:
    # put it on Hyprland's top layer, in the bottom-right corner, over the fullscreen game
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell

    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_anchor(
        win, GtkLayerShell.Edge.BOTTOM, True
    )  # change BOTTOM/RIGHT to
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, True)  # TOP/LEFT to move it
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.BOTTOM, 20)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.RIGHT, 20)
    GtkLayerShell.set_keyboard_mode(
        win, GtkLayerShell.KeyboardMode.NONE
    )  # never steal the keyboard

win.set_size_request(SIZE, SIZE + TEXT)
win.set_app_paintable(True)
visual = win.get_screen().get_rgba_visual()  # allows see-through pixels
if visual:
    win.set_visual(visual)

area = Gtk.DrawingArea()
area.connect("draw", on_draw)
win.add(area)
win.connect("destroy", Gtk.main_quit)
GLib.timeout_add(33, tick)  # redraw ~30 times per second
GLib.timeout_add(1000, reload_rules)  # re-read addresses.json once per second
win.show_all()
if "--window" not in sys.argv:
    win.input_shape_combine_region(
        cairo.Region()
    )  # empty click area = clicks go to the game
Gtk.main()
