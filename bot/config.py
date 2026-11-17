# https://github.com/Cl1ngz/HotlineMiamibot
# bot/config.py - the numbers more than one part of the bot uses (the rest live next to the code that uses them)

# the game runs at 60 frames per second, no point going faster
FPS = 60

# an enemy this close gets hit (the logs: every swing at 23-39 killed, one even at 45)
REACH = 38
# your card +0xA0 when your hands are empty: at rest / punching
EMPTY_HANDS = (0x1, 0x85)
# this close to a weapon -> right click picks it up (the press test worked at 13)
GRAB_REACH = 10
# you moved less than this: you stand still (a dialogue holds you, or you push at something)
MOVED_A_BIT = 2
