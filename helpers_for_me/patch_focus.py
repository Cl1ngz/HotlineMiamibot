# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/patch_focus.py - the first patch in the game's CODE: "behave as if you always had the focus"
#
# find_calls GetFocus showed the only place the game asks Windows "who has the focus?":
#   0x407d97: call [GetFocus]
#   0x407d9d: cmp eax, esi          is it our window?
#   0x407d9f: jne 0x407dec          not us -> jump away, skip the input part
# The jne is 2 bytes: 75 4B. Two NOPs (90 90, "do nothing") instead -> the jump never happens.
# It's undone with "off". The patch lives only in the running game's memory - the file on disk isn't touched,
# so restarting the game undoes it too.
#
#   python -m helpers_for_me.patch_focus on       (patch)
#   python -m helpers_for_me.patch_focus off      (put the original bytes back)
#   python -m helpers_for_me.patch_focus          (just show what's there now)
import os
import sys

from core.memory import attach, open_rw

ADDRESS = 0x407D9F
ORIGINAL = bytes([0x75, 0x4B])  # jne 0x407dec
PATCHED = bytes([0x90, 0x90])  # nop, nop

mem, regions, static_regions = attach()
now = os.pread(mem, 2, ADDRESS)
state = "ORIGINAL (jne)" if now == ORIGINAL else "PATCHED (nop nop)" if now == PATCHED else "something else!"
print(f"{ADDRESS:#x}: {now.hex(' ')}   -> {state}")
if now not in (ORIGINAL, PATCHED):
    raise SystemExit("unexpected bytes - a different game version? not touching anything")

wish = sys.argv[1] if len(sys.argv) > 1 else None
if wish not in ("on", "off"):
    raise SystemExit()
new = PATCHED if wish == "on" else ORIGINAL
if now == new:
    raise SystemExit(f"already {wish}")

mem_rw = open_rw()
try:
    os.pwrite(mem_rw, new, ADDRESS)
except OSError as error:
    raise SystemExit(f"the system refused to write into the game's code: {error}")
check = os.pread(mem, 2, ADDRESS)
print(f"{ADDRESS:#x}: {check.hex(' ')}   -> {'done' if check == new else 'the write did NOT stick!'}")
