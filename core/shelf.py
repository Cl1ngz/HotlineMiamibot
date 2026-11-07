# https://github.com/Cl1ngz/HotlineMiamibot
# core/shelf.py - a photo of the game's memory for ONE frame (a library)
#
# Why: every read_u32 / read_double / read_kind was one os.pread = one trip to the Linux kernel.
# see_timer on floor 1: ~9 800 of them per scan (23 ms), with the walls ~19 000 (40 ms) - one frame is 16.7 ms.
# But memory comes in 4 KB pages, and the whole shelf is only ~25 of them.
#
# A Shelf reads a page from the game the first time someone asks for it, keeps it, and answers every later
# read from it. So a new photo costs nothing until you use it, and the shelf costs ~25 kernel trips, not 19 000.
# Everything in one photo is from the same moment - a card can't move in the middle of a frame any more.
# Pass it wherever a `mem` goes - core/memory.py's read functions take both:
#
#   shelf = Shelf(mem)                  a new photo (empty - pages come in as they're needed)
#   find_me_card(shelf)                 the same function as always, just no kernel trips after the first
#   is_enemy(shelf, card, rules)        ...
#   shelf.records                       table_records(shelf) - read once, then remembered
#   shelf.cards                         shelf_cards(shelf, shelf.records) - read once, then remembered
#
# Take a NEW photo every frame: the game moves on, the photo doesn't.
# Only READ through it - writing (hands.py) always goes to the real mem_rw.
import os

from .enemies import shelf_cards
from .memory import table_records

PAGE = 0x1000  # 4 KB - the size of one memory page


class Shelf:
    """One frame's photo of the game's memory. Use it as `mem` for reading."""

    def __init__(self, mem):
        self.mem = mem  # the real game memory (the open /proc/<pid>/mem)
        self.pages = {}  # page address -> its 4096 bytes, or None (that page can't be read)
        self._records = None
        self._cards = None

    def read(self, size, address):
        """size bytes from address - like os.pread, but every page comes from the game only once.
        A page that can't be read -> OSError, like the real thing. Fewer bytes near the end of readable memory."""
        offset = address % PAGE
        start = address - offset
        page = self.pages[start] if start in self.pages else self.page(start)
        if page is not None and offset + size <= PAGE:
            return page[offset : offset + size]  # the usual case: all of it in one page
        # the rare case: across the end of a page, or a page that can't be read
        data = b""
        while size > 0:
            start = address - address % PAGE
            page = self.page(start)
            if page is None:
                if data:
                    return data  # the readable part (read_double sees it's too short)
                raise OSError(f"can't read {hex(address)}")
            take = min(size, start + PAGE - address)
            data += page[address - start : address - start + take]
            address += take
            size -= take
        return data

    def page(self, start):
        """The 4096 bytes of the page at start (read from the game the first time), or None."""
        if start not in self.pages:
            try:
                data = os.pread(self.mem, PAGE, start)
            except OSError:
                data = b""
            self.pages[start] = data if len(data) == PAGE else None
        return self.pages[start]

    # @property: shelf.records looks like a plain field, but Python runs this function when you read it.
    # The first time it reads the table, then it just gives back what it remembered.
    @property
    def records(self):
        """{card: (x, y)} of the table - table_records, but only once per photo."""
        if self._records is None:
            self._records = table_records(self)
        return self._records

    @property
    def cards(self):
        """Every card on the shelf at a real position - shelf_cards, but only once per photo."""
        if self._cards is None:
            self._cards = shelf_cards(self, self.records)
        return self._cards

