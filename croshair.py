from memory import attach, first_scan, narrow, wait

mem, regions, static_regions = attach()

wait("Put the mouse on the LEFT side of the game", 6)
candidates = first_scan(mem, regions, "Now the RIGHT side, keep it there", ask=wait)
print(len(candidates), "after first scan")

for r in range(2):
    wait("Mouse to the LEFT side, keep it there")
    candidates = narrow(mem, candidates, "down")
    wait("Mouse to the RIGHT side, keep it there")
    candidates = narrow(mem, candidates, "up")
    wait("Don't touch anything")
    candidates = narrow(mem, candidates, "same")
    print(f"round {r + 1}: {len(candidates)} left")

for a, v in candidates.items():
    print(hex(a), round(v, 1))
