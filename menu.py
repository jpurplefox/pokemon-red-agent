from constants import ADDR_MENU_Y, ADDR_MENU_X, ADDR_CURRENT_MENU, ADDR_MAX_MENU


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

    def is_name_menu(self):
        """Detect the name selection menu (4 options)."""
        max_item = self._pyboy.memory[ADDR_MAX_MENU]
        menu_y = self._pyboy.memory[ADDR_MENU_Y]
        menu_x = self._pyboy.memory[ADDR_MENU_X]
        current = self._pyboy.memory[ADDR_CURRENT_MENU]
        return max_item == 3 and menu_y > 0 and menu_x > 0 and current <= max_item

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
