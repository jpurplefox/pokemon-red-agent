"""Field menus — teaching HMs and using field moves like CUT (SRP).

Drives the START menu flows mapped on the real game:

  teach:  START > ITEM > (HM) > USE > "Teach X to a POKéMON?" YES
          > party (ABLE / NOT ABLE) > [4 moves: "Delete an older move?" YES
          > "Which move should be forgotten?" > move] > "... learned X!"
  use:    START > POKéMON > slot > field move > "... hacked away with CUT!"
"""

from data.constants import (
    ADDR_BAG_ITEMS, ADDR_CURRENT_MENU, ADDR_LIST_SCROLL_OFFSET, ADDR_NUM_BAG_ITEMS,
    ADDR_PARTY_COUNT, ADDR_PARTY_MONS, ADDR_TILEMAP, PARTY_MON_MOVES,
    PARTY_MON_SIZE, POKEMON_CHARMAP,
)
from data.pokemon_data import MOVE_NAMES

TILE_CURSOR = 0xED


class FieldMoves:
    def __init__(self, pyboy, screen, menu):
        self._pyboy = pyboy
        self._screen = screen
        self._menu = menu

    # ------------------------------------------------------------------
    # Teaching an HM
    # ------------------------------------------------------------------

    def teach_hm(self, item_id: int, slot: int, forget_index: int | None) -> str:
        """Teach the HM in the bag to party slot; returns the game's text.

        forget_index is the move to replace when the Pokémon already knows
        four (0-3), None otherwise.
        """
        mem = self._pyboy.memory
        bag = [mem[ADDR_BAG_ITEMS + 2 * i] for i in range(mem[ADDR_NUM_BAG_ITEMS])]
        if item_id not in bag:
            return ""
        lines = []
        self._press("start")
        self._menu.select("ITEM")
        self._pyboy.tick(30)
        self._scroll_list_to(bag.index(item_id))
        self._press("a")
        self._menu.select("USE")
        self._pyboy.tick(30)
        # "Booted up an HM! ... Teach X to a POKéMON?" -> YES
        if not self._advance_to_yes_no(lines):
            return self._close(lines)
        self._press("a")                           # YES
        self._pyboy.tick(30)
        self._move_cursor_to(slot)                 # party screen
        self._press("a", 60)
        if forget_index is not None:
            # "... can't learn more than 4 moves! Delete an older move?" -> YES
            if self._advance_to_yes_no(lines):
                self._press("a", 40)               # YES -> move list
                if not self._wait_for_text("forgotten?", lines):
                    return self._close(lines)
                self._pyboy.tick(40)               # list drawn after the text
                self._move_cursor_to(forget_index)
                self._press("a", 60)
        return self._close(lines, done=("learned", "did not learn", "knows"))

    # ------------------------------------------------------------------
    # Using a field move
    # ------------------------------------------------------------------

    def slot_knowing(self, move: str) -> int | None:
        """First party slot whose Pokémon knows the move."""
        mem = self._pyboy.memory
        for slot in range(mem[ADDR_PARTY_COUNT]):
            base = ADDR_PARTY_MONS + slot * PARTY_MON_SIZE + PARTY_MON_MOVES
            if any(MOVE_NAMES.get(mem[base + k]) == move for k in range(4)):
                return slot
        return None

    def use_field_move(self, slot: int, move: str) -> str:
        """Use a field move (e.g. CUT) from party slot; returns the game's text."""
        lines = []
        self._press("start")
        self._menu.select("POKéMON")
        self._pyboy.tick(40)
        self._move_cursor_to(slot)
        self._press("a", 40)
        options = self._menu.read_choice_menu()
        if not any(move in opt for opt in options):
            return self._close(lines)
        self._menu.select(move, options)
        self._pyboy.tick(60)
        return self._close(lines, done=("hacked away", "can't be used", "no one"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _press(self, button, wait=30):
        self._pyboy.button(button, delay=8)
        self._pyboy.tick(wait)

    def _scroll_list_to(self, index):
        """Move a scrolling list (bag) cursor to an absolute index."""
        mem = self._pyboy.memory
        for _ in range(40):
            current = mem[ADDR_LIST_SCROLL_OFFSET] + mem[ADDR_CURRENT_MENU]
            if current == index:
                return
            self._press("down" if current < index else "up", 10)

    def _move_cursor_to(self, index):
        mem = self._pyboy.memory
        for _ in range(10):
            current = mem[ADDR_CURRENT_MENU]
            if current == index:
                return
            self._press("down" if current < index else "up", 10)

    def _collect(self, lines):
        """Record the text box, merging it with what was already read: the
        game prints and scrolls text gradually, so snapshots overlap."""
        text = self._screen.read_text_box()
        if not text:
            return
        so_far = lines[0] if lines else ""
        if text in so_far:
            return
        overlap = next((k for k in range(min(len(so_far), len(text)), 0, -1)
                        if so_far.endswith(text[:k])), 0)
        merged = (so_far + ("" if overlap or not so_far else " ") + text[overlap:]).strip()
        lines[:] = [merged]

    def _wait_for_text(self, needle, lines, max_steps=20) -> bool:
        for _ in range(max_steps):
            self._collect(lines)
            if needle in self._screen.read_text_box():
                return True
            self._pyboy.tick(20)
        return False

    def _advance_to_yes_no(self, lines, max_steps=25) -> bool:
        """Press A through dialogue until a YES/NO box shows (cursor on YES)."""
        for _ in range(max_steps):
            self._collect(lines)
            if self._yes_no_visible():
                return True
            self._press("a", 40)
        return False

    def _yes_no_visible(self) -> bool:
        """A YES/NO box anywhere on screen. The generic menu reader misses
        the one drawn over the party screen, so look for the text itself."""
        mem = self._pyboy.memory

        def row_text(r):
            return "".join(">" if mem[ADDR_TILEMAP + r * 20 + c] == TILE_CURSOR
                           else POKEMON_CHARMAP.get(mem[ADDR_TILEMAP + r * 20 + c], "")
                           for c in range(20))
        for r in range(16):
            if "YES" in row_text(r) and "NO" in row_text(r + 2):
                return True
        return False

    def _close(self, lines, done=()) -> str:
        """Advance the remaining dialogue and back out to the overworld.

        Until one of the `done` phrases shows, text is advanced with A; after
        it only B is used, so leftover screens (the party list asking "Use TM
        on which POKéMON?") are backed out of instead of re-entered.
        """
        finished = not done
        for _ in range(30):
            if not finished:  # past the final message it's only menu residue
                self._collect(lines)
            text_so_far = lines[0] if lines else ""
            finished = finished or any(word in text_so_far for word in done)
            if self._screen.read_text_box():
                self._press("b" if finished else "a", 40)
            elif self._menu.find_cursor_on_screen() is not None:
                self._press("b", 30)
            else:
                break
        return " ".join(lines)
