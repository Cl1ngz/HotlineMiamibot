# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/true_kind.py - look for a number every enemy has in EVERY state
# Run it while one enemy chases you (layer 6) and another one still sits (layer 0xa6).
# Pause the game (Esc) first.
from enemies import copy_memory, find_me_card, find_rules
from memory import attach, read_kind, table_records

mem, regions, static_regions = attach()
you = find_me_card(mem)
cards = table_records(mem)

chasing = ...  # list of cards whose layer (card, 0x14) is 6
sitting = ...  # list of cards whose layer is 0xa6
print(f"chasing: {len(chasing)}  sitting: {len(sitting)}")
if not chasing or not sitting:
    raise SystemExit("need one enemy chasing you and one still sitting - try again")

guesses = find_rules(copy_memory(mem, cards), chasing, sitting, you, set())
for where, offset, value, count, walking in guesses[:15]:
    ...  # print where (0 card / 1 folder), offset and value in hex, and count
