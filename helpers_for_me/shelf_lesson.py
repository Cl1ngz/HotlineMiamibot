# Bug recreation: the game shuffles the slots and reuses the cards, so the old addresses.json is no longer valid.
# table: slot address -> card address
# cards: card address -> what is inside that card

table_p1 = {0xBEC918: 0x2421408, 0xBEC91C: 0x242A818, 0xBEC920: 0x24244E8}
cards_p1 = {
    0x2421408: "wall (192, 64)",
    0x242A818: "YOU (320, 472)",
    0x24244E8: "wall (272, 368)",
}

# floor 2: the game shuffled the slots and reused the cards
table_p2 = {0xBEC918: 0x242A818, 0xBEC91C: 0x2421408, 0xBEC920: 0x24244E8}
cards_p2 = {
    0x2421408: "wall (272, 368)",
    0x242A818: "wall (192, 64)",
    0x24244E8: "YOU (150, 240)",
}


def via_slot(table, cards, slot):
    """The old addresses.json way: slot -> card -> contents."""
    for k, v in table.items():
        if k == slot:
            return cards.get(v, None)
    # return cards.get(table.get(slot, None), None)


def via_card(cards, card):
    """Remember the card itself: card -> contents."""
    return cards.get(card, None)


OLD_SLOT = 0xBEC91C
OLD_CARD = 0x242A818

print(f"via_slot: {via_slot(table_p1, cards_p1, OLD_SLOT)}")
print(f"via_card: {via_card(cards_p1, OLD_CARD)}")
print(f"via_slot: {via_slot(table_p2, cards_p2, OLD_SLOT)}")
print(f"via_card: {via_card(cards_p2, OLD_CARD)}")

# Notes 1
# slot lied because the slot 0xBEC91C used to point to the card 0x242A818, which was YOU. Now it points  to a wall.
# The card 0x242A818 is no longer YOU, it's a wall. The game shuffled the slots and reused the cards, so the old addresses.json is no longer valid.
# X_OFF = 0x50   starts at 0x50 it takes 8 bytes
# Y_OFF = (0x58) 8 bytes offset because the game stores X and Y as doubles and x took 8 bytes

# NOTES - step 2
# What +0x14 really is: the draw layer. It says how the game draws the object, not what it is.
# Why dead enemies vanished from the radar: when an enemy dies, the game moves it to layer -100
#   (things lying on the floor). The enemy rule only looks for layer 6, so it stops matching.
# Why one enemy rule doesn't work on every floor: each floor can give enemies a different layer
#   (6 on one floor, 0xa6 and 0x3b on Crackdown floor 2).


# === STEP 3: value scan, recreated ===
# memory: address -> number at that address, at 3 moments
start = {0x100: 300.0, 0x200: 64.0, 0x300: 200.0, 0x400: 10.0}
after_left = {0x100: 280.0, 0x200: 64.0, 0x300: 190.0, 0x400: 12.0}
after_stand = {0x100: 280.0, 0x200: 64.0, 0x300: 180.0, 0x400: 14.0}

candidates = list(
    start
)  # list of a dict = its keys: every address is a suspect at first

# I walked LEFT -> keep only the addresses whose number went DOWN
for addr in list(candidates):
    if not (start[addr] > after_left[addr]):
        candidates.remove(addr)

# I STOOD still -> keep only the addresses whose number stayed the SAME
for addr in list(candidates):
    if not (after_left[addr] == after_stand[addr]):
        candidates.remove(addr)

print([hex(a) for a in candidates])
# After an execution I vanish from the table, but NOT from memory: my card still exists and moves.
# So the table is not a list of ALL objects.
# NOTES - step 3
# +0x14 contains draw layer me=0x2C wall = 9 eneimie = 6

# why list not normal iter
# nums = [1, 2, 2, 3]
# i = 0
# print("index value list")
# for n in nums:
#     if n == 2:
#         nums.remove(n)
#         print(f"Removed {n}")
#     print(f"i={i} n={n}, nums={nums}")
#     i += 1
# print(nums)
#
#
# print("\n\n\n")
# print("index value list")
# nums = [1, 2, 2, 3]
# i = 0
# for n in list(nums):
#     if n == 2:
#         nums.remove(n)
#         print(f"Removed {n}")
#     print(f"i={i} n={n}, nums={nums}")
#     i += 1
# print(nums)


# croshair for find me method
# >>>
# ... import math
# ... found = [(300, 200), (388, 160)]
# ... aims = [(310, 190)]
# ... math.dist(found[0], aims[0])
# ... math.dist(found[1], aims[0])
# ... min(found, key=lambda me: min(math.dist(me, aim) for aim in aims))
# ...
# (300, 200)
# >>> aims = [(310, 190), (390, 150)]
# ... min(found, key=lambda me: min(math.dist(me, aim) for aim in aims))
# ...
# (388, 160)
