from core.memory import attach
from core.weapons import find_weapons, load_names

mem, regions, static_regions = attach()
names = load_names()
for x, y, frame in find_weapons(mem):
    print(f"{x:6.1f}, {y:6.1f}  frame {frame}  {names.get(frame, {}).get('name', '?')}")
