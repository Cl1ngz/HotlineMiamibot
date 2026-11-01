# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/who_am_i.py - why can't the bot find you? Everything that looks like you or the crosshair.
#
# find_me_card looks for cards with layer 0x2C AND picture 0x47. One -> that's you. More than one -> the one
# closest to a crosshair card (layer 0xAF) from the TABLE. None of those -> "no player found".
# This prints every candidate, so we see which step fails.
#
#   python -m helpers_for_me.who_am_i     run it in a 2nd terminal WHILE hmbot says "no player found (paused)"
#                                         (don't stop hmbot). Then restart hmbot and run this once more.
#   python -m helpers_for_me.who_am_i watch   keeps looking, 2 times a second, NEXT TO hmbot - prints a line
#                                         every time the answer changes. Start both, die on floor 2, press R.
import math
import sys
import time

from core.enemies import RECORD, find_me_card
from core.memory import X_OFF, Y_OFF, attach, read_double, read_kind, read_u32, table_records

ME_LAYER, ME_PICTURE = 0x2C, 0x47
AIM_LAYER = 0xAF

mem, regions, static_regions = attach()


def you_cards(table, spread):
    """Cards with layer 0x2C AND picture 0x47 from `spread` cards before the table's first card to `spread` after
    its last one. find_me_card looks 64 around - a bigger spread shows if you sometimes live further away."""
    found = []
    for card in range(min(table) - spread * RECORD, max(table) + spread * RECORD + 1, RECORD):
        try:
            if read_kind(mem, card, 0, 0x14) == ME_LAYER and read_kind(mem, card, 1, 0x10) == ME_PICTURE:
                found.append(card)
        except OSError:
            continue
    return found


if len(sys.argv) > 1 and sys.argv[1] == "watch":
    print("watching... Ctrl+C to stop")
    start, last = time.monotonic(), None
    try:
        while True:
            try:
                table = table_records(mem)
                if not table:
                    line = "the table is empty (menu / loading)"
                else:
                    near, wide = you_cards(table, 64), you_cards(table, 2048)
                    far = [card for card in wide if card not in near]
                    me = find_me_card(mem)
                    line = (
                        f"table {len(table)} cards {min(table):#x}..{max(table):#x} | you within 64: "
                        f"{[hex(c) for c in near]} | further away: {[hex(c) for c in far]} | "
                        f"find_me_card: {'None' if me is None else hex(me)}"
                    )
            except OSError as err:
                line = f"error: {err}"
            if line != last:
                print(f"t={time.monotonic() - start:6.1f}s  {line}")
                last = line
            time.sleep(0.5)
    except KeyboardInterrupt:
        raise SystemExit("bye!")

table = table_records(mem)
if not table:
    raise SystemExit("the table is empty - menu or loading?")

players, aims = [], []
for card in range(min(table) - 64 * RECORD, max(table) + 64 * RECORD + 1, RECORD):
    try:
        x, y = read_double(mem, card + X_OFF), read_double(mem, card + Y_OFF)
        if not (0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000):
            continue
        layer = read_kind(mem, card, 0, 0x14)
        picture = read_kind(mem, card, 1, 0x10)
        state, done = read_u32(mem, card + 0x10), read_u32(mem, card + 0xB4)
    except OSError:
        continue
    line = (
        f"  {card:#x} at ({x:6.1f},{y:6.1f})  layer {layer:#6x}  picture {picture:#6x}"
        f"  +0x10 {state:#x}  +0xB4 {done}  {'table' if card in table else 'SHELF'}"
    )
    if layer == ME_LAYER or (picture == ME_PICTURE and layer not in (9, 0xFFFFFF9C)):
        players.append((card, (x, y), layer == ME_LAYER and picture == ME_PICTURE, line))
    if layer == AIM_LAYER:
        aims.append(((x, y), card in table, line))

print("cards that look like YOU (layer 0x2C and/or picture 0x47, walls and floor things skipped):")
for card, xy, both, line in players:
    print(line + ("   <- BOTH match (find_me_card counts this one)" if both else ""))
if not players:
    print("  none")
print("\ncrosshair cards (layer 0xAF):")
for xy, in_table, line in aims:
    print(line)
if not aims:
    print("  none")

matching = [p for p in players if p[2]]
in_table_aims = [xy for xy, in_table, _ in aims if in_table]
print(f"\n{len(matching)} card(s) match you, {len(in_table_aims)} crosshair card(s) in the table")
if len(matching) > 1:
    for card, xy, _, _ in matching:
        near = min((math.dist(xy, aim) for aim in in_table_aims), default=None)
        print(f"  {card:#x}: closest table crosshair {'none' if near is None else f'{near:.0f} away'}")
me = find_me_card(mem)
print(f"find_me_card says: {'None' if me is None else hex(me)}")
