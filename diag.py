from memory import attach, follow, read_double, read_u32

mem, regions, static_regions = attach()

print("--- table entries (what each card points to) ---")
for entry in range(0xBEC8C8, 0xBEC8C8 + 0x60, 4):
    print(hex(entry), "->", hex(read_u32(mem, entry)))

print("--- known paths ---")
for path in ([0xBEC8C8, 0xF68], [0xBEC91C, 0x50], [0xBECB84, 0xF68], [0xBECBD8, 0x50]):
    try:
        a = follow(mem, path)
        print(
            [hex(v) for v in path],
            "->",
            hex(a),
            "x =",
            read_double(mem, a),
            "y =",
            read_double(mem, a + 8),
        )
    except OSError as e:
        print([hex(v) for v in path], "-> can't read:", e)
