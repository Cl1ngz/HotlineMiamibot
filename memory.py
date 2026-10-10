import os

import numpy as np

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


def find_game_file(pid, exe, wine):
    # map containg virtual memory  map of process
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            parts = line.split(None, 5)
            if len(parts) < 6:
                continue
            path = parts[5].strip()
            if wine and path.lower().endswith(".exe") and GAME_NAME in path.lower():
                return int(parts[0].split("-")[0], 16), path
    return None, None


# pick writeble reg worth seaching
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


# takes photo of
def take_snapshot(mem, regions):
    snapshot = {}
    for start, end in regions:
        try:
            snapshot[start] = os.pread(mem, end - start, start)
        except OSError:
            print(f"Could not read memory region {hex(start)}-{hex(end)}")
            continue

    return snapshot


# read 8 bvtes at adres trun doble and return
def read_double(mem, address):
    data = os.pread(mem, 8, address)
    return np.frombuffer(data, dtype="<f8")[0]


def narrow(mem, candidates, how):
    new_candidates = {}
    match how:
        case "up":
            for addr, old in candidates.items():
                new = read_double(mem, addr)
                if new > old:
                    new_candidates[addr] = new
        case "down":
            for addr, old in candidates.items():
                new = read_double(mem, addr)
                if new < old:
                    new_candidates[addr] = new
        case "same":
            for addr, old in candidates.items():
                new = read_double(mem, addr)
                if new == old:
                    new_candidates[addr] = new
    return new_candidates
