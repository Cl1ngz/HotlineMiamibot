import os
import time

import numpy as np

from memory import (
    find_game,
    find_game_file,
    read_double,
    take_snapshot,
    writable_regions,
)

GAME_NAME = "hotline"


game = find_game()
# print(game)
if game is None:
    print(f"{GAME_NAME} not found")
    raise SystemExit
pid, name, _ = game
print(f"Found {name} pid {pid}")

# symlink to process executable
exe = os.readlink(f"/proc/{pid}/exe")
# print(f"Executable: {exe}")
wine = "wine" in os.path.basename(exe) or "preloader" in os.path.basename(exe)
print(f"its proton" if wine else "its native", exe)


start, path = find_game_file(pid, exe, wine)
if start is None:
    print("Couldn't find the game file in memory bruh")
    raise SystemExit
print(f"game file {os.path.basename(path)} at {hex(start)}")
# print(f"game file {path} at {hex(start)}")

try:
    mem = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
except PermissionError:
    print("ERROR run: sudo sysctl kernel.yama.ptrace_scope=0")
    raise SystemExit

header = os.pread(mem, 0x200, start)  # read 512 bytes at that address
print("First bytes there:", header[:4])

# linux native
if header[:4] == b"\x7fELF":
    bits = 32 if header[4] == 1 else 64
# Windows or proton
elif header[:2] == b"MZ":
    pe = int.from_bytes(header[0x3C:0x40], "little")
    magic = int.from_bytes(os.pread(mem, 2, start + pe + 24), "little")
    bits = 32 if magic == 0x10B else 64
else:
    bits = "unknown"
# if this shit show up mem reding work
print(f"Game is {bits}-bit")


regions = writable_regions(pid, path)
total_size = sum(end - start for start, end in regions)
print(f"Found {len(regions)} writable regions")
print(f"Total writable size: {total_size / 1024 / 1024:.2f} MB")


t = time.time()
snapshot = take_snapshot(mem, regions)
took = time.time() - t

print("Regions readed: ", len(snapshot))
# lendata is one chunk
print("how many mb was: ", sum(len(data) for data in snapshot.values()) / 1024 / 1024)
print(f"Snapshot took {took:.2f} seconds")


# for data in snapshot.values():
#     numbers = np.frombuffer(data, dtype="<f8")
#     print(np.count_nonzero(numbers))
#     print(numbers[1000:1020])

before = take_snapshot(mem, regions)
input("Walk RIGHT a bit in the game, then come back here and press Enter...")
after = take_snapshot(mem, regions)

candidates = {}
for start in before:
    if start not in after or len(before[start]) != len(after[start]):
        continue
    a = np.frombuffer(before[start], dtype="<f8")
    b = np.frombuffer(after[start], dtype="<f8")
    went_up = b > a
    looks_ok = (np.abs(b) > 0.01) & (np.abs(b) < 100000)
    both = went_up & looks_ok
    for i in np.flatnonzero(both):
        candidates[start + int(i) * 8] = b[i]

print(len(candidates), "candidates found")

for address, value in list(candidates.items())[:10]:
    print(hex(address), value)


input("Now walk LEFT, then press Enter...")
for address, old in list(candidates.items())[:5]:
    print(hex(address), "old:", old, "new:", read_double(mem, address))
new_candidates = {}
for address, old in candidates.items():
    try:
        new = read_double(mem, address)
    except OSError:
        continue
    if new < old:
        new_candidates[address] = new
candidates = new_candidates
print(len(candidates), "left after walking left")
