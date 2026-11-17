# https://github.com/Cl1ngz/HotlineMiamibot
# hmbot.py - the bot: one loop that sees, decides and acts, every frame
#
#   python hmbot.py         run until Ctrl+C
#   python hmbot.py 30      stop by itself after 30 seconds
#
# every frame:   let_go -> see -> decide -> act -> walk -> wait_frame
#   see()      reads the game into Eyes             (OSError = no player -> pause() instead)   bot/see.py
#   decide()   looks ONLY at Eyes and returns a Plan (never reads or writes the game)          bot/decide.py
#   act()      the buttons (Hands)                                                             bot/act.py
#   walk()     the legs (Legs)                                                                 bot/walk.py
# what lives between frames: bot/boxes.py. Set once at the start (game.mem, game.rules...): bot/game.py
import faulthandler
import math
import signal
import sys
import time

from bot import game
from bot.act import act, click, idle_tap, let_go
from bot.boxes import Eyes, Hands, Legs, Plan
from bot.config import FPS
from bot.decide import decide
from bot.see import see
from bot.share import SHARE_EVERY, share, status
from bot.walk import walk
from core import lockon
from core.enemies import find_aim
from core.hands import (
    KEY_SPACE,
    find_look,
    key_up,
    look_at,
    release_left,
    release_right,
)
from core.legs import hold


def pause(err, eyes, hands, legs, now):
    """No player this frame. Sitting on an enemy -> keep hitting. Anything else -> forget the floor and wait."""
    if now < hands.mounted_until:
        # sitting on him: we can't see you, but we know what's going on - keep hitting
        if hands.release_at is None and now >= hands.next_swing:
            click(hands, now)
        status("MOUNTED - hitting")
        time.sleep(1 / FPS)  # not 0.2 s like a pause - every frame counts here
    else:
        # a new floor, the menu, the score screen, a title card, or you sit on an enemy: forget the old floor
        lockon.reset()
        eyes.stairs = None
        eyes.car = None
        # new thing forget old
        legs.learned.clear()
        # look at the new floor and new walls
        eyes.next_scan = 0
        eyes.next_walls = 0
        status(f"{err} (paused)")
        # the score screen / a title card: no player, nothing else to do - tap through it
        idle_tap(hands, now)
        time.sleep(0.2)
    legs.held = hold(game.mem, game.mem_rw, set(), legs.held)


def wait_frame(eyes, now):
    """Wait for the next frame - and keep the crosshair on the target meanwhile."""
    frame_end = now + 1 / FPS
    aim = eyes.target is not None
    while time.monotonic() < frame_end:
        if aim:
            try:
                look_at(game.mem, game.mem_rw, eyes.spots[eyes.target])
            except OSError:
                # can't write right now - stop for this frame, the next one tries again
                aim = False
        # don't burn CPU while waiting for the next frame
        time.sleep(0.002)


# --- start ---

game.load()
# stuck? in another terminal:  kill -USR1 $(pgrep -f hmbot.py)   -> where it is right now goes to stuck.txt
stuck_file = open("stuck.txt", "w")
faulthandler.register(signal.SIGUSR1, file=stuck_file)
stop_at = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else math.inf

eyes, hands, legs = Eyes(), Hands(), Legs()
slowest = 0
# when to tell the radar again
next_share = 0
try:
    game.get_ready()
    while time.monotonic() < stop_at:
        now = time.monotonic()
        let_go(hands, now)
        try:
            see(eyes, now)
        except OSError as err:
            pause(err, eyes, hands, legs, now)
            if now >= next_share:
                share(Plan(text=f"{err} (paused)"), eyes, legs)
                next_share = now + SHARE_EVERY
            # only the loop can skip the rest of the frame - see() can't
            continue
        plan = decide(eyes, hands, now)
        try:
            act(plan, eyes, hands, now)
            walk(plan, eyes, legs, now)
        except OSError as err:
            # a write didn't reach the game: the look chain may lead somewhere else now - pick it again
            if find_look(game.mem, find_aim(game.mem)) is None:
                status(f"can't write to the game: {err}")
            time.sleep(1 / FPS)
            continue
        status(plan.text)
        if now >= next_share:
            share(plan, eyes, legs)
            next_share = now + SHARE_EVERY

        # ms spent on see + decide + act + walk in this loop
        work = (time.monotonic() - now) * 1000
        slowest = max(slowest, work)
        if work > 1000 / FPS:
            print(f"\nslow loop: {work:.1f} ms")
        wait_frame(eyes, now)
except KeyboardInterrupt:
    pass
finally:
    print("\nbye!")
    release_left(game.mem, game.mem_rw)
    release_right(game.mem, game.mem_rw)
    key_up(game.mem, game.mem_rw, KEY_SPACE)
    hold(game.mem, game.mem_rw, set(), legs.held)
    print(f"slowest loop: {slowest:.1f} ms")
