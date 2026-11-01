# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/blackbox.py - a flight recorder: what did the bot SEE in the last 3 seconds?
#
# Run it NEXT TO hmbot (it only reads memory, it never writes). 30 times a second it writes down:
#   - you: where you are, where your character looks (the look - hmbot writes it there when it's locked on)
#     and your card +0xA0 (with the bat: 0x13 = at rest, 0x57 = swinging)
#   - every object closer than RANGE that matches an enemy RULE (dead checks are NOT used to pick them!):
#     its layer, a few numbers we're unsure about, and what is_enemy and can_see say about it
#     "<- LOOK" marks the enemy your character is looking at (= the bot's target, when it's locked on)
# It keeps only the last KEEP seconds. When you die it saves them to blackbox_1.txt, blackbox_2.txt...
# Ctrl+C saves the last seconds too - for moments that aren't a death (e.g. the enemy knocked down by a door).
#
# "near" mode: instead of rule-matching objects, write down EVERY object closer than NEAR_RANGE
# (except you and the walls) - for things our rules don't know yet, like a freshly knocked-down enemy.
#
#   python -m helpers_for_me.blackbox         (hmbot in another terminal, then play; send me the .txt files)
#   python -m helpers_for_me.blackbox near    (everything right around you)
import math
import subprocess
import sys
import time
from collections import Counter, deque

from core.enemies import find_me_card, is_enemy, load_rules, matches
from core.hands import LOOK_X, LOOK_Y, follow
from core.memory import X_OFF, Y_OFF, attach, read_double, read_u32, table_cards, table_records
from core.walls import can_see, find_walls, wall_lines

EVERY = 1 / 30  # seconds between two samples
KEEP = 8  # seconds of history to save
SCAN_EVERY = 0.25  # seconds between looking for new enemy cards (like hmbot)
NEAR = len(sys.argv) > 1 and sys.argv[1] == "near"
RANGE = 60 if NEAR else 250  # only write down things this close to you (250 = lockon's MAX_RANGE)
LAYER = 0x14
SWING = 0xA0
EXTRA = (0x10, 0xA4, 0xB4)  # card offsets we're unsure about - shown for every enemy
LOOK_NEAR = 8  # the look is this close to an enemy -> the bot is aiming at him

mem, regions, static_regions = attach()
rules = load_rules()
if not rules:
    raise SystemExit("no enemy rules yet - run python -m tools.obj_kinds first")


def notify(text):
    """Pop-up, because you're looking at the game, not the terminal."""
    print(text)
    subprocess.run(["notify-send", "-t", "2000", "HMBot blackbox", text])


def xy_of(card):
    return read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)


def read_look():
    """Where your character looks, or None if the chain can't be followed right now."""
    try:
        return read_double(mem, follow(mem, LOOK_X)), read_double(mem, follow(mem, LOOK_Y))
    except OSError:
        return None


def describe(card, you, look, lines):
    """One line about one enemy-looking object, or None if it's far away or gone."""
    try:
        xy = xy_of(card)
        far = math.dist(xy, you)
        if far > RANGE:
            return None
        extra = "  ".join(f"+{offset:#x} {read_u32(mem, card + offset):#6x}" for offset in EXTRA)
        layer = read_u32(mem, card + LAYER)
    except OSError:
        return None
    enemy = "YES" if is_enemy(mem, card, rules) else "no "
    see = "YES" if can_see(you, xy, lines) else "no "
    aimed = "  <- LOOK" if look is not None and math.dist(look, xy) < LOOK_NEAR else ""
    return (
        f"   {card:#x} ({xy[0]:4.0f},{xy[1]:4.0f}) far {far:3.0f}  layer {layer:#6x}  {extra}"
        f"  enemy={enemy} see={see}{aimed}"
    )


def sample(candidates, lines):
    """Everything we write down in one moment, as lines of text. None = you're not in the game (dead/menu)."""
    me = find_me_card(mem)
    if me is None:
        return None
    you = xy_of(me)
    look = read_look()
    look_text = "?" if look is None else f"({look[0]:4.0f},{look[1]:4.0f})"
    text = [f"you ({you[0]:4.0f},{you[1]:4.0f})  look {look_text}  swing +0xA0 {read_u32(mem, me + SWING):#x}"]
    alive = table_cards(mem)
    for card in candidates:
        if card in alive and card != me:
            line = describe(card, you, look, lines)
            if line is not None:
                text.append(line)
    return text


def save(history, number):
    """Write the history to blackbox_<number>.txt. Time is counted back from the last moment (t=-0.50s ...)."""
    name = f"blackbox_{number}.txt"
    last = history[-1][0]
    with open(name, "w") as f:
        for moment, text in history:
            f.write(f"t={moment - last:+.2f}s  {text[0]}\n")
            for line in text[1:]:
                f.write(line + "\n")
    notify(f"saved the last {KEEP} s to {name}")


def everything_but_walls(records):
    """Every card except the walls: the walls are the layer that most cards share."""
    layers = {}
    for record in records:
        try:
            layers[record] = read_u32(mem, record + LAYER)
        except OSError:
            continue
    if not layers:
        return []
    wall = Counter(layers.values()).most_common(1)[0][0]
    return [record for record, layer in layers.items() if layer != wall]


history = deque()  # (time, lines of text), oldest first
saved = 0
was_in_game = False
candidates, lines = [], []
next_scan = 0
print("recording... die, or press Ctrl+C, to save the last seconds")
try:
    while True:
        now = time.monotonic()
        try:
            if now >= next_scan:
                records = table_records(mem)
                if NEAR:
                    candidates = everything_but_walls(records)
                else:
                    candidates = [r for r in records if any(matches(mem, r, *rule) for rule in rules)]
                lines = wall_lines(find_walls(mem, records, rules))
                next_scan = now + SCAN_EVERY
            text = sample(candidates, lines)
        except OSError:
            text = None  # loading / new floor: memory is moving
        if text is None:
            if was_in_game and history:
                saved += 1
                save(history, saved)  # you just died (or the floor changed)
                history.clear()
            was_in_game = False
        else:
            was_in_game = True
            history.append((now, text))
            while now - history[0][0] > KEEP:
                history.popleft()
        time.sleep(max(0, EVERY - (time.monotonic() - now)))
except KeyboardInterrupt:
    if history:
        save(history, saved + 1)
