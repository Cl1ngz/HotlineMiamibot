import time

from enemies import copy_memory
from memory import X_OFF, attach, read_kind, table_records

mem, regions, static_regions = attach()


def my_cards():
    """Karty wszystkich obiektów z numerem 0x2C (czyli Ciebie przed dobiciem)."""
    # DZIURA 1: warunek "ma numer 0x2C"
    return [r for r in table_records(mem) if read_kind(mem, r, 0, 0x14) == 0x2C]


# 1. STAN A: czekamy, aż będzie dokładnie jeden Ty, i robimy kopię Twojej karty + folderu
print("Czekam na stan A (ja: 1)...")
while len(my_cards()) != 1:
    time.sleep(0.2)
me_a = my_cards()[0]
copy_a = copy_memory(mem, [me_a])[me_a]  # (bajty karty, bajty folderu)
print(f"Mam kopię A (karta {hex(me_a)}). Teraz dobij kogoś!")

# 2. STAN B: czekamy, aż przez ~1 sekundę NIE będzie nikogo z 0x2C (5 sprawdzeń z rzędu)
gone = 0
while gone < 5:
    if len(my_cards()) == 0:
        gone += 1
    else:
        gone = 0  # ktoś z 0x2C znowu jest -> liczymy od nowa
    time.sleep(0.2)
time.sleep(0.5)
objects_b = table_records(mem)  # {karta: (x, y)} wszystkich obiektów teraz
copies_b = copy_memory(mem, objects_b)  # kopie wszystkich obiektów teraz
print(f"Mam kopię B ({len(copies_b)} obiektów). Szukam...")
print("stara karta nadal w tabeli?", me_a in objects_b)

# 3. PORÓWNANIE: miejsce, w którym Twoja wartość z A jest w B u DOKŁADNIE JEDNEGO obiektu
candidates = []
for where in (0, 1):
    for offset in range(0, len(copy_a[where]), 4):
        if where == 0 and X_OFF <= offset < X_OFF + 16:
            continue  # X i Y pomijamy
        value_a = int.from_bytes(copy_a[where][offset : offset + 4], "little")
        # DZIURA 2
        owners = [
            r
            for r, data in copies_b.items()
            if int.from_bytes(data[where][offset : offset + 4], "little") == value_a
        ]
        if len(owners) == 1:
            candidates.append((where, offset, value_a, owners[0]))

candidates.sort(
    key=lambda c: (not 0 <= c[2] < 10000, c[0], c[1])
)  # małe liczby na górę
for where, offset, value, owner in candidates[:15]:
    x, y = objects_b[owner]
    print(
        f"{('karta', 'folder')[where]:6} {hex(offset):>6}  wartość {hex(value):>10}  ma ją tylko: {hex(owner)} na ({x:.0f}, {y:.0f})"
    )
