# https://github.com/Cl1ngz/HotlineMiamibot
import json
import math
import os
import subprocess
import time

import numpy as np

TABLE_START = 0xBEB900  # the game's object table is around here (you: 0xBEC91C, crosshair: 0xBECBD8)
TABLE_END = 0xBED900
X_OFF = 0x50  # starts at 0x50 it takes 8 bytes
Y_OFF = (
    0x58  # 8 bytes offset because the game stores X and Y as doubles and x took 8 bytes
)

GAME_NAME = "hotline"
ADDRESS_FILE = "addresses.json"

# experimen find_me.py
PLAYER_KIND = 0x2C  # hides when dead
AIM_KIND = 0xAF  # closer is the one


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
            # print(f"Could not read memory region {hex(start)}-{hex(end)}")
            continue

    return snapshot


# read 8 bvtes at adres trun doble and return
def read_double(mem, address):
    data = os.pread(mem, 8, address)
    if len(data) < 8:
        raise OSError(f"can't read {hex(address)}")
    return np.frombuffer(data, dtype="<f8")[0]


def narrow(mem, candidates, how):
    new_candidates = {}
    for addr, old in candidates.items():
        try:
            new = read_double(mem, addr)
        except OSError:
            # memory freed = drop it
            continue
        if how == "up":
            keep = new > old
        elif how == "down":
            keep = new < old
        elif how == "same":
            keep = new == old
        else:
            raise ValueError(f"unknown how: {how}")
        if keep:
            new_candidates[addr] = new
    return new_candidates


def first_scan(mem, regions, prompt, ask=input):
    before = take_snapshot(mem, regions)
    ask(prompt)
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

    return candidates


def attach():
    game = find_game()
    if game is None:
        raise SystemExit("Hotline Miami isn't running - start it first")
    pid, name, _ = game
    # print(f"Found {name} pid {pid}")

    # symlink to process executable
    exe = os.readlink(f"/proc/{pid}/exe")
    wine = "wine" in os.path.basename(exe) or "preloader" in os.path.basename(exe)
    start, path = find_game_file(pid, exe, wine)
    # print(f"game file {os.path.basename(path)} at {hex(start)}")

    mem = os.open(f"/proc/{pid}/mem", os.O_RDONLY)

    pe = int.from_bytes(os.pread(mem, 4, start + 0x3C), "little")
    image_size = int.from_bytes(os.pread(mem, 4, start + pe + 80), "little")

    regions = writable_regions(pid, path)
    # the game's own globals: inside the game file's memory, same address every launch
    static_regions = [
        (s, e) for s, e in regions if s < start + image_size and e > start
    ]
    return mem, regions, static_regions


def read_u32(mem, address):
    """Read a 4-byte whole number (= a pointer in a 32-bit game)."""
    return int.from_bytes(os.pread(mem, 4, address), "little")


# if i forgotr it liek looking for somethign in room that u know it is
def follow(mem, path):
    # we here
    address = path[0]
    # read the note how far to go from here and the walt to it
    for offset in path[1:]:
        # add how far to here
        address = read_u32(mem, address) + offset
    # returns final addres
    return address


# this is like if u dont know the room but know its somewhere in the hause(mem)
def find_pointers(snapshot, target, max_offset=0x1000):
    hits = []
    for start, data in snapshot.items():
        values = np.frombuffer(data, dtype="<u4", count=len(data) // 4)
        # if values <= than the thing u looking and
        # values >= than the thing u looking - the distance u willing to look
        mask = (values <= target) & (values >= target - max_offset)
        # if mask is true then add to hits the address and the value
        for i in np.flatnonzero(mask):
            # where it is, where it says
            hits.append((start + int(i) * 4, int(values[i])))
    # return genelar list of where it is and what it says
    return hits


# its like building a map of the tresure
def pointer_scan(heap, static, target):
    paths = []
    # where the card lies and the room door it names
    for where, value in find_pointers(static, target):
        # where, door to tresure distance
        paths.append([where, target - value])
    # find all the cards that say where the tresure is
    heap_hits = find_pointers(heap, target)
    # sort them by how close they are to the tresure
    heap_hits.sort(key=lambda hit: target - hit[1])
    # take 300 cards
    for h_where, h_value in heap_hits[:300]:
        # is there a card at reception (fixed place) that points to this card's office?
        for s_where, s_value in find_pointers(static, h_where):
            # map: reception card -> walk to the office card -> follow it -> walk to the treasure
            paths.append([s_where, h_where - s_value, target - h_value])
    return paths


def wait(text, seconds=4):
    print(text)
    subprocess.run(["notify-send", "-t", str(seconds * 1000), "HMBot", text])
    for s in range(seconds, 0, -1):
        print(f"  {s}...", end="\r", flush=True)
        time.sleep(1)
    print("  scanning!")


def safe_read(mem, address):
    try:
        return read_double(mem, address)
    except OSError:
        return math.nan


def nearby(mem, x_addr):
    # look in range(-64, 72, 8)
    return {off: safe_read(mem, x_addr + off) for off in range(-0x40, 0x48, 8)}


def save_address(name, value):
    # Store a path [..] or a number under `name` in addresses.json (as hex text).
    data = {}
    if os.path.exists(ADDRESS_FILE):
        with open(ADDRESS_FILE) as f:
            data = json.load(f)
    data[name] = [hex(v) for v in value] if isinstance(value, list) else hex(value)
    with open(ADDRESS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_address(name):
    # Read one entry back from addresses.json (hex text -> numbers).
    with open(ADDRESS_FILE) as f:
        value = json.load(f)[name]
    return [int(v, 16) for v in value] if isinstance(value, list) else int(value, 16)


def table_objects(mem):
    # Every object in the game's object table: {table entry address: (x, y)}.
    data = os.pread(mem, TABLE_END - TABLE_START, TABLE_START)
    objects = {}
    for i in range(0, len(data) - 3, 4):
        ptr = int.from_bytes(data[i : i + 4], "little")
        if ptr == 0:
            continue
        try:
            x = read_double(mem, ptr + X_OFF)
            y = read_double(mem, ptr + Y_OFF)
        except OSError:
            continue
        if 0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000:
            objects[TABLE_START + i] = (x, y)
    return objects


def moved(before, after):
    # Table entries whose position changed between two looks.
    return {e for e in before if e in after and before[e] != after[e]}


def auto_setup(mem):
    wait("Stand still, hands off", 5)
    a = table_objects(mem)
    wait("Move the MOUSE somewhere else (don't walk)")
    b = table_objects(mem)
    mouse = moved(a, b)
    wait("WALK a bit (don't touch the mouse)")
    c = table_objects(mem)
    walk = moved(b, c)
    # moves when you walk, NOT when you move the mouse
    players = walk - mouse
    print(f"objects in table: {len(a)}")
    print(f"moved with mouse: {[hex(e) for e in sorted(mouse)]}")
    print(f"moved with walking: {[hex(e) for e in sorted(walk)]}")
    print(f"known entries seen? you: {0xBEC91C in a}, crosshair: {0xBECBD8 in a}")
    if not players or not mouse:
        raise SystemExit(
            "Setup failed: couldn't tell you and the crosshair apart. Run it again."
        )
    player = min(players)
    wait("Put the cursor ON your character and hold it there", 5)
    d = table_objects(mem)
    if player not in d:
        raise SystemExit("Setup failed: lost the player. Run it again.")
    px, py = d[player]
    crosshair = min(
        mouse & d.keys(), key=lambda e: abs(d[e][0] - px) + abs(d[e][1] - py)
    )
    save_address("player", [player, X_OFF])
    save_address("crosshair", [crosshair, X_OFF])
    save_address("y_offset", Y_OFF - X_OFF)
    print(f">>> player = {hex(player)}, crosshair = {hex(crosshair)}  (saved)")


# Same as table_objects, but keyed by the object itself instead of its seat (seats get shuffled).
def table_records(mem):
    """Every object in the table: {record address: (x, y)}."""
    data = os.pread(mem, TABLE_END - TABLE_START, TABLE_START)
    records = {}
    for i in range(0, len(data) - 3, 4):
        record = int.from_bytes(data[i : i + 4], "little")
        if record == 0:
            continue
        try:
            x = read_double(mem, record + X_OFF)
            y = read_double(mem, record + Y_OFF)
        except OSError:
            continue
        if 0.01 < abs(x) < 100000 and 0.01 < abs(y) < 100000:
            records[record] = (x, y)
    return records


def read_kind(mem, record, where, offset):
    """
    Read a 4-byte number from an object ("which number is in this pocket?").
    #   record = the card's address (the table points to cards; cards sit on the shelf every 0xB8 bytes)
    #   where  = 0 -> read inside the card itself (0xB8 bytes: +0x14 layer, +0x50 X, +0x58 Y)
    #            1 -> read inside the folder: the card's first 4 bytes hold the folder's address (0x6D0 bytes)
    #   offset = how many bytes from the start of the card / folder ("which pocket")
    # Examples:
       read_kind(mem, card, 0, 0x14) -> the card's layer (6 enemy, 0xa6 sitting enemy, 0x2C you...)
       read_kind(mem, card, 1, 0x10) -> the folder's picture number (0x47 you, 0xA5 crosshair...)
     Junk address -> OSError.
    """
    base = record if where == 0 else read_u32(mem, record)
    return read_u32(mem, base + offset)
