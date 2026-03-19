"""Console UI for interacting with the game (SRP: user input/output only)."""

BUTTONS = {"up", "down", "left", "right", "a", "b", "start", "select"}
COMMANDS = BUTTONS | {"quit", "look", "scan", "go", "lead", "ai"}


def prompt_menu(options):
    """Show numbered menu options and return the user's choice."""
    print("\n--- Menu ---")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        try:
            choice = int(input("Choose: "))
            if 1 <= choice <= len(options):
                return options[choice - 1]
        except (ValueError, EOFError):
            pass
        print(f"Enter 1-{len(options)}")


def prompt_name():
    """Ask the user to type a name (1-7 uppercase letters)."""
    while True:
        name = input("Enter name: ").strip().upper()
        if 1 <= len(name) <= 7 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ " for c in name):
            return name
        print("1-7 letters A-Z only")


def prompt_command():
    """Prompt for an overworld command. Returns the command string."""
    cmd = input("> ").strip().lower()
    if cmd and cmd not in COMMANDS:
        print("Commands: up, down, left, right, a, b, start, select, look, go, quit")
        return None
    return cmd


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
            choice = int(input("Go to: "))
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
    "connection": "🛤️",
    "sprite": "🧑",
    "exit": "🚪",
    "warp": "🌀",
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


def render_map(pois, py, px, grid, visit_counts=None):
    """Return an ASCII map string with numbered POI markers and a legend.

    visit_counts: optional list parallel to pois with visit counts per POI.
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

    lines = []
    for y in range(h):
        row = ""
        for x in range(w):
            if y == py and x == px:
                row += " @"
            elif (y, x) in poi_at:
                ref = poi_at[(y, x)]
                row += f"{ref:>2}"
            elif grid[y][x]:
                row += " ·"
            else:
                row += " #"
        lines.append(row)

    lines.append("")
    for i, poi in enumerate(pois):
        icon = _poi_icon(poi)
        suffix = ""
        if visit_counts and visit_counts[i] > 0:
            suffix = f" (visited {visit_counts[i]}x)"
        lines.append(f"  {i + 1:>2}. {icon} {poi['label']}{suffix}")

    return "\n".join(lines)


def print_map(pois, py, px, grid):
    """Display an ASCII map with numbered POI icons and a legend."""
    print(render_map(pois, py, px, grid))
