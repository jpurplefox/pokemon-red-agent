"""Battle menu driver — presses buttons to execute battle actions (SRP).

Pure output adapter: translates domain-level intents into button sequences.
No WRAM reading for game state — only reads cursor position for navigation.
"""

from data.constants import (
    ADDR_CURRENT_MENU, ADDR_MENU_WATCHED_KEYS, ADDR_LIST_SCROLL_OFFSET,
)


# Naming keyboard grid layout (uppercase)
_NAMING_GRID = {}
_ROWS = ["ABCDEFGHI", "JKLMNOPQR", "STUVWXYZ  "]
for _r, _row_chars in enumerate(_ROWS):
    for _c, _ch in enumerate(_row_chars):
        if _ch != " ":
            _NAMING_GRID[_ch] = (_r, _c)


class BattleMenuDriver:
    """Presses buttons to navigate battle menus and execute actions."""

    def __init__(self, pyboy, screen):
        self._pyboy = pyboy
        self._screen = screen
        self._last_move_idx = 0

    def reset_move_cursor(self):
        """Reset tracked move cursor position."""
        self._last_move_idx = 0

    @property
    def last_move_idx(self):
        return self._last_move_idx

    def has_battle_menu(self) -> bool:
        """Check if FIGHT/ITEM/RUN menu is on screen."""
        for row in range(14, 18):
            text = self._screen.decode_tiles(row, 8, 12)
            if "FIGHT" in text:
                return True
        return False

    def select_battle_option(self, option: str):
        """Select FIGHT, ITEM, PKMN, or RUN from the 2x2 battle menu."""
        targets = {"FIGHT": (0, 0), "PKMN": (0, 1),
                   "ITEM": (1, 0), "RUN": (1, 1)}
        row, col = targets.get(option, (0, 0))

        self._pyboy.button("up")
        self._pyboy.tick(8)
        self._pyboy.button("left")
        self._pyboy.tick(8)

        for _ in range(row):
            self._pyboy.button("down")
            self._pyboy.tick(8)
        for _ in range(col):
            self._pyboy.button("right")
            self._pyboy.tick(8)

        self._pyboy.button("a")
        self._pyboy.tick(10)

    def wait_for_move_menu(self, moves):
        """Wait for the move selection menu to appear."""
        first_move = moves[0].name if moves else ""
        for _ in range(60):
            self._pyboy.tick(10)
            if not self.has_battle_menu():
                break

        if first_move:
            for _ in range(30):
                for row in range(14, 18):
                    text = self._screen.decode_tiles(row, 1, 12)
                    if first_move in text:
                        self._pyboy.tick(5)
                        return
                self._pyboy.tick(10)

    def select_move(self, move_idx: int):
        """Select a move by index (0-3) from the move list menu."""
        # Wait for the move menu to be fully ready for input
        for _ in range(30):
            if self._pyboy.memory[ADDR_MENU_WATCHED_KEYS] != 0:
                break
            self._pyboy.tick(5)
        self._pyboy.tick(10)  # settle time after menu ready
        current = self._last_move_idx
        diff = move_idx - current
        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down", delay=8)
                self._pyboy.tick(10)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up", delay=8)
                self._pyboy.tick(10)

        self._pyboy.button("a")
        self._pyboy.tick(10)
        self._last_move_idx = move_idx

    def use_ball(self, bag_index: int):
        """Select ITEM from battle menu, then select the ball by bag index.

        Reads the current cursor position and scroll offset from WRAM
        to navigate correctly regardless of bag state.
        """
        self.select_battle_option("ITEM")
        for _ in range(30):
            self._pyboy.tick(10)
            if not self.has_battle_menu():
                break

        # Wait for item menu to be ready for input
        mem = self._pyboy.memory
        for _ in range(60):
            if mem[ADDR_MENU_WATCHED_KEYS] != 0:
                break
            self._pyboy.tick(5)

        # Read current cursor state from WRAM
        cursor_pos = mem[ADDR_CURRENT_MENU]
        scroll_offset = mem[ADDR_LIST_SCROLL_OFFSET]
        current_index = scroll_offset + cursor_pos

        # Navigate from current position to target
        delta = bag_index - current_index
        direction = "down" if delta > 0 else "up"

        # Navigate by tracking actual position, retrying lost presses
        max_presses = abs(delta) * 3  # safety limit
        presses = 0
        while presses < max_presses:
            cur = mem[ADDR_CURRENT_MENU] + mem[ADDR_LIST_SCROLL_OFFSET]
            if cur == bag_index:
                break
            self._pyboy.button(direction)
            presses += 1
            for _ in range(30):
                self._pyboy.tick(5)
                if mem[ADDR_CURRENT_MENU] + mem[ADDR_LIST_SCROLL_OFFSET] != cur:
                    break

        self._pyboy.button("a")
        self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(10)

    def switch_pokemon(self, party_idx: int):
        """Switch to a different Pokemon by party index."""
        self.select_battle_option("PKMN")
        for _ in range(30):
            self._pyboy.tick(10)
            if not self.has_battle_menu():
                break
        self._pyboy.tick(10)

        self._navigate_to_party_slot(party_idx)

        self._pyboy.button("a")
        self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(10)

        self._last_move_idx = 0

    def navigate_party_menu(self, target_idx: int):
        """Navigate to a party member in the party selection screen."""
        self._navigate_to_party_slot(target_idx)
        self._pyboy.button("a")
        self._pyboy.tick(10)

    def _navigate_to_party_slot(self, target_idx: int):
        """Move cursor to a specific party slot reliably.

        Waits for menu to be ready, reads actual cursor position,
        then navigates the minimum number of steps.
        """
        mem = self._pyboy.memory

        # Wait for menu to accept input
        for _ in range(60):
            self._pyboy.tick(5)
            if mem[ADDR_MENU_WATCHED_KEYS] != 0:
                break

        current = mem[ADDR_CURRENT_MENU]
        diff = target_idx - current

        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down")
                self._pyboy.tick(10)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up")
                self._pyboy.tick(10)

    def type_name(self, name: str):
        """Type a name on the Pokemon Red naming keyboard."""
        cur_row, cur_col = 0, 0
        for ch in name:
            if ch not in _NAMING_GRID:
                continue
            target_row, target_col = _NAMING_GRID[ch]
            dy = target_row - cur_row
            btn = "down" if dy > 0 else "up"
            for _ in range(abs(dy)):
                self._pyboy.button(btn)
                self._pyboy.tick(5)
            dx = target_col - cur_col
            btn = "right" if dx > 0 else "left"
            for _ in range(abs(dx)):
                self._pyboy.button(btn)
                self._pyboy.tick(5)
            self._pyboy.button("a")
            self._pyboy.tick(8)
            cur_row, cur_col = target_row, target_col

        self._pyboy.button("start")
        self._pyboy.tick(10)
