# https://github.com/Cl1ngz/HotlineMiamibot
# core/shelf.py - copy of game memory for one frame
# every 4 KB page is read from the game only once, then bytes come from the copy (~25 reads, not ~19 000)
# use it like mem: shelf = Shelf(mem), then find_me_card(shelf), is_enemy(shelf, ...)
# new one every frame, only for reading (writing goes to mem_rw)
import os

from .enemies import shelf_cards
from .memory import table_records

# 4 KB  page
PAGE = 0x1000


class Shelf:
    """copy of game memory for one frame - use it as mem"""

    def __init__(self, mem):
        self.mem = mem  # real game memory
        self.pages = {}  # page start -> 4096 bytes none=cant read
        self._records = None
        self._cards = None

    def read(self, size, address):
        """size bytes from address, like os.pread but each page read only once"""
        offset = address % PAGE
        start = address - offset
        page = self.pages[start] if start in self.pages else self.page(start)
        if page is not None and offset + size <= PAGE:
            # all bytes in one page
            return page[offset : offset + size]
        # bytes go over the page end, or page can't be read
        data = b""
        while size > 0:
            start = address - address % PAGE
            page = self.page(start)
            if page is None:
                if data:
                    # retur what can be read
                    return data
                raise OSError(f"can't read {hex(address)}")
            take = min(size, start + PAGE - address)
            data += page[address - start : address - start + take]
            address += take
            size -= take
        return data

    def page(self, start):
        """4096 bytes of the page at start (from game only first time), or None"""
        if start not in self.pages:
            try:
                data = os.pread(self.mem, PAGE, start)
            except OSError:
                data = b""
            self.pages[start] = data if len(data) == PAGE else None
        return self.pages[start]

    # @property: shelf.records works like a field but runs this - first time reads, then remembers
    @property
    def records(self):
        """table_records, only once per frame"""
        if self._records is None:
            self._records = table_records(self)
        return self._records

    @property
    def cards(self):
        """shelf_cards, only once per frame"""
        if self._cards is None:
            self._cards = shelf_cards(self, self.records)
        return self._cards
