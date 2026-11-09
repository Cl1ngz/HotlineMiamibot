# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/card_diff.py - what makes a FAKE enemy (blood, footprints) different from a REAL one?
#
# Blood on level 2 matches rule 1 (+0x10 = 6) just like the real enemies, and its "picture" is not
# always the same (0x5, 0x6, ...), so one death sign isn't enough. This keeps the bytes of cards that
# the bot counts as enemies, in two groups, and then looks for a number that EVERY fake one has and
# NO real one has - that number becomes a death sign ("not an enemy") of the rule.
#
#   python -m helpers_for_me.card_diff real    bot off, aim at a REAL living enemy - its bytes get kept
#   python -m helpers_for_me.card_diff junk    bot off, aim at a FAKE enemy (blood the radar shows orange)
#   python -m helpers_for_me.card_diff         compare everything kept so far, list the possible signs
#   python -m helpers_for_me.card_diff add N   save sign N from that list as a death sign of the rule
#   python -m helpers_for_me.card_diff clear   forget everything kept
#
# Everything is kept in card_diff.json, so real and junk can come from different levels and game starts.
# The more of each the better: 3+ real (different enemies, standing and walking) and 3+ junk.
import json
import math
import os
import sys
import time

import core.enemies
from core.enemies import (
    AIM_PICTURE,
    copy_memory,
    find_aim,
    find_me_card,
    is_enemy,
    load_rules,
    save_dead_checks,
    shelf_cards,
)
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, table_records, wait

FILE = "card_diff.json"
CLOSE = 20  # the card must be this close to the crosshair
WATCH = 8  # read it this many times, 0.25 s apart: only numbers that never change get kept
SMALL = 0x10000  # numbers below this (or this close below 0) are flags / kinds; bigger ones may be pointers
POSITION = range(X_OFF, Y_OFF + 8)  # the x/y doubles: never a sign
SHOW = 15  # print at most this many signs
NAMES = {(0, 0x14): "layer", (0, 0x10): "+0x10", (1, 0x10): "picture", (0, 0xB4): "+0xB4"}


def name(where, offset):
    return NAMES.get((where, offset), f"{'card' if where == 0 else 'folder'} {offset:+#x}")


def load():
    try:
        with open(FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"real": [], "junk": [], "last": []}


def save(data):
    with open(FILE, "w") as f:
        json.dump(data, f)


def small(value):
    return value < SMALL or value > 0xFFFFFFFF - SMALL


def keep(group):
    """Aim at one card that counts as an enemy, read it WATCH times, keep the numbers that never changed."""
    mem, regions, static_regions = attach()
    rules = load_rules()
    find_aim(mem)  # warm-up: find_aim has to see the crosshair move once
    what = "a REAL living enemy" if group == "real" else "a FAKE enemy (orange blood on the radar)"
    wait(f"aim at {what} and keep the crosshair on it", 3)
    aim = find_aim(mem)
    table = table_records(mem)
    if aim is None or not table:
        raise SystemExit("no crosshair / no table - inside a level, move the mouse a bit and try again")
    me = find_me_card(mem)

    near = []
    for card in shelf_cards(mem, list(table)):
        xy = (read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF))
        if card == me or math.dist(xy, aim) >= CLOSE:
            continue
        # any card a rule matches, bodies (+0xB4 = 1) left out - NOT is_enemy(), so blood that an
        # earlier sign already hides (picture 0x6) can still be kept as junk
        if core.enemies.matches(mem, card, 1, 0x10, AIM_PICTURE):
            continue  # the crosshair itself
        if any(core.enemies.matches(mem, card, *r) for r in rules) and read_kind(mem, card, 0, 0xB4) != 1:
            near.append((math.dist(xy, aim), card, xy))
    if not near:
        raise SystemExit("nothing under the crosshair matches an enemy rule - aim right at it")
    _, card, xy = min(near)
    # is_enemy goes with the FIRST rule that matches, so that's the rule a death sign has to go under
    rule = next(r for r in rules if core.enemies.matches(mem, card, *r))
    picture = read_kind(mem, card, 1, 0x10)
    hidden = "" if is_enemy(mem, card, rules) else " (an earlier sign already hides it)"

    stable = None
    for _ in range(WATCH):
        copy = copy_memory(mem, [card]).get(card)
        if copy is None:
            raise SystemExit("lost the card while reading it - try again")
        now = {}
        for where in (0, 1):
            for offset in range(0, len(copy[where]) - 3, 4):
                if where == 0 and offset in POSITION:
                    continue
                now[f"{where}:{offset}"] = int.from_bytes(copy[where][offset : offset + 4], "little")
        stable = now if stable is None else {k: v for k, v in stable.items() if now.get(k) == v}
        time.sleep(0.25)

    data = load()
    data[group].append(
        {"rule": list(rule), "at": [round(xy[0]), round(xy[1])], "picture": picture, "bytes": stable}
    )
    save(data)
    print(
        f"kept {card:#x} at ({xy[0]:.0f},{xy[1]:.0f}) as {group}: rule {rules.index(rule)} "
        f"({name(*rule[:2])} = {rule[2]:#x}), picture {picture:#x}, {len(stable)} numbers that stayed the same{hidden}"
    )
    print(f"now: {len(data['real'])} real, {len(data['junk'])} junk kept")


def compare():
    data = load()
    signs = []  # [rule, [where, offset, value]] - the same order as printed, for "add N"
    for rule in sorted({tuple(j["rule"]) for j in data["junk"]}):
        junk = [j for j in data["junk"] if tuple(j["rule"]) == rule]
        real = [r for r in data["real"] if tuple(r["rule"]) == rule]
        print(f"\nrule {name(*rule[:2])} = {rule[2]:#x}: {len(junk)} junk, {len(real)} real")
        print("  junk pictures: " + ", ".join(f"{j['picture']:#x} at {tuple(j['at'])}" for j in junk))
        print("  real pictures: " + (", ".join(f"{r['picture']:#x} at {tuple(r['at'])}" for r in real) or "-"))
        if not real:
            print("  no real enemy of this rule kept yet - run: python -m helpers_for_me.card_diff real")
            continue
        if len(junk) < 2:
            print("  (only 1 junk: almost every number 'agrees' - keep 1 or 2 more junk for a short list)")

        found = []
        for key, value in junk[0]["bytes"].items():
            if any(j["bytes"].get(key) != value for j in junk):
                continue  # the fake ones don't all have it
            theirs = [r["bytes"].get(key) for r in real]
            if None in theirs:
                continue  # it changed on a real enemy while reading - it could hit this value one day
            if value in theirs:
                continue  # a real enemy has it too - that sign would hide him
            where, offset = (int(part) for part in key.split(":"))
            agree = len(set(theirs)) == 1
            # best first: the real ones all agree on another number, then small numbers (not pointers)
            found.append((not agree, not small(value), where, offset, value, theirs))
        found.sort()
        if not found:
            print("  no number tells them apart - keep more real/junk or look somewhere else")
            continue
        print("    #  spot            junk has     real have")
        for not_agree, big, where, offset, value, theirs in found[:SHOW]:
            shown = f"{theirs[0]:#x} (all)" if not not_agree else ", ".join(hex(t) for t in sorted(set(theirs)))
            note = "   (big - maybe a pointer, changes between game starts)" if big else ""
            print(f"  {len(signs):3}  {name(where, offset):14}  {value:#10x}   {shown}{note}")
            signs.append([list(rule), [where, offset, value]])
        if len(found) > SHOW:
            print(f"  ... and {len(found) - SHOW} more")
    data["last"] = signs
    save(data)
    if signs:
        print("\nsave a good one (small, real ones all agree): python -m helpers_for_me.card_diff add N")


def add(word):
    signs = load().get("last", [])
    try:
        rule, check = signs[int(word)]
    except (ValueError, IndexError):
        raise SystemExit(f"give a number from the last list (0 to {len(signs) - 1})")
    load_rules()  # fills core.enemies.dead_checks
    checks = core.enemies.dead_checks
    sign = (tuple(rule), tuple(check))
    if sign in checks:
        raise SystemExit("that death sign is already saved")
    checks.append(sign)
    save_dead_checks(checks)
    print(f"saved: rule {name(*rule[:2])} = {rule[2]:#x} is NOT an enemy when {name(*check[:2])} = {check[2]:#x}")
    print("check it: python -m tools.radar - the blood not orange any more, the real enemies still orange")


args = sys.argv[1:]
if args in (["real"], ["junk"]):
    keep(args[0])
elif not args:
    compare()
elif args[0] == "add" and len(args) == 2:
    add(args[1])
elif args == ["clear"]:
    if os.path.exists(FILE):
        os.remove(FILE)
    print("forgot everything")
else:
    raise SystemExit("usage: python -m helpers_for_me.card_diff [real | junk | add N | clear]")
