"""Console UI for interacting with the game (SRP: user input/output only)."""

BUTTONS = {"up", "down", "left", "right", "a", "b", "start", "select"}
COMMANDS = BUTTONS | {"quit", "look", "scan", "go", "lead", "ai", "speed"}

# Replaceable input function — Game swaps this with a ticking version
# so the emulator keeps running while waiting for user input.
_input_fn = input


def set_input_fn(fn):
    """Replace the input function used by all console prompts."""
    global _input_fn
    _input_fn = fn


def prompt_menu(options):
    """Show numbered menu options and return the user's choice."""
    print("\n--- Menu ---")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        try:
            choice = int(_input_fn("Choose: "))
            if 1 <= choice <= len(options):
                return options[choice - 1]
        except (ValueError, EOFError):
            pass
        print(f"Enter 1-{len(options)}")


def prompt_name():
    """Ask the user to type a name (1-7 uppercase letters)."""
    while True:
        name = _input_fn("Enter name: ").strip().upper()
        if 1 <= len(name) <= 7 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ " for c in name):
            return name
        print("1-7 letters A-Z only")


def prompt_command():
    """Prompt for an overworld command. Returns the command string."""
    cmd = _input_fn("> ").strip().lower()
    if cmd and cmd not in COMMANDS:
        print("Commands: up, down, left, right, a, b, start, select, look, go, quit")
        return None
    return cmd


def prompt_action(interactables, connections) -> tuple | None:
    """Show action prompt and parse user input.

    interactables: list of domain Interactable objects
    connections: list of domain MapConnection objects

    Accepts:
      <n>           — interact with interactable n (number from map)
      <letter>      — travel to connection (letter from map)
      MOVE:<dir>    — walk one tile (up/down/left/right)
      START / LOOK / QUIT

    Returns (action_type, detail) or None on invalid input.
    """
    print("\n--- Actions ---")
    print("  <number>  interact    <letter>  travel")
    print("  MOVE:<dir>  walk (up/down/left/right)")
    print("  START / LOOK / QUIT")

    cmd = _input_fn("ACTION: ").strip()
    if not cmd:
        return None

    upper = cmd.upper()

    # Number → interact
    if cmd.isdigit():
        idx = int(cmd) - 1
        if 0 <= idx < len(interactables):
            return ("interact", idx)
        print(f"  Interactable range: 1-{len(interactables)}")
        return None

    # Single letter → connection
    if len(cmd) == 1 and cmd.isalpha() and cmd.lower() != cmd.upper():
        idx = ord(cmd.lower()) - ord("a")
        if 0 <= idx < len(connections):
            return ("go", idx)
        if connections:
            last = chr(ord("a") + len(connections) - 1)
            print(f"  Connection range: a-{last}")
        return None

    if upper.startswith("MOVE:"):
        direction = upper[5:].strip().lower()
        if direction in {"up", "down", "left", "right"}:
            return ("move", direction)
        print("  MOVE directions: up, down, left, right")
        return None

    if upper == "START":
        return ("start", None)
    if upper == "LOOK":
        return ("look", None)
    if upper == "QUIT":
        return ("quit", None)

    lower = cmd.lower()
    if lower in BUTTONS:
        return ("button", lower)
    if lower == "ai":
        return ("ai", None)
    if lower == "speed":
        return ("speed", None)
    if lower == "lead":
        return ("lead", None)
    if lower == "scan":
        return ("scan", None)

    print("  Type a number, letter, MOVE:<dir>, START, LOOK, or QUIT")
    return None


def prompt_poi_selection(pois):
    """Show numbered POI list and return the selected POI dict, or None."""
    if not pois:
        print("Nothing nearby to go to.")
        return None

    print("\n--- Go to ---")
    for i, poi in enumerate(pois, 1):
        print(f"  {i}. {poi['label']} \u2014 {poi['dir']}")
    print(f"  0. Cancel")

    while True:
        try:
            choice = int(_input_fn("Go to: "))
            if choice == 0:
                return None
            if 1 <= choice <= len(pois):
                return pois[choice - 1]
        except (ValueError, EOFError):
            pass
        print(f"Enter 0-{len(pois)}")


def print_pois(pois):
    """Display nearby points of interest."""
    if not pois:
        print("Nothing nearby.")
        return
    print("Nearby:")
    for poi in pois:
        print(f"  {poi['label']} \u2014 {poi['dir']}")


# Icon characters for each POI kind/label on the ASCII map.
_POI_ICONS = {
    "House": "🏠", "Lab": "🔬", "Door": "🚪",
    "Stairs": "🪜", "Exit": "🚪", "Warp": "🌀",
    "Sign": "🪧", "TV": "📺", "PC": "💻", "SNES": "🎮",
    "Bookshelf": "📚", "Desk": "🗄️", "Plant": "🌿",
    "Bed": "🛏️", "Person": "🧑", "Object": "❓",
    "Pokémon": "🐾", "Item": "🔴", "Poké Ball": "🔴", "Boulder": "🪨",
    "Nurse": "💊", "Clerk": "🧑‍💼", "Cable Club": "🔌", "Book": "📖", "Clipboard": "📋",
    "Fossil": "🦴", "Note": "📝",
    # Building types (from destination map names)
    "Pokecenter": "🏥", "Mart": "🛒", "Gym": "🏟️", "Museum": "🏛️",
    "School": "🏫",
}

# Fallback icons by POI kind (for labels not in _POI_ICONS, e.g. map names)
_POI_KIND_ICONS = {
    "connection": "🚪",
    "sprite": "🧑",
    "exit": "🚪",
    "warp": "🚪",
    "grass": "🌿",
}


def _poi_icon(poi):
    """Return the display icon for a POI."""
    label = poi["label"]
    if label in _POI_ICONS:
        return _POI_ICONS[label]
    # Keyword match: "Nickname House" → "House", "Viridian Gym" → "Gym"
    for keyword, icon in _POI_ICONS.items():
        if keyword in label:
            return icon
    return _POI_KIND_ICONS.get(poi.get("kind"), "🚪")


_LEDGE_ARROWS = {"down": "↓", "left": "←", "right": "→"}


def render_map(pois, py, px, grid, visit_counts=None, legend=True, ledges=None):
    """Return an ASCII map string with numbered POI markers and a legend.

    visit_counts: optional list parallel to pois with visit counts per POI.
    legend: if False, omit the text legend below the map (grid only).
    ledges: optional set of (y, x, direction) tuples for one-way tiles.
    """
    if not pois:
        return "Nothing nearby."

    h = len(grid)
    w = len(grid[0]) if h else 0

    poi_at = {}
    for i, poi in enumerate(pois):
        key = (poi["ty"], poi["tx"])
        if key not in poi_at and 0 <= poi["ty"] < h and 0 <= poi["tx"] < w:
            poi_at[key] = str(i + 1)

    # Build ledge lookup: (y, x) → arrow character
    ledge_at = {}
    if ledges:
        for entry in ledges:
            ly, lx, direction = entry
            ledge_at[(ly, lx)] = _LEDGE_ARROWS.get(direction, "·")

    lines = []
    for y in range(h):
        row = ""
        for x in range(w):
            if y == py and x == px:
                row += " @"
            elif (y, x) in poi_at:
                ref = poi_at[(y, x)]
                row += f"{ref:>2}"
            elif (y, x) in ledge_at:
                row += f" {ledge_at[(y, x)]}"
            elif grid[y][x]:
                row += " ·"
            else:
                row += " #"
        lines.append(row)

    if legend:
        lines.append("")
        for i, poi in enumerate(pois):
            icon = _poi_icon(poi)
            suffix = ""
            if visit_counts and visit_counts[i] > 0:
                suffix = f" (visited {visit_counts[i]}x)"
            lines.append(f"  {i + 1:>2}. {icon} {poi['label']}{suffix}")

    return "\n".join(lines)


def print_map(pois, py, px, grid, ledges=None):
    """Display an ASCII map with numbered POI icons and a legend."""
    print(render_map(pois, py, px, grid, ledges=ledges))


def format_move(move):
    """Format a move dict for display (name, type, power, PP, category, desc)."""
    parts = [move["name"]]
    if move.get("type"):
        parts.append(f"[{move['type']}]")
    parts.append(f"Pow:{move.get('power', 0)}")
    parts.append(f"PP:{move.get('pp', 0)}")
    if move.get("category"):
        parts.append(f"({move['category']})")
    if move.get("desc"):
        parts.append(f"— {move['desc']}")
    return " ".join(parts)
