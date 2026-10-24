# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/rebuild/read_kind_rebuild.py - rebuild read_kind from memory, tested on a fake locker room
#
#   python helpers_for_me/rebuild/read_kind_rebuild.py

# the fake locker room: locker number -> the number inside
LOCKERS = {
    0x100: 0x500,  # card +0x00 -> link to the folder
    0x110: 0x3,  # card +0x10 -> something else
    0x114: 0x6,  # card +0x14 -> layer
    0x510: 0x47,  # folder +0x10 -> picture
}


def read_u32(mem, address):
    """Open the locker at this address and give back the number inside (mem is not used here)."""
    return LOCKERS[address]


def read_kind(mem, card, where, offset):
    # DONE: where == 0 -> open one locker, where == 1 -> open two lockers
    if where == 0:
        # open the locker at card + offset and return the number inside
        return read_u32(mem, card + offset)
    if where == 1:
        # open the locker at card then open the locker at the number inside + offset and return that number
        folder = read_u32(mem, card)
        return read_u32(mem, folder + offset)
    raise ValueError(f"where must be 0 or 1, not {where}")


# each test: (card, where, offset) and what read_kind should give back
tests = [
    ((0x100, 0, 0x14), 0x6),
    ((0x100, 1, 0x10), 0x47),
    ((0x100, 0, 0x10), 0x3),
]
for (card, where, offset), expected in tests:
    got = read_kind(None, card, where, offset)
    result = "OK  " if got == expected else "FAIL"
    got_text = hex(got) if isinstance(got, int) else repr(got)
    print(
        f"{result} read_kind(mem, {card:#x}, {where}, {offset:#x}) -> {got_text}   (expected {expected:#x})"
    )
