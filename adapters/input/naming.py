from data.constants import NAME_KEYBOARD


class NameEntry:
    def __init__(self, pyboy):
        self._pyboy = pyboy

    def enter(self, name):
        """Navigate the name entry keyboard to type a name, then confirm."""
        self._pyboy.tick(60)  # Wait for naming screen to load

        cur_row, cur_col = 0, 0  # Cursor starts at 'A'

        for char in name.upper():
            target_row, target_col = self._find_char(char)

            # Move vertically
            while cur_row != target_row:
                self._pyboy.button("down" if cur_row < target_row else "up")
                cur_row += 1 if cur_row < target_row else -1
                self._pyboy.tick(8)

            # Move horizontally
            while cur_col != target_col:
                self._pyboy.button("right" if cur_col < target_col else "left")
                cur_col += 1 if cur_col < target_col else -1
                self._pyboy.tick(8)

            # Select character
            self._pyboy.button("a")
            self._pyboy.tick(10)

        # Confirm name with START
        self._pyboy.button("start")
        self._pyboy.tick(30)

    @staticmethod
    def _find_char(char):
        """Find row and column of a character in the keyboard layout."""
        for r, row in enumerate(NAME_KEYBOARD):
            c = row.find(char)
            if c != -1:
                return r, c
        raise ValueError(f"'{char}' not in keyboard layout")
