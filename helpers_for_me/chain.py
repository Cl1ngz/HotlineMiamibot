# helpers_for_me/chain.py - follow the game's own links from a fixed address
from core.memory import attach, read_kind, read_u32

GAME = 0xBB0D68  # a locker inside the game file - the same address after every restart

mem, regions, static_regions = attach()
# what lies in locker GAME (a link to some big object of the game)
game = read_u32(mem, GAME)
# what lies in locker game + 0x3bc (the part the game checks after GetFocus)
part = read_u32(mem, game + 0x3BC)
print(f"game object at {game:#x}, its part +0x3bc at {part:#x}")
