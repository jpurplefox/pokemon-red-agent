"""Game orchestration — manages the game loop and state transitions (SRP).

Each _handle_* method is a self-contained state handler (OCP):
adding a new game state means adding a new handler, not modifying existing ones.
Dependencies are injected via constructor (DIP).
"""

from pyboy import PyBoy
from constants import ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD
from screen import ScreenReader
from menu import MenuReader
from dialogue import DialogueAdvancer
from naming import NameEntry
from overworld import OverworldScanner
from console import prompt_menu, prompt_name, prompt_command, print_pois, BUTTONS


class Game:
    def __init__(self, rom_path):
        self._pyboy = PyBoy(rom_path)
        self._screen = ScreenReader(self._pyboy)
        self._menu = MenuReader(self._pyboy, self._screen)
        self._dialogue = DialogueAdvancer(self._pyboy, self._screen)
        self._naming = NameEntry(self._pyboy)
        self._scanner = OverworldScanner(self._pyboy)
        self._in_overworld = False
        self._running = True

    def run(self):
        """Start the game: skip intro, handle main menu, enter game loop."""
        print("Skipping intro...")
        self._menu.wait_for_main_menu()
        self._handle_main_menu()
        self._game_loop()
        self._pyboy.stop()

    def _handle_main_menu(self):
        """Handle the initial NEW GAME / CONTINUE / OPTION menu."""
        self._pyboy.tick(30)
        options = self._menu.get_options()
        choice = prompt_menu(options)
        self._menu.select(choice, options)
        self._pyboy.tick(30)

    def _game_loop(self):
        """Main game loop — detect state and dispatch to handlers."""
        while self._running:
            self._pyboy.tick(10)

            if self._handle_name_menu():
                continue
            if self._handle_dialogue():
                continue
            if self._handle_overworld():
                continue
            # No event detected — transition, keep ticking

    def _handle_name_menu(self):
        """Handle name selection menus (player/rival name)."""
        if not self._menu.is_name_menu():
            return False

        self._in_overworld = False
        options = self._menu.get_options()
        choice = prompt_menu(options)
        self._menu.select(choice, options)
        self._pyboy.tick(30)

        if "NEW NAME" in choice:
            name = prompt_name()
            self._naming.enter(name)
            print(f"Name: {name}")

        return True

    def _handle_dialogue(self):
        """Auto-advance dialogue, print text, detect overworld transition."""
        text = self._screen.read_text_box()
        if not text:
            return False

        full = self._dialogue.advance_until(
            lambda d, u: self._menu.is_name_menu() or (d and u > 15)
        )
        if full:
            print(f"\n{full}")

        # After dialogue ends, check if we reached the overworld
        self._pyboy.tick(30)
        if self._pyboy.memory[ADDR_MAP_N] != 0:
            self._in_overworld = True

        return True

    def _handle_overworld(self):
        """Prompt for movement/action commands in the overworld."""
        if not self._in_overworld:
            return False

        cmd = prompt_command()
        if cmd == "quit":
            self._running = False
        elif cmd == "look":
            print_pois(self._scanner.get_pois())
        elif cmd == "scan":
            self._debug_scan()
        elif cmd in BUTTONS:
            self._pyboy.button(cmd, delay=8)
            self._pyboy.tick(30)
            # Show POIs automatically after movement
            if cmd in {"up", "down", "left", "right"}:
                print_pois(self._scanner.get_pois())

        return True

    def _debug_scan(self):
        """[DEBUG] Dump the block map for the current room."""
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        W = mem[0xD369]   # wCurMapWidth (blocks)
        H = mem[0xD368]   # wCurMapHeight (blocks)
        B = 3             # MAP_BORDER (blocks)
        base = 0xC6E8     # wOverworldMap

        player_block_y = py // 2
        player_block_x = px // 2
        row_width = W + 2 * B

        tileset = mem[0xD367]
        print(f"\nTileset {tileset} | Map {W}x{H} blocks | Player tile ({py},{px}) = block ({player_block_y},{player_block_x})")
        header = "     " + "".join(f" {c:<3}" for c in range(W))
        print(header)
        for row in range(H):
            cells = []
            for col in range(W):
                addr = base + (row + B) * row_width + (col + B)
                bid = mem[addr]
                if row == player_block_y and col == player_block_x:
                    cells.append(f"[{bid:02X}]")
                else:
                    cells.append(f" {bid:02X} ")
            print(f"  {row}: " + "".join(cells))
