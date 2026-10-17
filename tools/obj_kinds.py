# https://github.com/Cl1ngz/HotlineMiamibot
# obj_kinds.py - teach the bot what an enemy is
import json
import math
import sys
import time

import core.enemies
from core.enemies import (copy_memory, find_aim_card, find_me_card, find_rules,
                          is_enemy, load_rules, matches, save_alive_checks,
                          save_rules)
from core.memory import X_OFF, Y_OFF, attach, read_double, table_records, wait

GUESS_FILE = "enemy_guesses.json"
PLACES = ("record", "object")  # where 0 = record, 1 = object


def under_crosshair(mem, you):
    # Look at the table once: (records right under the crosshair, every object's position).
    # second look: you moved the mouse while aiming, so find_aim_card now knows the live crosshair
    aim = find_aim_card(mem)
    if aim is None:
        raise SystemExit("can't see the crosshair - are you in a level?")
    # read X and Y from the aim card
    aim_xy = (read_double(mem, aim + X_OFF), read_double(mem, aim + Y_OFF))
    objects = table_records(mem)
    distance = {
        r: math.dist(xy, aim_xy) for r, xy in objects.items() if r not in (you, aim)
    }
    closest = min(distance.values())
    if closest > 20:
        raise SystemExit(
            f"nothing under the crosshair (closest thing is {closest:.0f} away) - aim right at it"
        )
    # the thing, plus anything glued to it (legs, its gun...)
    return [r for r, d in distance.items() if d < closest + 2], objects


def people(mem, you, aim):
    ##Aim at two enemies -> guesses.
    wait("Aim at an ENEMY and keep the crosshair on it", 6)
    first, before = under_crosshair(mem, you)
    wait("Now aim at a DIFFERENT enemy", 6)
    second, after = under_crosshair(mem, you)
    if set(first) & set(second):
        raise SystemExit(
            "that was the same enemy twice - run again and aim at two different ones"
        )
    # things that walked around by themselves while you were aiming (patrolling enemies)
    movers = {r for r in after if r in before and before[r] != after[r]} - {you, aim}
    print(f"{len(movers)} objects walked around while you were aiming")
    return find_rules(copy_memory(mem, after), first, second, you, movers)


def dogs(mem, you, aim):
    # Stand still -> whatever moves by itself and isn't an enemy yet -> guesses.
    rules = load_rules()
    wait("Stand still and DON'T touch the mouse - watching for 3 seconds", 5)
    before = table_records(mem)
    moving = set()
    for _ in range(30):
        time.sleep(0.1)
        now = table_records(mem)
        moving |= {r for r in now if r in before and now[r] != before[r]}
    runners = [
        r
        for r in moving
        if r in now and r not in (you, aim) and not is_enemy(mem, r, rules)
    ]
    print(f"{len(runners)} things ran around that aren't enemies yet")
    if len(runners) < 2:
        raise SystemExit(
            "need at least 2 of them - are the dogs alive and running? (press R and try again)"
        )
    return find_rules(
        copy_memory(mem, now), runners[:1], runners[1:2], you, set(run)


def dead(mem, you, aim):
    # Aim at a body that's still orange -> spots where every living enemy agrees and the body doesn't.
    rules = load_rules()
    wait("Aim at the DEAD body that's still orange on the radar", 6)
    under, objects = under_crosshair(mem, you)
    bodies = [r for r in under if is_enemy(mem, r, rules)]
    if not bodies:
        raise SystemExit(
            "that body doesn't count as an enemy (it isn't orange) - nothing to fix"
        )
    body = bodies[0]
    kind = next(
        rule for rule in rules if matches(mem, body, *rule)
    )  # the rule that made it orange
    living = [
        r
        for r in objects
        if r != body and matches(mem, r, *kind) and is_enemy(mem, r, rules)
    ]
    if len(living) < 2:
        raise SystemExit(
            "need at least 2 living enemies of that kind left on the floor to compare with"
        )

    print(f"comparing the body with {len(living)} living enemies for 2 seconds...")
    agree = None  # {(where, offset, value every living enemy has): the body's value}
    for _ in range(
        8
    ):  # look several times: a number that changes while they walk around is no good
        copies = copy_memory(mem, [body] + living)
        if body not in copies:
            raise SystemExit("lost the body - try again")
        found = {}
        for where in (0, 1):
            for offset in range(0, len(copies[body][where]), 4):
                theirs = {
                    int.from_bytes(d[where][offset : offset + 4], "little")
                    for r, d in copies.items()
                    if r != body
                }
                mine = int.from_bytes(
                    copies[body][where][offset : offset + 4], "little"
                )
                if (
                    len(theirs) == 1 and mine not in theirs
                ):  # all the living agree, the body doesn't
                    found[(where, offset, theirs.pop())] = mine
        agree = (
            found if agree is None else {k: v for k, v in found.items() if k in agree}
        )
        time.sleep(0.25)

    guesses = [
        [where, offset, value, mine] for (where, offset, value), mine in agree.items()
    ]
    guesses.sort(
        key=lambda g: (not (0 <= g[2] < 10000 and 0 <= g[3] < 10000), g[0], g[1])
    )  # small numbers first
    return guesses, kind


# --- find guesses (or load the last ones for --pick) ---
if "--pick" in sys.argv:
    with open(GUESS_FILE) as f:
        last = json.load(f)
    if isinstance(last, list):  # saved by an older version of this script
        last = {"mode": "kind", "guesses": last, "dogs": True}
    pick = int(sys.argv[sys.argv.index("--pick") + 1])
else:
    mem, regions, static_regions = attach()
    you = find_me_card(mem)
    aim = find_aim_card(mem)
    if you is None or aim is None:
        raise SystemExit("can't find you or the crosshair - are you in a level? ")

    if "dead" in sys.argv:
        guesses, kind = dead(mem, you, aim)
        last = {"mode": "alive", "guesses": guesses, "kind": kind}
    else:
        guesses = dogs(mem, you, aim) if "dogs" in sys.argv else people(mem, you, aim)
        last = {"mode": "kind", "guesses": guesses, "dogs": "dogs" in sys.argv}
    with open(GUESS_FILE, "w") as f:
        json.dump(last, f)
    pick = 0

guesses = last["guesses"]
if not guesses and last["mode"] == "alive":
    raise SystemExit(
        "nothing sets that one apart from the living enemies - are you sure it's dead? (aim right at it)"
    )
if not guesses:
    raise SystemExit("no guesses - try again")
if pick >= len(guesses):
    raise SystemExit(f"there are only {len(guesses)} guesses (0 to {len(guesses) - 1})")

# --- show them and save the picked one ---
if last["mode"] == "kind":
    print("  #  where   offset       value  objects  walking")
    for i, (where, offset, value, count, walking) in enumerate(guesses[:15]):
        mark = "  <- saved" if i == pick else ""
        print(
            f"{i:3}  {PLACES[where]:6} {hex(offset):>7} {hex(value):>11} {count:8} {walking:8}{mark}"
        )
    where, offset, value, count, walking = guesses[pick]
    rules = load_rules()
    if "--pick" in sys.argv:
        rules = rules[:-1]  # swap out the last rule
    elif not last["dogs"]:
        rules = []  # people: start the rules over
    rules.append((where, offset, value))
    save_rules(rules)
    print(
        f"\nsaved guess #{pick} ({count} objects). The radar now uses {len(rules)} rule(s)."
    )
    print("Wrong things orange? python obj_kinds.py --pick 1  (then 2, 3...)")
else:
    print("  #  where   offset   living have   body has")
    for i, (where, offset, value, mine) in enumerate(guesses[:15]):
        mark = "  <- saved" if i == pick else ""
        print(
            f"{i:3}  {PLACES[where]:6} {hex(offset):>7} {hex(value):>13} {hex(mine):>10}{mark}"
        )
    where, offset, value, mine = guesses[pick]
    load_rules()  # also loads the current alive checks
    checks = enemies.alive_checks
    if "--pick" in sys.argv:
        checks = checks[:-1]  # swap out the last check
    checks.append((tuple(last["kind"]), (where, offset, value)))
    save_alive_checks(checks)
    print(
        f"\nsaved guess #{pick}: the body should stop being orange, living enemies should stay orange."
    )
    print("Living enemies went grey too? python obj_kinds.py --pick 1  (then 2, 3...)")
