"""Console UI for interacting with the game (SRP: user input/output only)."""

BUTTONS = {"up", "down", "left", "right", "a", "b", "start", "select"}
COMMANDS = BUTTONS | {"quit", "look", "scan", "go"}


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
