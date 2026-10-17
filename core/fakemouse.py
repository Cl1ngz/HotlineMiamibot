# https://github.com/Cl1ngz/HotlineMiamibot
# mouse the bot holds, made with kernel uinput
# game thin and hyp[r] its second mose
import time

from evdev import UInput, ecodes

FIX = """
Fix (one time):
  sudo modprobe uinput
  echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/60-hmbot-uinput.rules
  sudo udevadm control --reload-rules && sudo udevadm trigger
then log out and back in."""

device = None


def start():
    global device
    try:
        device = UInput(
            {
                ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y],
                ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT],
            },
            name="hmbot-mouse",
        )
    except Exception as err:
        # no permission for /dev/uinput
        raise SystemExit(f"can't make the fake mouse: {err}\n{FIX}")
    time.sleep(1)


def move(dx, dy):
    # right/down == positive
    device.write(ecodes.EV_REL, ecodes.REL_X, dx)
    device.write(ecodes.EV_REL, ecodes.REL_Y, dy)
    device.syn()


def click(button=ecodes.BTN_LEFT):
    # press
    device.write(ecodes.EV_KEY, button, 1)
    device.syn()
    time.sleep(0.02)
    # release
    device.write(ecodes.EV_KEY, button, 0)
    device.syn()


def stop():
    if device:
        device.close()
