from constants import (
    ADDR_MENU_Y, ADDR_MENU_X, ADDR_CURRENT_MENU, ADDR_MAX_MENU,
    ADDR_MENU_WATCHED_KEYS, ADDR_TILEMAP,
)

TILE_CURSOR = 0xED  # ▶ menu cursor tile


class MenuReader:
    def __init__(self, pyboy, screen):
        self._pyboy = pyboy
        self._screen = screen

    def get_options(self):
        """Read current menu options from wTileMap. Returns list of strings."""
        menu_y = self._pyboy.memory[ADDR_MENU_Y]
        menu_x = self._pyboy.memory[ADDR_MENU_X]
        max_item = self._pyboy.memory[ADDR_MAX_MENU]

        options = []
        for i in range(max_item + 1):
            row = menu_y + i * 2
            text = self._screen.decode_tiles(row, menu_x + 1)
            options.append(text)
        return options

    def select(self, target, options=None):
        """Navigate the menu and select the option matching target."""
        if options is None:
            options = self.get_options()

        target_index = next(
            (i for i, opt in enumerate(options) if target in opt), None
        )
        if target_index is None:
            raise ValueError(f"'{target}' not found in menu: {options}")

        current = self._pyboy.memory[ADDR_CURRENT_MENU]

        while current != target_index:
            if current < target_index:
                self._pyboy.button("down")
            else:
                self._pyboy.button("up")
            self._pyboy.tick(10)
            current = self._pyboy.memory[ADDR_CURRENT_MENU]

        self._pyboy.button("a")
        self._pyboy.tick(10)

    def is_visible(self):
        """Detect a visible menu by checking menu WRAM."""
        menu_y = self._pyboy.memory[ADDR_MENU_Y]
        menu_x = self._pyboy.memory[ADDR_MENU_X]
        current = self._pyboy.memory[ADDR_CURRENT_MENU]
        max_item = self._pyboy.memory[ADDR_MAX_MENU]

        if menu_y == 0 or menu_x == 0:
            return False
        if max_item > 2:
            return False
        if current > max_item:
            return False
        return True

    def has_cursor_on_screen(self):
        """Check if a menu cursor (▶) is actually drawn on screen.

        More reliable than is_visible() since WRAM values persist after
        menus close, but the cursor tile does not.
        """
        mem = self._pyboy.memory
        menu_y = mem[ADDR_MENU_Y]
        menu_x = mem[ADDR_MENU_X]
        current = mem[ADDR_CURRENT_MENU]
        max_item = mem[ADDR_MAX_MENU]

        if menu_y == 0 or menu_x == 0:
            return False
        if max_item > 2 or current > max_item:
            return False

        cursor_row = menu_y + current * 2
        cursor_col = menu_x - 1
        if cursor_row >= 18 or cursor_col < 0 or cursor_col >= 20:
            return False
        tile = mem[ADDR_TILEMAP + cursor_row * 20 + cursor_col]
        return tile == TILE_CURSOR

    def find_cursor_on_screen(self):
        """Scan the entire tilemap for a menu cursor tile (▶).

        Returns (row, col) of the cursor if found, or None.
        Unlike has_cursor_on_screen(), this does NOT rely on WRAM menu
        addresses — it finds the cursor wherever it's drawn.
        Searches all 18 rows (including text box area) since WRAM
        position checks in read_choice_menu() filter false positives.
        """
        mem = self._pyboy.memory
        for row in range(18):
            for col in range(20):
                tile = mem[ADDR_TILEMAP + row * 20 + col]
                if tile == TILE_CURSOR:
                    return (row, col)
        return None

    def read_choice_menu(self):
        """Detect an active choice menu and return its options.

        Approach: find cursor tile 0xED on screen, then verify it sits
        exactly where WRAM says the cursor should be drawn.  This rejects
        stray 0xED tiles in map graphics (they won't match WRAM coords).
        """
        mem = self._pyboy.memory

        # Find cursor tile anywhere in rows 0-11
        pos = self.find_cursor_on_screen()

        menu_y = mem[ADDR_MENU_Y]
        menu_x = mem[ADDR_MENU_X]
        current = mem[ADDR_CURRENT_MENU]
        max_item = mem[ADDR_MAX_MENU]

        if pos is None:
            return []

        cursor_row, cursor_col = pos

        expected_row = menu_y + current * 2

        # Cursor can be at menu_x (some menus) or menu_x - 1 (others)
        if cursor_row != expected_row or cursor_col not in (menu_x, menu_x - 1):
            return []

        if max_item > 10 or max_item < 1:
            return []

        # Verify non-selected option slots have a blank tile (0x7F) in the
        # cursor column.  Real menus clear those slots; map graphics won't.
        TILE_BLANK = 0x7F
        for i in range(max_item + 1):
            if i == current:
                continue
            check_row = menu_y + i * 2
            tile = mem[ADDR_TILEMAP + check_row * 20 + cursor_col]
            if tile != TILE_BLANK:
                return []

        # Read options from WRAM coordinates
        options = []
        text_col = cursor_col + 1
        for i in range(max_item + 1):
            row = menu_y + i * 2
            text = self._screen.decode_tiles(row, text_col, 19 - text_col)
            stripped = text.strip()
            if stripped:
                options.append(stripped)

        # Real menus always have at least 2 options
        if len(options) < 2:
            return []
        return options

    def is_name_menu(self):
        """Detect the name selection menu (4 options).

        Checks WRAM values AND verifies the cursor tile is drawn at the
        expected WRAM position, AND non-selected slots have blank tiles.
        """
        mem = self._pyboy.memory
        max_item = mem[ADDR_MAX_MENU]
        menu_y = mem[ADDR_MENU_Y]
        menu_x = mem[ADDR_MENU_X]
        current = mem[ADDR_CURRENT_MENU]
        if not (max_item == 3 and menu_y > 0 and menu_x > 0
                and current <= max_item):
            return False
        # Verify cursor tile is at the expected WRAM position
        cursor_row = menu_y + current * 2
        if cursor_row >= 18:
            return False
        # Cursor can be at menu_x or menu_x - 1
        cursor_col = None
        for col in (menu_x, menu_x - 1):
            if 0 <= col < 20:
                tile = mem[ADDR_TILEMAP + cursor_row * 20 + col]
                if tile == TILE_CURSOR:
                    cursor_col = col
                    break
        if cursor_col is None:
            return False
        # Verify non-selected slots have blank tiles (rejects stale WRAM
        # when map graphics happen to have 0xED at the cursor position)
        TILE_BLANK = 0x7F
        for i in range(max_item + 1):
            if i == current:
                continue
            check_row = menu_y + i * 2
            tile = mem[ADDR_TILEMAP + check_row * 20 + cursor_col]
            if tile != TILE_BLANK:
                return False
        # Verify first option has real text on screen
        options = self.get_options()
        return any(o.strip() for o in options)

    def wait_for_main_menu(self):
        """Spam A and Start through logos and title screen,
        stop when the New Game / Continue menu appears."""
        while True:
            if self.is_visible():
                options = self.get_options()
                if any("NEW GAME" in opt for opt in options):
                    break

            self._pyboy.button("a")
            self._pyboy.tick(10)
            self._pyboy.button("start")
            self._pyboy.tick(10)
