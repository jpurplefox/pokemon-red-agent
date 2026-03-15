from pyboy import PyBoy
from constants import ADDR_MAP_N
from screen import ScreenReader
from menu import MenuReader
from dialogue import DialogueAdvancer
from naming import NameEntry

BUTTONS = {"up", "down", "left", "right", "a", "b", "start", "select"}


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


def main():
    pyboy = PyBoy("rom.gb")
    screen = ScreenReader(pyboy)
    menu = MenuReader(pyboy, screen)
    dialogue = DialogueAdvancer(pyboy, screen)
    naming = NameEntry(pyboy)

    print("Skipping intro...")
    menu.wait_for_main_menu()

    # Handle main menu (NEW GAME / CONTINUE / OPTION)
    pyboy.tick(30)
    options = menu.get_options()
    choice = prompt_menu(options)
    menu.select(choice, options)
    pyboy.tick(30)

    in_overworld = False

    while True:
        pyboy.tick(10)

        # 1. Name menu (4 options) — may need name entry
        if menu.is_name_menu():
            in_overworld = False
            options = menu.get_options()
            choice = prompt_menu(options)
            menu.select(choice, options)
            pyboy.tick(30)
            if "NEW NAME" in choice:
                name = prompt_name()
                naming.enter(name)
                print(f"Name: {name}")
            continue

        # 2. Dialogue — auto-advance and print
        text = screen.read_text_box()
        if text:
            full = dialogue.advance_until(
                lambda d, u: menu.is_name_menu() or (d and u > 15)
            )
            if full:
                print(f"\n{full}")
            # After dialogue ends, check if we reached the overworld
            pyboy.tick(30)
            if pyboy.memory[ADDR_MAP_N] != 0:
                in_overworld = True
            continue

        # 3. Overworld — prompt for commands
        if in_overworld:
            cmd = input("> ").strip().lower()
            if cmd == "quit":
                break
            if cmd in BUTTONS:
                pyboy.button(cmd)
                pyboy.tick(20)
            elif cmd:
                print("Commands: up, down, left, right, a, b, start, select, quit")
            continue

        # 4. Transition — keep ticking

    pyboy.stop()


if __name__ == "__main__":
    main()
