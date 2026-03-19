"""Battle menu driver — presses buttons to execute battle actions (SRP).

Pure output adapter: translates domain-level intents into button sequences.
No WRAM reading for game state — only reads cursor position for navigation.
"""

from data.constants import ADDR_CURRENT_MENU


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
        """Select a move by index (0-3) from the move menu."""
        current = self._last_move_idx
        diff = move_idx - current
        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down")
                self._pyboy.tick(8)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up")
                self._pyboy.tick(8)

        self._pyboy.button("a")
        self._pyboy.tick(10)
        self._last_move_idx = move_idx

    def use_ball(self, bag_index: int):
        """Select ITEM from battle menu, then select the ball by bag index."""
        self.select_battle_option("ITEM")
        for _ in range(30):
            self._pyboy.tick(10)
            if not self.has_battle_menu():
                break

        for _ in range(10):
            self._pyboy.button("up")
            self._pyboy.tick(5)

        for _ in range(bag_index):
            self._pyboy.button("down")
            self._pyboy.tick(8)

        self._pyboy.button("a")
        self._pyboy.tick(20)
        self._pyboy.button("a")
        self._pyboy.tick(10)

    def switch_pokemon(self, party_idx: int):
        """Switch to a different Pokemon by party index."""
        self.select_battle_option("PKMN")
        for _ in range(30):
            self._pyboy.tick(10)
            if not self.has_battle_menu():
                break
        self._pyboy.tick(40)

        current = self._pyboy.memory[ADDR_CURRENT_MENU]
        diff = party_idx - current

        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down")
                self._pyboy.tick(10)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up")
                self._pyboy.tick(10)

        self._pyboy.button("a")
        self._pyboy.tick(20)
        self._pyboy.button("a")
        self._pyboy.tick(10)

        self._last_move_idx = 0

    def navigate_party_menu(self, target_idx: int):
        """Navigate to a party member in the party selection screen."""
        current = self._pyboy.memory[ADDR_CURRENT_MENU]
        diff = target_idx - current
        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down")
                self._pyboy.tick(10)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up")
                self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(20)

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
        self._pyboy.tick(30)
