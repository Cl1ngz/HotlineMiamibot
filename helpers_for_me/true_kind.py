# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/true_kind.py - look for a number every enemy has in EVERY state
# Run it while one enemy chases you (layer 6) and another one still sits (layer 0xa6).
# Pause the game (Esc) first.
import sys
import time

from enemies import copy_memory, find_me_card, find_rules
from memory import attach, read_kind, table_records


def wait_for(mem, mode):
    """Wait for the right moment, then take a photo of memory."""
    while True:
        cards = table_records(mem)
        chasing = []
        sitting = []
        ...  # your for loop, fills chasing and sitting
        for card in cards:
            kind = read_kind(mem, card, 0, 0x14)
            if kind == 6:
                chasing.append(card)
            elif kind == 0xA6:
                sitting.append(card)
        if mode == "sitting" and len(sitting) >= 2:
            break
        if mode == "chasing" and len(chasing) >= 2:
            break
        if mode == "mixed" and len(chasing) >= 1 and len(sitting) >= 1:
            break
        time.sleep(0.05)
    return copy_memory(mem, cards), chasing, sitting


if __name__ == "__main__":
    mem, regions, static_regions = attach()
    you = find_me_card(mem)
    cards = table_records(mem)

    mode = sys.argv[1] if len(sys.argv) > 1 else "mixed"

    copies, chasing, sitting = wait_for(mem, mode)
    print(f"got it! chasing: {len(chasing)}  sitting: {len(sitting)}")

    if mode == "sitting":
        first, second = sitting[:1], sitting[1:2]
    elif mode == "chasing":
        first, second = chasing[:1], chasing[1:2]
    else:
        first, second = chasing, sitting
    guesses = find_rules(copies, first, second, you, set())

    for where, offset, value, count, walking in guesses[:15]:
        # print where (0 card / 1 folder), offset and value in hex, and count
        print(
            f"{'card' if where == 0 else 'folder'} {offset:#04x} {value:#04x} {count} {'walking' if walking else 'still'}"
        )
