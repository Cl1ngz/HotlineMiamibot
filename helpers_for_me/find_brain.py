# helpers_for_me/find_brain.py - where else in memory is a sitting enemy's position?
import struct

from helpers_for_me.true_kind import wait_for
from memory import (
    X_OFF,
    Y_OFF,
    attach,
    read_double,
    read_kind,
    table_records,
    take_snapshot,
)

mem, regions, static_regions = attach()
cards = table_records(mem)
_, _, sitting = wait_for(mem, "sitting")
snapshot = take_snapshot(
    mem, regions
)  # {region start: its bytes} - all writable memory

for card in sitting:
    x = read_double(mem, card + X_OFF)
    y = read_double(mem, card + Y_OFF)
    # x and y as 16 bytes, exactly as they sit in memory
    patterns = {
        "double": struct.pack("<dd", x, y),  # 2 x 8 bytes, like the card
        "float": struct.pack("<ff", x, y),  # 2 x 4 bytes
    }
    print(f"enemy card {hex(card)} at {x}, {y}:")
    for name, pattern in patterns.items():
        for start, data in snapshot.items():
            i = data.find(pattern)  # where in this region? -1 = not here
            while i != -1:
                address = start + i
                if address == card + X_OFF:
                    print(f"  {hex(address)} (the card itself) pattern: {name}")
                else:
                    print(f"  {hex(address)} pattern: {name}")
                i = data.find(pattern, i + 1)  # look for the next one after this
