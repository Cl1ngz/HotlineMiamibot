import time

from memory import attach, read_kind, table_records

mem, regions, static_regions = attach()

first = table_records(mem)
print("CHODŹ przez 2 sekundy!")
time.sleep(4)
now = table_records(mem)
for record, (x, y) in now.items():
    # DZIURA: karta była w first ORAZ jej pozycja się zmieniła (tak jak w kinds.py)
    if record in first and now[record] != first[record]:
        try:
            print(
                hex(record),
                "na",
                round(x),
                round(y),
                "  +0x14:",
                hex(read_kind(mem, record, 0, 0x14)),
                "  folder+0x10:",
                hex(read_kind(mem, record, 1, 0x10)),
            )
        except OSError:
            pass
