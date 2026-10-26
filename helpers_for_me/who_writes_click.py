# https://github.com/Cl1ngz/HotlineMiamibot
# helpers_for_me/who_writes_click.py - WHICH INSTRUCTION in the game's code writes the click byte?
#
# The game wipes our 1 in the click byte (0x132fc53) every frame. Somewhere in its code there's one
# instruction that does it. gdb (a debugger) can set a "watchpoint" on the byte: the CPU itself stops the
# game the moment anything writes there, and gdb shows where in the code it happened.
# This only LOOKS - it changes nothing. When it's done, gdb lets go and the game runs on.
#
#   sudo pacman -S gdb                               (once)
#   python -m helpers_for_me.who_writes_click        (be in a level; when it says so, CLICK once in the game)
#   if it says "ptrace: Operation not permitted":  sudo .venv/bin/python -m helpers_for_me.who_writes_click
import shutil
import subprocess

from core.memory import find_game

CLICK = 0x132FC53  # the "left button held" byte from find_click

if shutil.which("gdb") is None:
    raise SystemExit("gdb isn't installed: sudo pacman -S gdb")
game = find_game()
if game is None:
    raise SystemExit("Hotline Miami isn't running")
pid = game[0]

commands = [
    "set pagination off",
    "set confirm off",
    # Wine uses signals for its own work all the time - let them through, don't stop on them
    "handle all nostop noprint pass",
    # stop the game the moment anything WRITES the click byte
    f"watch -l *(unsigned char *){CLICK:#x}",
    "continue",
    # the CPU stops right AFTER the writing instruction - show where we are and the bytes around it
    "info registers",
    "x/48xb $pc-24",
    "detach",
    "quit",
]
args = ["gdb", "-q", "-p", str(pid), "-batch"]
for command in commands:
    args += ["-ex", command]

print(f"attaching to the game (pid {pid}) - it freezes for a second.")
print(">>> when you see 'Continuing.' below: go to the game and CLICK ONCE <<<\n")
subprocess.run(args)
print("\nPaste me everything above - especially the lines after 'Hardware watchpoint' and the bytes (0x.. 0x.. ...).")
