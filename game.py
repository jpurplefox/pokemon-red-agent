"""Game orchestration — manages the game loop and state transitions (SRP).

Each _handle_* method is a self-contained state handler (OCP):
adding a new game state means adding a new handler, not modifying existing ones.
Dependencies are injected via constructor (DIP).
"""

from pyboy import PyBoy
from constants import (
    ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH, ADDR_OVERWORLD_MAP,
    ADDR_TILESET, MAP_BORDER, BLOCK_DESCRIPTIONS, WALKABLE_BLOCKS,
)
from screen import ScreenReader
from menu import MenuReader
from dialogue import DialogueAdvancer
from naming import NameEntry
from overworld import OverworldScanner
from pathfinder import find_best_path
from console import (
    prompt_menu, prompt_name, prompt_command, print_pois,
    prompt_poi_selection, BUTTONS,
)


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
            if not self._in_overworld:
                self._in_overworld = True
                print_pois(self._scanner.get_pois())

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
        elif cmd == "go":
            self._handle_go()
        elif cmd == "start":
            self._pyboy.button("start", delay=8)
            self._pyboy.tick(30)
            self._handle_game_menu()
        elif cmd in BUTTONS:
            self._pyboy.button(cmd, delay=8)
            self._pyboy.tick(30)
            # Show POIs automatically after movement
            if cmd in {"up", "down", "left", "right"}:
                print_pois(self._scanner.get_pois())

        return True

    def _handle_go(self):
        """Select a POI, pathfind to it, walk there, and interact."""
        pois = self._scanner.get_pois()
        poi = prompt_poi_selection(pois)
        if not poi:
            return

        grid, _, _ = self._scanner.get_walkable_grid()
        blocked = self._scanner.get_npc_tiles()
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]

        path, face = find_best_path(grid, (py, px), poi, blocked)
        if path is None:
            print(f"Cannot reach {poi['label']}.")
            return

        print(f"Walking to {poi['label']} ({len(path)} steps)...")
        for direction in path:
            self._pyboy.button(direction, delay=8)
            self._pyboy.tick(30)

        if face is None:
            # Warp (stairs) — walking onto the tile activates it
            self._pyboy.tick(60)
        elif poi["kind"] == "exit":
            # Exit (door) — press down to walk through
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(60)
        else:
            # Sign/Sprite — face the POI and press A
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(30)
            self._pyboy.button("a", delay=8)
            self._pyboy.tick(30)

        print(f"Arrived at {poi['label']}.")
        print_pois(self._scanner.get_pois())

    def _handle_game_menu(self):
        """Handle the start menu and any sub-menus/dialogues it triggers.

        Distinguishes dialogue from menu overlay by checking the LEFT side
        of the text box area: dialogue fills the full width, menus only
        appear on the right side of the screen.
        """
        while True:
            # Dialogue fills full screen width; menus only cover the right side.
            # Text on the left half (cols 1-8) means a real text box is open.
            is_dialogue = any(
                self._screen.decode_tiles(row, 1, 8).strip()
                for row in range(13, 17)
            )
            if is_dialogue:
                full = self._dialogue.advance_until(
                    lambda d, u: d and u > 15
                )
                if full:
                    print(f"\n{full}")
                self._pyboy.tick(30)
                continue

            # Read menu options (filter empty trailing entries)
            raw_options = self._menu.get_options()
            valid = [opt for opt in raw_options if opt.strip()]
            if not valid:
                break

            choice = prompt_menu(valid + ["BACK"])
            if choice == "BACK":
                self._pyboy.button("b", delay=8)
                self._pyboy.tick(30)
            else:
                self._menu.select(choice, raw_options)
                self._pyboy.tick(30)

    def _debug_scan(self):
        """[DEBUG] Dump the block map for the current room."""
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]

        player_block_y = py // 2
        player_block_x = px // 2
        row_width = W + 2 * MAP_BORDER

        tileset = mem[ADDR_TILESET]
        descriptions = BLOCK_DESCRIPTIONS.get(tileset, {})
        walkable = WALKABLE_BLOCKS.get(tileset, {})

        print(f"\nTileset {tileset} | Map {W}x{H} blocks | Player tile ({py},{px}) = block ({player_block_y},{player_block_x})")
        header = "     " + "".join(f" {c:<3}" for c in range(W))
        print(header)

        seen = set()
        for row in range(H):
            cells = []
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                bid = mem[addr]
                seen.add(bid)
                if row == player_block_y and col == player_block_x:
                    cells.append(f"[{bid:02X}]")
                else:
                    cells.append(f" {bid:02X} ")
            print(f"  {row}: " + "".join(cells))

        # Legend: show known/unknown blocks
        known = []
        unknown = []
        for bid in sorted(seen):
            if bid in descriptions:
                tl, tr, bl, br = descriptions[bid]
                wk = walkable.get(bid, (False, False, False, False))
                tiles = f"{tl}({'✓' if wk[0] else '✗'}), {tr}({'✓' if wk[1] else '✗'}) / {bl}({'✓' if wk[2] else '✗'}), {br}({'✓' if wk[3] else '✗'})"
                known.append(f"  {bid:02X}: {tiles}")
            else:
                unknown.append(f"{bid:02X}")

        if known:
            print("\nConocidos:")
            for line in known:
                print(line)
        if unknown:
            print(f"\n??? Sin mapear: {', '.join(unknown)}")
