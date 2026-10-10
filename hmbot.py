import os

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

    return None, None


start, path = find_game_file(pid, exe, wine)
