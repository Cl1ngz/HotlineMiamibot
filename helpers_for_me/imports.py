# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/imports.py - which Windows functions does the game use? (its import table)
#
# A Windows program doesn't contain the system's functions - it has a LIST of the ones it needs
# ("from user32.dll: GetCursorPos, GetKeyState..."). When the game starts, Windows (here: Wine) fills in
# where each function really lives - that filled-in list is the IAT (import address table).
# The game asks for the mouse buttons every frame through one of these functions. This prints the list,
# and marks the ones that read the mouse / keyboard.
#
#   python -m helpers_for_me.imports                  (the game just has to run)
#   python -m helpers_for_me.imports USER32.dll       (... and list every function from that one library)
import os
import sys

from core.memory import attach, find_game, find_game_file

# functions a game can use to read the mouse buttons / keyboard
INPUT = {
    "GetAsyncKeyState", "GetKeyState", "GetKeyboardState", "GetCursorPos", "ScreenToClient",
    "DirectInput8Create", "DirectInputCreateA", "DirectInputCreateW", "DirectInputCreateEx",
    "XInputGetState", "RegisterRawInputDevices", "GetRawInputData", "GetRawInputBuffer",
    "PeekMessageA", "PeekMessageW", "GetMessageA", "GetMessageW", "GetMouseMovePointsEx",
}
show_all = sys.argv[1].lower() if len(sys.argv) > 1 else None  # a library to list in full

mem, regions, static_regions = attach()
pid = find_game()[0]
exe = os.readlink(f"/proc/{pid}/exe")
wine = "wine" in os.path.basename(exe) or "preloader" in os.path.basename(exe)
base, path = find_game_file(pid, exe, wine)
if base is None:
    raise SystemExit("couldn't find the game file in memory")


def u16(address):
    return int.from_bytes(os.pread(mem, 2, address), "little")


def u32(address):
    return int.from_bytes(os.pread(mem, 4, address), "little")


def text(address):
    """A 0-terminated string."""
    data = os.pread(mem, 128, address)
    return data.split(b"\0")[0].decode("ascii", "replace")


# the PE header: "MZ" at the start, the offset of "PE" at +0x3C
pe = base + u32(base + 0x3C)
if os.pread(mem, 4, pe) != b"PE\0\0":
    raise SystemExit("no PE header - is this the game?")
optional = pe + 24
if u16(optional) != 0x10B:
    raise SystemExit("not a 32-bit program?")
imports_rva = u32(optional + 96 + 8)  # data directory 1 = the import table
print(f"game file at {base:#x}, import table at {base + imports_rva:#x}\n")

found = []
descriptor = base + imports_rva
while True:
    names_rva, _, _, dll_rva, iat_rva = (u32(descriptor + 4 * i) for i in range(5))
    if dll_rva == 0:
        break  # an empty entry ends the list
    dll = text(base + dll_rva)
    functions = []
    list_rva = names_rva or iat_rva
    i = 0
    while True:
        entry = u32(base + list_rva + 4 * i)
        if entry == 0:
            break
        name = f"#{entry & 0xFFFF}" if entry & 0x80000000 else text(base + entry + 2)  # by number or by name
        slot = base + iat_rva + 4 * i  # where the game keeps this function's address
        functions.append(name)
        if name in INPUT:
            found.append((dll, name, slot, u32(slot)))
        i += 1
    print(f"{dll}: {len(functions)} functions")
    if dll.lower() == show_all:
        for name in sorted(functions):
            print(f"    {name}")
    descriptor += 20

print("\nfunctions that can read the mouse / keyboard:")
for dll, name, slot, target in found:
    print(f"  {dll:14} {name:26} the game finds it at {slot:#x} (it points to {target:#x})")
if not found:
    print("  none in the list - the game may load them some other way")
