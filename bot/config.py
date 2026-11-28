# https://github.com/Cl1ngz/HotlineMiamibot
# bot/config.py - the numbers more than one part of the bot uses (the rest live next to the code that uses them)

# the game runs at 60 frames per second, no point going faster
FPS = 60

# an enemy this close gets hit (the logs: every swing at 23-39 killed, one even at 45)
REACH = 38
# a gun fires at an enemy you see this close (bullets fly further - lock-on sees 250)
GUN_RANGE = 200
# an empty gun gets thrown at an enemy this close (it knocks him down)
THROW_RANGE = 150
# your card +0xA0 when your hands are empty: at rest / punching
EMPTY_HANDS = (0x1, 0x85)
# this close to a weapon -> right click picks it up (the press test worked at 13)
GRAB_REACH = 13
# empty hands: the right button from this close (a press too far does nothing). The game takes a weapon from
# further than GRAB_REACH (the logs: standing still, taken from 16, 23, 28, 29 away) - and by a wall you can't
# walk closer (the logs: 2 s pushing A 16 from a pipe, the button never pressed)
GRAB_EMPTY = 24
# you moved less than this: you stand still (a dialogue holds you, or you push at something)
MOVED_A_BIT = 2
# a gun with ammo beats every melee weapon (ranks 1-4 in weapon_names.json); an empty one is worth nothing
GUN_RANK = 100
