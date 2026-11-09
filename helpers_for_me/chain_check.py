# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/chain_check.py - why did a write to the game fail? (a helper, only reads)
#
# hmbot died with "OSError: [Errno 5] Input/output error" in look_at: the address the look chain
# led to is not the game's memory. This checks the two ways that can happen:
#   1. TWO game processes: attach() (reading) and open_rw() (writing) each pick "the biggest one" by
#      themselves - if they pick different ones, the bot reads one game and writes into the other
#   2. a link of a chain is empty or junk right now (a scene where the game hasn't set it up yet)
#
#   python -m helpers_for_me.chain_check      the game where the bot died, the bot NOT running
import os
import time

from core.hands import BUTTON, GAME, KEYBOARD, LOOK_X, LOOK_Y
from core.memory import GAME_NAME, find_game, read_bytes, read_double, read_u32

CHAINS = {"look X": LOOK_X, "look Y": LOOK_Y, "left button": BUTTON, "keyboard": KEYBOARD}
LOOKS = 5  # look this many times...
EVERY = 0.5  # ...this many seconds apart: a link that keeps changing is no good either

# 1. every process with "hotline" in its name
print("game processes:")
games = []
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    try:
        with open(f"/proc/{pid}/comm") as f:
            name = f.read().strip()
        with open(f"/proc/{pid}/statm") as f:
            ram = int(f.read().split()[1])
    except OSError:
        continue
    if GAME_NAME in name.lower():
        games.append((int(pid), name, ram))
        print(f"  pid {pid:>7}  {name:20}  {ram * 4 // 1024:6} MB in RAM")
if not games:
    raise SystemExit("  none - start the game first")
chosen = find_game()
print(f"the bot takes pid {chosen[0]} (the biggest)")
if len(games) > 1:
    print("  !! MORE THAN ONE: attach() and open_rw() may take different ones - close the extra one")

# 2. follow every chain, link by link, a few times
mem = os.open(f"/proc/{chosen[0]}/mem", os.O_RDONLY)


def follow_loud(chain):
    """The chain link by link: 'GAME 0x.. -> 0x.. -> ... = 0x..', and the end address (None = broken)."""
    offsets, last = chain
    text = f"[{GAME:#x}]"
    try:
        here = read_u32(mem, GAME)
        text += f" = {here:#x}"
        for offset in offsets:
            here = read_u32(mem, here + offset)
            text += f" -> +{offset:#x} = {here:#x}"
    except OSError:
        return text + " -> CAN'T READ", None
    return text + f" -> +{last:#x}", here + last


for look in range(LOOKS):
    print(f"\nlook {look + 1}:")
    for name, chain in CHAINS.items():
        text, end = follow_loud(chain)
        if end is None:
            print(f"  {name:12} BROKEN   {text}")
            continue
        try:
            if name.startswith("look"):
                value = read_double(mem, end)  # where your character looks
            else:
                byte = read_bytes(mem, 1, end)  # 0x80 held, 0 let go
                if not byte:
                    raise OSError
                value = byte[0]
            print(f"  {name:12} ok {value:10.1f}   {text} = {end:#x}")
        except OSError:
            print(f"  {name:12} NOT GAME MEMORY   {text} = {end:#x}   <- a write here = Errno 5")
    time.sleep(EVERY)
