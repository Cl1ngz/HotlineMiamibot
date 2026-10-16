# https://github.com/Cl1ngz/HotlineMiamibot
import math

from enemies import find_aim, is_enemy, load_rules, matches, save_rules
from memory import attach, read_kind, table_records

mem, regions, static_regions = attach()
rules = load_rules()
rules.append((0, 20, 166))
cards = table_records(mem)
print(len(cards), rules)
for card, xy in cards.items():
    if is_enemy(mem, card, rules):
        print(
            hex(card),
            xy,
            hex(read_kind(mem, card, 0, 0x14)),
            hex(read_kind(mem, card, 1, 0x10)),
        )

# save_rules(rules)
