# https://github.com/Cl1ngz/HotlineMiamibot
# tools/blackbox.py - a flight recorder of the game, as TEXT: what you (or hmbot) did, saw and pressed
#
# It only READS memory, it never presses anything - run it next to hmbot (or while you play).
# Many times a second it writes down a "sample":
#   you      where you are, where your character looks, what's in your hand (+0xA0)
#   inputs   the keys and mouse buttons held RIGHT NOW in the game (W A S D SPACE R, LMB RMB) - also the bot's
#   enemies  every living enemy (from the whole shelf - also the ones the table misses): layer, +0x10, +0xB4,
#            can you see him, "<- LOOK" = the one your character looks at   (--bodies: the bodies too)
#   near     (--near 60) EVERY card close to you, any kind (but walls) - for hunting new things
# and between the samples it writes EVENTS (lines with !!): an enemy appeared / died, your hand changed,
# GO! went on, the car is ready, a goal or a weapon near you disappeared, the map changed, you got stuck,
# you were hidden (sitting on an enemy / dead / loading), you died, you came back on a new floor.
#
# It keeps the last --keep seconds and saves them to blackbox/<date>_<why>.txt when something happens:
#   death   you died: your dead card is there, and you're hidden longer than any execution (2 s)
#           or R was pressed meanwhile (a quick restart) - saved 1 s later
#   stuck   you hold walking keys but don't move for 1.5 s
#   key     you press F9 in the game - "save what just happened"
#   floor   you came back on a new floor
#   Ctrl+C  always
#
#   python -m tools.blackbox                       the usual: you, inputs, enemies + events, last 10 s
#   python -m tools.blackbox --near 60             ...plus every card within 60 of you
#   python -m tools.blackbox --what you,inputs     only these parts (you, inputs, enemies, items, map, near)
#   python -m tools.blackbox --events              only the events (+ one line about you every second) - long runs
#   python -m tools.blackbox --changes             a sample only when it's different from the last one (shorter)
#   python -m tools.blackbox --bodies              the dead bodies in every sample too (a body that's still orange?)
#   python -m tools.blackbox --full                everything into ONE file until Ctrl+C (no ring, nothing lost)
#   python -m tools.blackbox --keep 20 --rate 60   more history / more samples per second
#   python -m tools.blackbox --range 400           enemies further away too
#   python -m tools.blackbox --save-on death,key   save only on these (death, stuck, key, floor)
import argparse
import math
import os
import subprocess
import time
from collections import deque
from datetime import datetime

from core.enemies import find_me_card, is_enemy, load_rules, matches
from core.hands import BUTTON, KEY_A, KEY_D, KEY_R, KEY_S, KEY_SPACE, KEY_W, KEYBOARD, LOOK_X, LOOK_Y, follow
from core.memory import X_OFF, Y_OFF, attach, read_bytes, read_double, read_kind, read_u32, table_cards
from core.path import blocked_cells
from core.shelf import Shelf
from core.stairs import find_car, find_stairs
from core.walls import can_see, fake_door_boxes, real_walls, wall_lines
from core.weapons import find_goals, find_weapons, load_names

SECTIONS = ("you", "inputs", "enemies", "items", "map", "near")
TRIGGERS = ("death", "stuck", "key", "floor")
parser = argparse.ArgumentParser(description="a text flight recorder of the game (only reads memory)")
parser.add_argument("--what", default="you,inputs,enemies,items,map", help=f"parts to record: {','.join(SECTIONS)}")
parser.add_argument("--near", type=float, metavar="RANGE", help="also every card (but walls) this close to you")
parser.add_argument("--range", type=float, default=250, help="enemies this close to you (default 250)")
parser.add_argument("--rate", type=float, default=30, help="samples per second (default 30)")
parser.add_argument("--keep", type=float, default=10, help="seconds of history in a saved file (default 10)")
parser.add_argument("--save-on", default="death,stuck,key,floor", help=f"when to save: {','.join(TRIGGERS)}")
parser.add_argument("--events", action="store_true", help="only events + one line about you every second")
parser.add_argument("--changes", action="store_true", help="a sample only when it's different from the last one")
parser.add_argument("--bodies", action="store_true", help="bodies (cards matching a rule but dead) in samples too")
parser.add_argument("--full", action="store_true", help="record everything into one file until Ctrl+C")
parser.add_argument("--out", default="blackbox", help="folder for the files (default blackbox)")
args = parser.parse_args()
what = set(args.what.split(","))
if args.near:
    what.add("near")
save_on = set(args.save_on.split(","))
if what - set(SECTIONS) or save_on - set(TRIGGERS):
    parser.error(f"unknown part/trigger - parts: {','.join(SECTIONS)}  triggers: {','.join(TRIGGERS)}")

SCAN_EVERY = 0.25  # seconds between the slow looks (enemy cards, items, near)
MAP_EVERY = 2.0  # seconds between looks at the walls (they don't move)
KEY_F9 = 0x43  # DirectInput's number for F9 - the "save now" key
KEYS = {KEY_W: "W", KEY_A: "A", KEY_S: "S", KEY_D: "D", KEY_SPACE: "SPACE", KEY_R: "R"}
WALKING = {"W", "A", "S", "D"}
ME_LAYER, AIM_LAYER, WALL_LAYER = 0x2C, 0xAF, 0x9
LOOK_NEAR = 8  # the look is this close to an enemy -> your character looks at him
ITEM_NEAR = 60  # weapons appearing / disappearing this close to you are events (far ones are noise)
STUCK_FOR, STUCK_MOVE = 1.5, 2  # holding walking keys and moving less than STUCK_MOVE in STUCK_FOR s = stuck
GONE_AFTER = 3.0  # hidden longer than this = not just sitting on an enemy
# an execution (SPACE) hides you too - for 1.0 s with a weapon, 1.3 s with fists - and your old card even
# looks dead meanwhile.
# So only hidden LONGER than this can be a death
DEATH_AFTER = 2.0
SPACE_BEFORE = 0.5  # hidden this soon after SPACE = probably an execution
AFTER = {"death": 1.0, "stuck": 0.5, "key": 0.0, "floor": 0.0}  # wait this long before saving (show the aftermath)

# the game's memory. Every sample takes a PHOTO of it (core/shelf.py) and reads only through the photo:
# ~100 kernel reads a scan instead of ~19 000 - so the blackbox doesn't slow hmbot down any more
game, regions, static_regions = attach()
mem = game
rules = load_rules()
names = load_names()
started = time.monotonic()


def notify(text):
    """A pop-up too, because you're looking at the game, not the terminal."""
    print(text)
    try:
        subprocess.run(["notify-send", "-t", "2000", "HMBot blackbox", text])
    except OSError:
        pass


def header(why):
    return (
        f"# tools/blackbox.py - {why}\n"
        f"# {datetime.now():%Y-%m-%d %H:%M:%S}   parts: {','.join(sorted(what))}   rate {args.rate:g}/s"
        f"   range {args.range:g}" + (f"   near {args.near:g}" if args.near else "") + "\n"
        "# t = seconds (in a saved file: before the save)   !! = event\n\n"
    )


class Recorder:
    """Keeps the lines: a ring of the last --keep seconds, or (--full) straight into one file."""

    def __init__(self):
        self.ring = deque()  # (time, text) - text can have more lines: the sample's details
        self.file = None
        if args.full:
            self.file = open(self.new_name("full"), "w")
            self.file.write(header("full recording"))

    def new_name(self, why):
        os.makedirs(args.out, exist_ok=True)
        name = os.path.join(args.out, f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{why}")
        path, n = name + ".txt", 2
        while os.path.exists(path):  # two saves in the same second: don't write over the first one
            path, n = f"{name}_{n}.txt", n + 1
        return path

    @staticmethod
    def lines(t, text):
        first, *rest = text.split("\n")
        return [f"{t}  {first}"] + [f"{' ' * len(t)}    {line}" for line in rest]

    def add(self, now, text):
        if self.file:
            self.file.write("\n".join(self.lines(f"t={now - started:8.2f}s", text)) + "\n")
            return
        self.ring.append((now, text))
        while now - self.ring[0][0] > args.keep:
            self.ring.popleft()

    def save(self, now, why, state):
        if self.file:
            self.add(now, f"!! ---- {why} (a saved moment) ----")
            self.file.flush()
            return
        if not self.ring:
            return
        name = self.new_name(why)
        with open(name, "w") as f:
            f.write(header(f"saved because: {why}"))
            for moment, text in self.ring:
                f.write("\n".join(self.lines(f"t={moment - now:+7.2f}s", text)) + "\n")
            f.write("\n# when it was saved:\n" + "".join(f"#   {line}\n" for line in state))
        self.ring.clear()
        notify(f"saved {name}")

    def close(self, now, state):
        if self.file:
            self.file.write("\n# at the end:\n" + "".join(f"#   {line}\n" for line in state))
            self.file.close()
            notify(f"saved {self.file.name}")
        else:
            self.save(now, "ctrl-c", state)


def xy_of(card):
    return read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)


def spot(xy):
    return "-" if xy is None else f"({xy[0]:4.0f},{xy[1]:4.0f})"


def read_look():
    try:
        return read_double(mem, follow(mem, LOOK_X)), read_double(mem, follow(mem, LOOK_Y))
    except OSError:
        return None


def read_inputs():
    """(names of everything held, is F9 held) - straight from DirectInput's rows in the game."""
    try:
        row = read_bytes(mem, 256, follow(mem, KEYBOARD))
        buttons = read_bytes(mem, 2, follow(mem, BUTTON))
        held = {name for key, name in KEYS.items() if row[key] & 0x80}
        if buttons[0] & 0x80:
            held.add("LMB")
        if buttons[1] & 0x80:
            held.add("RMB")
        return held, bool(row[KEY_F9] & 0x80)
    except (OSError, IndexError):  # IndexError: the game is gone (an empty read)
        return set(), False


def weapon_name(frame):
    return "phantom" if frame == 0 else names.get(frame, {}).get("name", f"frame {frame}")


def describe(card, you, look, lines, table):
    """One line about a card that matches an enemy rule, or None if it's too far / gone."""
    try:
        xy = xy_of(card)
        far = math.dist(xy, you)
        if far > args.range:
            return None
        layer, state = read_kind(mem, card, 0, 0x14), read_kind(mem, card, 0, 0x10)
        done = read_u32(mem, card + 0xB4)
    except OSError:
        return None
    rule = next((i for i, r in enumerate(rules) if matches(mem, card, *r)), None)
    who = "ENEMY" if is_enemy(mem, card, rules) else "body "
    see = "yes" if can_see(you, xy, lines) else "no "
    aimed = "  <- LOOK" if look is not None and math.dist(look, xy) < LOOK_NEAR else ""
    return (
        f"{who} {card:#x} {spot(xy)} far {far:3.0f}  rule {rule}  layer {layer:#x}  +0x10 {state:#x}"
        f"  +0xB4 {done}  {'table' if card in table else 'SHELF'}  see={see}{aimed}"
    )


rec = Recorder()
records, candidates, lines, near_text = {}, [], [], []
items = {"stairs": None, "car": None, "goals": set(), "weapons": set(), "map": None}
alive = {}  # enemy card -> where he was, last sample
hand = None
you = last_you = None
hidden_since, gone_told, dead_told = None, False, False
dead_seen = False  # while hidden: your dead-looking card was there (an execution shows it too!)
r_hidden = False  # while hidden: R was pressed (restart after a death)
still_xy, still_since, stuck_told = None, 0, False
f9_before = False
last_space = -math.inf  # when SPACE was held last
pending = None  # (when, why) - a save waiting for its aftermath
next_scan = next_map = next_beat = next_dead = 0
last_sample = None  # --changes
print(f"recording ({','.join(sorted(what))})... F9 in the game = save the last {args.keep:g} s, Ctrl+C = end")
try:
    while True:
        now = time.monotonic()
        events = []
        mem = Shelf(game)  # this sample's photo - every read below (and in the functions above) goes through it

        # --- the slow looks ---
        try:
            if now >= next_scan:
                records = mem.records
                shelf = mem.cards
                candidates = [c for c in shelf if any(matches(mem, c, *r) for r in rules)]
                if "items" in what:
                    stairs, car = find_stairs(mem, records), find_car(mem, records, shelf)
                    if stairs != items["stairs"]:
                        events.append(f"GO! on the stairs at {spot(stairs)}" if stairs else "the stairs went off")
                    if car != items["car"]:
                        events.append(f"the car is READY at {spot(car)}" if car else "the car is not ready")
                    goals = {(round(x), round(y)) for x, y in find_goals(mem, shelf)}
                    events += [f"a goal appeared at {spot(g)}" for g in goals - items["goals"]]
                    events += [f"a goal is gone from {spot(g)} (taken?)" for g in items["goals"] - goals]
                    weapons = {(round(x), round(y), frame) for x, y, frame in find_weapons(mem, shelf) if frame}
                    if you is not None:
                        for x, y, frame in weapons ^ items["weapons"]:
                            if math.dist((x, y), you) < ITEM_NEAR:
                                verb = "lies" if (x, y, frame) in weapons else "is gone"
                                events.append(f"{weapon_name(frame)} {verb} at ({x},{y}) near you")
                    items.update(stairs=stairs, car=car, goals=goals, weapons=weapons)
                if "near" in what and you is not None:
                    near_text = []
                    for card in shelf:
                        try:
                            xy = xy_of(card)
                            layer = read_kind(mem, card, 0, 0x14)
                            if layer in (WALL_LAYER, ME_LAYER, AIM_LAYER) or math.dist(xy, you) > args.near:
                                continue
                            near_text.append(
                                f"near {card:#x} {spot(xy)} far {math.dist(xy, you):3.0f}  layer {layer:#x}"
                                f"  +0x10 {read_kind(mem, card, 0, 0x10):#x}  picture {read_kind(mem, card, 1, 0x10):#x}"
                                f"  {'table' if card in records else 'SHELF'}"
                            )
                        except OSError:
                            continue
                next_scan = now + SCAN_EVERY
            if now >= next_map:
                walls = real_walls(mem, records, mem.cards) if records else []  # every wall ONCE: (xy, box) pairs
                lines = wall_lines([xy for xy, box in walls])
                if "map" in what and records:
                    boxes = [box for xy, box in walls] + fake_door_boxes(mem, records)
                    if len(boxes) != items["map"]:
                        events.append(f"map: {len(boxes)} boxes, {len(blocked_cells(boxes))} blocked cells")
                        items["map"] = len(boxes)
                next_map = now + MAP_EVERY
            # table cards that aren't candidates yet: new ones AND ones that just started matching a rule
            # (a sitting enemy stands up) - check them NOW, like hmbot does, instead of at the next scan
            known = set(candidates)
            for card in table_cards(mem) - known:
                if any(matches(mem, card, *r) for r in rules):
                    candidates.append(card)
            me = find_me_card(mem)
        except OSError:
            me = None  # loading / a new floor: memory is moving

        held, f9 = read_inputs()
        if f9 and not f9_before:
            events.append("F9 pressed - saving")
            if "key" in save_on:
                pending = (now, "f9")
        f9_before = f9
        if "SPACE" in held:
            last_space = now

        # --- you ---
        sample = None
        if me is None:
            if "inputs" in what:
                sample = f"(hidden)  keys {' '.join(sorted(held)) or '-'}"  # e.g. the bot hitting while sitting on him
            if hidden_since is None:
                hidden_since = now
                if now - last_space < SPACE_BEFORE:
                    events.append("you're hidden right after SPACE - an execution?")
                else:
                    events.append("you're hidden (dead / loading / sitting on an enemy)")
            if "R" in held:
                r_hidden = True
            if not dead_seen and last_you is not None and now >= next_dead:
                next_dead = now + SCAN_EVERY
                # your dead card: layer 0x2C with the death sign, where you were
                for card in mem.cards if records else []:
                    try:
                        if read_kind(mem, card, 0, 0x14) == ME_LAYER and read_u32(mem, card + 0xB4) == 1:
                            if math.dist(xy_of(card), last_you) < 40:
                                dead_seen = True
                                break
                    except OSError:
                        continue
            # an execution shows that card too - so a death only when it lasts too long, or R restarts the level
            if dead_seen and not dead_told and (now - hidden_since > DEATH_AFTER or r_hidden):
                events.append("YOU DIED" + (" (R pressed)" if r_hidden else ""))
                dead_told = True
                if "death" in save_on:
                    pending = (now + AFTER["death"], "death")
            if not gone_told and now - hidden_since > GONE_AFTER:
                events.append(f"you're gone for {GONE_AFTER:g} s (menu / new floor / dead)")
                gone_told = True
        else:
            try:
                you = xy_of(me)
                new_hand = read_u32(mem, me + 0xA0)
            except OSError:
                you, new_hand = None, hand
            if you is not None:
                if hidden_since is not None:
                    gap = now - hidden_since
                    if last_you is not None and math.dist(you, last_you) > 100:
                        events.append(f"you're back after {gap:.1f} s, {math.dist(you, last_you):.0f} away - new floor?")
                        if "floor" in save_on and not dead_told:
                            pending = (now, "floor")
                    else:
                        events.append(f"you're back after {gap:.1f} s")
                    if dead_seen and r_hidden and not dead_told:
                        # R and the restart were quicker than one sample while hidden
                        events.append("YOU DIED (R pressed)")
                        dead_told = True
                        if "death" in save_on:
                            pending = (now + AFTER["death"], "death")
                    hidden_since, gone_told, dead_told = None, False, False
                    dead_seen = r_hidden = False
                if new_hand != hand and hand is not None:
                    events.append(f"hand {hand:#x} -> {new_hand:#x}")
                hand, last_you = new_hand, you
                look = read_look()
                parts = [f"you {spot(you)}"]
                if "you" in what:
                    parts.append(f"look {spot(look)}  hand {hand:#x}")
                if "inputs" in what:
                    parts.append(f"keys {' '.join(sorted(held)) or '-'}")
                details = []
                now_alive = {}
                for card in candidates:
                    line = describe(card, you, look, lines, records)
                    if line is None:
                        continue
                    if line.startswith("ENEMY"):
                        now_alive[card] = xy_of(card)
                    if "enemies" in what and (args.bodies or line.startswith("ENEMY")):
                        details.append(line)
                for card in now_alive.keys() - alive.keys():
                    events.append(f"an enemy appeared: {card:#x} at {spot(now_alive[card])}")
                for card in alive.keys() - now_alive.keys():
                    try:
                        died = read_u32(mem, card + 0xB4) == 1
                    except OSError:
                        died = False
                    events.append(f"enemy {card:#x} {'died' if died else 'is gone'} at {spot(alive[card])}")
                alive = now_alive
                if near_text:
                    details += near_text
                    near_text = []
                sample = "  ".join(parts) + "".join(f"\n{line}" for line in details)

                # stuck: walking keys held, but you don't move
                if held & WALKING:
                    if still_xy is None or math.dist(you, still_xy) > STUCK_MOVE:
                        still_xy, still_since, stuck_told = you, now, False
                    elif now - still_since > STUCK_FOR and not stuck_told:
                        events.append(f"STUCK at {spot(you)} holding {' '.join(sorted(held & WALKING))}")
                        stuck_told = True
                        if "stuck" in save_on:
                            pending = (now + AFTER["stuck"], "stuck")
                else:
                    still_xy = None

        # --- write it down ---
        for event in events:
            rec.add(now, f"!! {event}")
        if sample is not None and args.changes:
            if sample == last_sample:
                sample = None  # --changes: the same as last time - skip it
            else:
                last_sample = sample
        if sample is not None:
            if not args.events:
                rec.add(now, sample)
            elif now >= next_beat:
                rec.add(now, sample.split("\n")[0])  # --events: one line about you every second
                next_beat = now + 1
        if pending is not None and now >= pending[0]:
            state = [
                f"you {spot(last_you)}  hand {hand:#x}" if hand is not None else "you: -",
                f"stairs {spot(items['stairs'])}   car {spot(items['car'])}   goals {len(items['goals'])}",
                f"enemies alive {len(alive)}   map {items['map']} boxes",
            ]
            rec.save(now, pending[1], state)
            pending = None
        time.sleep(max(0, 1 / args.rate - (time.monotonic() - now)))
except KeyboardInterrupt:
    rec.close(time.monotonic(), [f"you {spot(last_you)}", f"enemies alive {len(alive)}"])
