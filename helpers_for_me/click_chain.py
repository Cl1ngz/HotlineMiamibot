# helpers_for_me/click_chain.py - follow the chain to the click byte
from core.memory import attach, read_u32

mem, regions, static_regions = attach()
# step 1: the link in the fixed locker
game = read_u32(mem, 0xBB0D68)
# step 2: the link at game + 0x42c
thing = read_u32(mem, game + 0x42C)
# step 3: the link at thing + 0x9c   (the mouse device?)
mouse = read_u32(mem, thing + 0x9C)
# the click byte inside the mouse
button = mouse + 0x52D
print(f"mouse device at {mouse:#x}, click byte at {button:#x}")
