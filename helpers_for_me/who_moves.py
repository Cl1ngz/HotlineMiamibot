from memory import X_OFF, attach, first_scan, narrow, read_double, table_records, wait

mem, regions, static_regions = attach()

# 1. zdjęcie całej pamięci -> idziesz w PRAWO -> drugie zdjęcie: zostają liczby, które UROSŁY
candidates = first_scan(mem, regions, "Idź w PRAWO", ask=wait)
print("po pierwszym skanie:", len(candidates))

# 2. zawężanie: każde polecenie wykonujesz w grze w czasie odliczania
for text, how in [
    ("Idź w LEWO", "down"),
    ("STÓJ", "same"),
    ("Idź w PRAWO", "up"),
    ("Idź w LEWO", "down"),
    ("STÓJ", "same"),
]:
    wait(text)
    candidates = narrow(mem, candidates, how)
    print(f"po '{text}':", len(candidates))

# 3. kto został? i czy jego karta jest w naszej tabeli?
cards = table_records(mem)
for addr, x in list(candidates.items())[:20]:
    y = read_double(mem, addr + 8)
    print(
        hex(addr),
        " x =",
        round(x),
        " y =",
        round(y),
        "  karta w tabeli?",
        (addr - X_OFF) in cards,
    )
