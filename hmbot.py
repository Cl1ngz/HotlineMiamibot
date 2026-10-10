import os
import time

GAME_NAME = "hotline"


def find_game():
    best = None
    for pid in os.listdir("/proc"):
        # print(f"Checking {pid}")
        if not pid.isdigit():
            continue
        try:
            # comm name of pid name of running process
            with open(f"/proc/{pid}/comm") as f:
                name = f.read().strip()
                # print(name)
            # statm fiel conntaing detiailed memory usage: {size rezident shared text lib data dt}
            # [1] reads phisical memory current
            with open(f"/proc/{pid}/statm") as f:
                ram = int(f.read().split()[1])
                # print(ram)
        except OSError:
            continue
        if GAME_NAME in name.lower() and (best is None or ram > best[2]):
            best = (int(pid), name, ram)
    return best


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


def find_game_file(pid, exe, wine):
    # map containg virtual memory  map of process
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            parts = line.split(None, 6)
            if len(parts) < 6:
                continue
            path = parts[5].strip()
            if wine and path.lower().endswith(".exe") and GAME_NAME in path.lower():
                return int(parts[0].split("-")[0], 16), path
    return None, None


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


def writable_regions(pid, game_path):
    regions = []
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            parts = line.split(None, 5)
            if not parts[1].startswith("rw"):
                continue
            path = parts[5].strip() if len(parts) == 6 else ""
            if path not in ("", "[heap]", game_path):
                continue
            start, end = (int(x, 16) for x in parts[0].split("-"))
            regions.append((start, end))
    return regions


regions = writable_regions(pid, path)
total_size = sum(end - start for start, end in regions)
print(f"Found {len(regions)} writable regions")
print(f"Total writable size: {total_size / 1024 / 1024:.2f} MB")


def take_snapshot(mem, regions):
    snapshot = {}
    for start, end in regions:
        try:
            snapshot[start] = os.pread(mem, end - start, start)
        except OSError:
            print(f"Could not read memory region {hex(start)}-{hex(end)}")
            continue

    return snapshot


t = time.time()
snapshot = take_snapshot(mem, regions)
took = time.time() - t

print("Regions readed: ", len(snapshot))
print("how many mb was: ", sum(len(data) for data in snapshot.values()) / 1024 / 1024)
print(f"Snapshot took {took:.2f} seconds")
