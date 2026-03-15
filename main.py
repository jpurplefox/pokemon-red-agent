from pyboy import PyBoy

# Pokemon Red WRAM addresses (pret/pokered disassembly)
ADDR_MAP_N = 0xD35E            # wCurMap: 0 during intro, non-zero in overworld
ADDR_MENU_Y = 0xCC24           # wTopMenuItemY: Y position of first menu item
ADDR_MENU_X = 0xCC25           # wTopMenuItemX: X position of first menu item
ADDR_CURRENT_MENU = 0xCC26     # wCurrentMenuItem: selected item (0 = first)
ADDR_MAX_MENU = 0xCC28         # wMaxMenuItem: index of last item

ADDR_TILEMAP = 0xC3A0          # wTileMap: WRAM copy of screen (20 tiles per row)

# Pokemon Red character encoding (from pret/pokered charmap.asm)
POKEMON_CHARMAP = {
    0x7F: " ",
    # Uppercase A-Z
    0x80: "A", 0x81: "B", 0x82: "C", 0x83: "D", 0x84: "E",
    0x85: "F", 0x86: "G", 0x87: "H", 0x88: "I", 0x89: "J",
    0x8A: "K", 0x8B: "L", 0x8C: "M", 0x8D: "N", 0x8E: "O",
    0x8F: "P", 0x90: "Q", 0x91: "R", 0x92: "S", 0x93: "T",
    0x94: "U", 0x95: "V", 0x96: "W", 0x97: "X", 0x98: "Y",
    0x99: "Z",
    # Punctuation
    0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";", 0x9E: "[", 0x9F: "]",
    # Lowercase a-z
    0xA0: "a", 0xA1: "b", 0xA2: "c", 0xA3: "d", 0xA4: "e",
    0xA5: "f", 0xA6: "g", 0xA7: "h", 0xA8: "i", 0xA9: "j",
    0xAA: "k", 0xAB: "l", 0xAC: "m", 0xAD: "n", 0xAE: "o",
    0xAF: "p", 0xB0: "q", 0xB1: "r", 0xB2: "s", 0xB3: "t",
    0xB4: "u", 0xB5: "v", 0xB6: "w", 0xB7: "x", 0xB8: "y",
    0xB9: "z",
    # Special characters
    0xBA: "é",
    0xE0: "'", 0xE3: "-", 0xE6: "?", 0xE7: "!", 0xE8: ".",
    0xF4: ",", 0xF5: "/",
    # Digits
    0xF6: "0", 0xF7: "1", 0xF8: "2", 0xF9: "3", 0xFA: "4",
    0xFB: "5", 0xFC: "6", 0xFD: "7", 0xFE: "8", 0xFF: "9",
}

# Name entry keyboard layout (uppercase, Pokemon Red)
NAME_KEYBOARD = [
    "ABCDEFGHI",
    "JKLMNOPQR",
    "STUVWXYZ ",
]


def decode_tiles(pyboy, row, col, length=18):
    """Read tiles from wTileMap and decode as Pokemon text."""
    text = ""
    for i in range(length):
        tile = pyboy.memory[ADDR_TILEMAP + row * 20 + col + i]
        if tile == 0x50:
            break
        text += POKEMON_CHARMAP.get(tile, "")
    return text.strip()


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
    """Navigate the menu and select the option matching target."""
    if options is None:
        options = get_menu_options(pyboy)

    target_index = next(
        (i for i, opt in enumerate(options) if target in opt), None
    )
    if target_index is None:
        raise ValueError(f"'{target}' not found in menu: {options}")

    current = pyboy.memory[ADDR_CURRENT_MENU]

    while current != target_index:
        if current < target_index:
            pyboy.button("down")
        else:
            pyboy.button("up")
        pyboy.tick(10)
        current = pyboy.memory[ADDR_CURRENT_MENU]

    pyboy.button("a")
    pyboy.tick(10)


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


def read_text_box(pyboy):
    """Read text from the text box area (bottom of screen, rows 12-17)."""
    lines = []
    for row in range(12, 18):
        line = decode_tiles(pyboy, row, 1, 18)
        if line:
            lines.append(line)
    return " ".join(lines)


def is_name_menu(pyboy):
    """Detect the name selection menu (4 options)."""
    max_item = pyboy.memory[ADDR_MAX_MENU]
    menu_y = pyboy.memory[ADDR_MENU_Y]
    menu_x = pyboy.memory[ADDR_MENU_X]
    current = pyboy.memory[ADDR_CURRENT_MENU]
    return max_item == 3 and menu_y > 0 and menu_x > 0 and current <= max_item


def advance_dialogue(pyboy):
    """Press A through dialogue until a name selection menu appears.
    Waits for text to finish rendering before capturing each box.
    Returns all captured dialogue as a single string."""
    dialogue = []
    last_captured = ""

    while True:
        if is_name_menu(pyboy):
            break

        # Wait for text to stabilize (letter-by-letter animation finished)
        prev = ""
        current = read_text_box(pyboy)
        while current != prev:
            prev = current
            pyboy.tick(10)
            current = read_text_box(pyboy)
            if is_name_menu(pyboy):
                break

        # Capture only complete, new text
        if current and current != last_captured:
            dialogue.append(current)
            last_captured = current

        if is_name_menu(pyboy):
            break

        # Press A to advance to next text box
        pyboy.button("a")
        pyboy.tick(10)

    return _deduplicate_dialogue(dialogue)


def _deduplicate_dialogue(lines):
    """Remove overlapping text between consecutive captures.
    The text box shows 2 lines at a time, so when it scrolls,
    the next capture starts with text from the previous one."""
    if not lines:
        return ""
    result = [lines[0]]
    for line in lines[1:]:
        prev = result[-1]
        # Check if the new line starts with the end of the previous one
        # (text box scroll: line2 of prev becomes line1 of current)
        overlap = ""
        for length in range(min(len(prev), len(line)), 0, -1):
            if line.startswith(prev[-length:]):
                overlap = prev[-length:]
                break
        if overlap:
            new_text = line[len(overlap):]
            if new_text.strip():
                result.append(new_text.strip())
        else:
            result.append(line)
    return " ".join(result)


def skip_to_menu(pyboy):
    """Spam A and Start through logos and title screen,
    stop when the New Game / Continue menu appears."""
    while True:
        if is_main_menu(pyboy):
            options = get_menu_options(pyboy)
            if any("NEW GAME" in opt for opt in options):
                break

        pyboy.button("a")
        pyboy.tick(10)
        pyboy.button("start")
        pyboy.tick(10)


def enter_name(pyboy, name):
    """Navigate the name entry keyboard to type a name, then confirm."""
    pyboy.tick(60)  # Wait for naming screen to load

    cur_row, cur_col = 0, 0  # Cursor starts at 'A'

    for char in name.upper():
        target_row = target_col = None
        for r, row in enumerate(NAME_KEYBOARD):
            c = row.find(char)
            if c != -1:
                target_row, target_col = r, c
                break
        if target_row is None:
            raise ValueError(f"'{char}' not in keyboard layout")

        # Move vertically
        while cur_row != target_row:
            pyboy.button("down" if cur_row < target_row else "up")
            cur_row += 1 if cur_row < target_row else -1
            pyboy.tick(8)

        # Move horizontally
        while cur_col != target_col:
            pyboy.button("right" if cur_col < target_col else "left")
            cur_col += 1 if cur_col < target_col else -1
            pyboy.tick(8)

        # Select character
        pyboy.button("a")
        pyboy.tick(10)

    # Confirm name with START
    pyboy.button("start")
    pyboy.tick(30)


def advance_to_overworld(pyboy):
    """Press A through dialogue until Oak finishes and the overworld loads."""
    dialogue = []
    last_captured = ""
    no_new_text = 0

    while True:
        prev = ""
        current = read_text_box(pyboy)
        while current != prev:
            prev = current
            pyboy.tick(10)
            current = read_text_box(pyboy)

        if current and current != last_captured:
            dialogue.append(current)
            last_captured = current
            no_new_text = 0
        else:
            no_new_text += 1

        # Stop after prolonged silence (animation + transition done)
        if dialogue and no_new_text > 30:
            break

        pyboy.button("a")
        pyboy.tick(10)

    return _deduplicate_dialogue(dialogue)


pyboy = PyBoy("rom.gb")

# Skip intro and select New Game
skip_to_menu(pyboy)
pyboy.tick(30)
select_menu_option(pyboy, "NEW GAME")

# Advance Oak's dialogue and capture text
dialogue = advance_dialogue(pyboy)
print("=== Oak's Speech ===")
print(dialogue)

# Select NEW NAME and enter "JESS"
pyboy.tick(30)
options = get_menu_options(pyboy)
print("\nName options:", options)
select_menu_option(pyboy, "NEW NAME", options)
enter_name(pyboy, "JESS")
print("Name entered: JESS")

# Advance Oak's dialogue about the rival
rival_dialogue = advance_dialogue(pyboy)
print("\n=== Oak's Speech (Rival) ===")
print(rival_dialogue)

# Select NEW NAME and enter "FOLAGOR"
pyboy.tick(30)
rival_options = get_menu_options(pyboy)
print("\nRival name options:", rival_options)
select_menu_option(pyboy, "NEW NAME", rival_options)
enter_name(pyboy, "FOLAGOR")
print("Rival name entered: FOLAGOR")

# Advance remaining dialogue until player appears in bedroom
final_dialogue = advance_to_overworld(pyboy)
print("\n=== Oak's Final Speech ===")
print(final_dialogue)
print("\nPlayer is now in their bedroom!")

while pyboy.tick():
    pass

pyboy.stop()
