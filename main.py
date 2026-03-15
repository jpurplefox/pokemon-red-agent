from pyboy import PyBoy

# Pokemon Red WRAM addresses (pret/pokered disassembly)
ADDR_MAP_N = 0xD35E            # wCurMap: 0 during intro, non-zero in overworld
ADDR_MENU_Y = 0xCC24           # wTopMenuItemY: Y position of first menu item
ADDR_MENU_X = 0xCC25           # wTopMenuItemX: X position of first menu item
ADDR_CURRENT_MENU = 0xCC26     # wCurrentMenuItem: selected item (0 = first)
ADDR_MAX_MENU = 0xCC28         # wMaxMenuItem: index of last item

ADDR_TILEMAP = 0xC3A0          # wTileMap: WRAM copy of screen (20 tiles per row)

# Pokemon Red character encoding (charmap)
POKEMON_CHARMAP = {
    0x7F: " ",
    0x80: "A", 0x81: "B", 0x82: "C", 0x83: "D", 0x84: "E",
    0x85: "F", 0x86: "G", 0x87: "H", 0x88: "I", 0x89: "J",
    0x8A: "K", 0x8B: "L", 0x8C: "M", 0x8D: "N", 0x8E: "O",
    0x8F: "P", 0x90: "Q", 0x91: "R", 0x92: "S", 0x93: "T",
    0x94: "U", 0x95: "V", 0x96: "W", 0x97: "X", 0x98: "Y",
    0x99: "Z",
    0x50: "",  # string terminator
}


def decode_tiles(pyboy, row, col, length=12):
    """Read tiles from the background tilemap and decode as Pokemon text."""
    text = ""
    for i in range(length):
        tile = pyboy.memory[ADDR_TILEMAP + row * 20 + col + i]
        if tile == 0x50:
            break
        text += POKEMON_CHARMAP.get(tile, "")
    return text.strip()


def print_menu(pyboy):
    """Print the current menu options read from the tilemap."""
    menu_y = pyboy.memory[ADDR_MENU_Y]
    menu_x = pyboy.memory[ADDR_MENU_X]
    max_item = pyboy.memory[ADDR_MAX_MENU]
    current = pyboy.memory[ADDR_CURRENT_MENU]

    print(f"menu pos=({menu_x},{menu_y}) current={current} max={max_item}")

    for i in range(max_item + 1):
        row = menu_y + i * 2
        # dump raw tile bytes for debugging
        raw = [pyboy.memory[ADDR_TILEMAP + row * 20 + menu_x + j] for j in range(12)]
        text = decode_tiles(pyboy, row, menu_x + 1)
        cursor = ">" if i == current else " "
        print(f"  {cursor} {text}  (raw: {[hex(b) for b in raw]})")


def is_main_menu(pyboy):
    """Detect the New Game / Continue menu by checking menu WRAM."""
    menu_y = pyboy.memory[ADDR_MENU_Y]
    menu_x = pyboy.memory[ADDR_MENU_X]
    current = pyboy.memory[ADDR_CURRENT_MENU]
    max_item = pyboy.memory[ADDR_MAX_MENU]

    if menu_y == 0 or menu_x == 0:
        return False
    if max_item > 2:
        return False
    if current > max_item:
        return False
    return True


def get_menu_options(pyboy):
    """Read current menu options from wTileMap. Returns list of strings."""
    menu_y = pyboy.memory[ADDR_MENU_Y]
    menu_x = pyboy.memory[ADDR_MENU_X]
    max_item = pyboy.memory[ADDR_MAX_MENU]

    options = []
    for i in range(max_item + 1):
        row = menu_y + i * 2
        text = decode_tiles(pyboy, row, menu_x + 1)
        options.append(text)
    return options


def select_menu_option(pyboy, target, options=None):
    """Navigate the menu and select the option matching target.
    If options is None, reads them from the tilemap."""
    if options is None:
        options = get_menu_options(pyboy)

    target_index = next(
        (i for i, opt in enumerate(options) if target in opt), None
    )
    if target_index is None:
        raise ValueError(f"'{target}' not found in menu: {options}")

    current = pyboy.memory[ADDR_CURRENT_MENU]

    # Navigate to the target option
    while current != target_index:
        if current < target_index:
            pyboy.button("down")
        else:
            pyboy.button("up")
        pyboy.tick(10)
        current = pyboy.memory[ADDR_CURRENT_MENU]

    # Press A to confirm
    pyboy.button("a")
    pyboy.tick(10)


def skip_to_menu(pyboy):
    """Spam A and Start through logos and title screen,
    stop when the New Game / Continue menu appears."""
    while True:
        if pyboy.memory[ADDR_MAP_N] != 0:
            break
        if is_main_menu(pyboy):
            break

        pyboy.button("a")
        pyboy.tick(10)
        pyboy.button("start")
        pyboy.tick(10)


pyboy = PyBoy("rom.gb")
skip_to_menu(pyboy)
pyboy.tick(30)  # wait for tiles to be drawn

options = get_menu_options(pyboy)
print("Menu:", options)

select_menu_option(pyboy, "NEW GAME", options)

while pyboy.tick():
    pass

pyboy.stop()
