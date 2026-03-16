"""Game orchestration — manages the game loop and state transitions (SRP).

Each _handle_* method is a self-contained state handler (OCP):
adding a new game state means adding a new handler, not modifying existing ones.
Dependencies are injected via constructor (DIP).
"""

from pyboy import PyBoy
from constants import (
    ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH, ADDR_OVERWORLD_MAP,
    ADDR_TILESET, MAP_BORDER, MAP_NAMES,
    ADDR_NUM_SPRITES, ADDR_SPRITE_DATA, ADDR_SPRITE_DATA2,
    ADDR_MENU_Y, ADDR_MENU_X, ADDR_CURRENT_MENU, ADDR_MAX_MENU,
)
from screen import ScreenReader
from menu import MenuReader
from dialogue import DialogueAdvancer
from naming import NameEntry
from overworld import OverworldScanner
from pathfinder import find_best_path
from console import (
    prompt_menu, prompt_name, prompt_command, print_pois, print_map,
    prompt_poi_selection, BUTTONS,
)


class Game:
    def __init__(self, rom_path):
        self._pyboy = PyBoy(rom_path)
        self._screen = ScreenReader(self._pyboy)
        self._menu = MenuReader(self._pyboy, self._screen)
        self._dialogue = DialogueAdvancer(self._pyboy, self._screen)
        self._naming = NameEntry(self._pyboy)
        self._scanner = OverworldScanner(self._pyboy, rom_path)
        self._in_overworld = False
        self._show_pois = False
        self._running = True

    def _map_loaded(self):
        """Check if a valid map is loaded (works for all maps including map 0)."""
        mem = self._pyboy.memory
        return mem[ADDR_MAP_WIDTH] > 0 and mem[ADDR_MAP_HEIGHT] > 0

    def _print_surroundings(self):
        """Print map name and ASCII map of surroundings with numbered POIs."""
        mem = self._pyboy.memory
        map_id = mem[ADDR_MAP_N]
        map_name = MAP_NAMES.get(map_id, f"Map {map_id}")
        print(f"\n--- {map_name} ---")
        pois = self._scanner.get_pois()
        grid, _, _ = self._scanner.get_walkable_grid()
        print_map(pois, mem[ADDR_Y_COORD], mem[ADDR_X_COORD], grid)

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

        if "CONTINUE" in choice:
            for _ in range(600):
                self._pyboy.tick(1)
                if self._screen.read_text_box():
                    self._pyboy.button("a", delay=8)
                    self._pyboy.tick(10)
                if self._map_loaded():
                    self._in_overworld = True
                    self._show_pois = True
                    break

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
        if self._map_loaded():
            if not self._in_overworld:
                self._in_overworld = True
                self._show_pois = True

        return True

    def _process_event(self):
        """Tick through a cutscene/event, handling dialogues and menus inline.

        Keeps ticking until the game state is fully stable: no dialogue,
        no menu activity, player position and map not changing.  Used when
        walking is interrupted by an event (e.g. Oak, trainer battle).
        """
        mem = self._pyboy.memory
        idle = 0
        last_state = None
        last_text = None
        pending_lines = []     # accumulate text captures for deduplication
        while idle < 20:  # ~200 frames of total stability → event over
            self._pyboy.tick(10)

            if self._handle_name_menu():
                idle = 0
                last_text = None
                continue

            # Detect naming keyboard (max_item > 4 = letter grid)
            if mem[ADDR_MAX_MENU] > 4:
                name = prompt_name()
                if name:
                    self._naming.enter(name)
                    print(f"Nickname: {name}")
                else:
                    # Empty = use default name, press Start to confirm
                    self._pyboy.button("start", delay=8)
                    print("Using default name.")
                # Wait for naming screen to fully close
                for _ in range(10):
                    self._pyboy.tick(10)
                idle = 0
                last_text = None
                continue

            # Wait for text to stabilize (letter-by-letter animation)
            text = self._screen.read_text_box()
            if text:
                prev_t = ""
                while text != prev_t:
                    prev_t = text
                    self._pyboy.tick(10)
                    text = self._screen.read_text_box()

            state = (mem[ADDR_MAP_N], mem[ADDR_Y_COORD], mem[ADDR_X_COORD])

            if text:
                if text != last_text:
                    last_text = text
                    pending_lines.append(text)

                # Check if YES/NO menu is drawn on screen
                if self._menu.has_yes_no_on_screen():
                    # Flush accumulated dialogue before showing menu
                    if pending_lines:
                        line = self._dialogue._deduplicate(pending_lines)
                        if line:
                            print(f"\n{line}")
                        pending_lines = []
                    options = self._menu.get_options()
                    valid = [o.strip() for o in options if o.strip()]
                    choice = prompt_menu(valid)
                    self._menu.select(choice, options)
                    self._pyboy.tick(30)
                    idle = 0
                    last_text = None
                    continue

                # Not a menu — press A to advance dialogue
                self._pyboy.button("a", delay=8)
                self._pyboy.tick(20)

                idle = 0
                continue

            # No text on screen — flush accumulated dialogue
            if pending_lines:
                line = self._dialogue._deduplicate(pending_lines)
                if line:
                    print(f"\n{line}")
                pending_lines = []
            last_text = None

            if state != last_state:
                last_state = state
                idle = 0
                continue

            idle += 1

        self._in_overworld = True

    def _handle_overworld(self):
        """Prompt for movement/action commands in the overworld."""
        if not self._in_overworld:
            return False

        if self._show_pois:
            self._show_pois = False
            self._print_surroundings()

        cmd = prompt_command()
        if cmd == "quit":
            self._running = False
        elif cmd == "look":
            self._print_surroundings()
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
            # Show map automatically after movement
            if cmd in {"up", "down", "left", "right"}:
                self._print_surroundings()

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
        start_map = mem[ADDR_MAP_N]
        for direction in path:
            self._pyboy.button(direction, delay=8)
            self._pyboy.tick(30)

            # Detect interruptions: dialogue/cutscene or unexpected map change
            if self._screen.read_text_box():
                print("Interrupted!")
                self._process_event()
                self._print_surroundings()
                return
            if mem[ADDR_MAP_N] != start_map:
                self._in_overworld = True
                self._show_pois = True
                return

        if face is None:
            # Warp (stairs) — walking onto the tile activates it
            self._pyboy.tick(60)
        elif poi["kind"] == "connection":
            # Map connection — step off the edge to transition
            old_map = mem[ADDR_MAP_N]
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(60)
            if mem[ADDR_MAP_N] == old_map:
                print(f"Cannot cross to {poi['label']} (blocked).")
                self._print_surroundings()
                return
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

        # Wait for the game to respond — poll for text/event
        event_detected = False
        for _ in range(20):
            self._pyboy.tick(10)
            if self._screen.read_text_box():
                event_detected = True
                break

        if event_detected:
            print(f"Event at {poi['label']}!")
            self._process_event()
            self._print_surroundings()
            return

        print(f"Arrived at {poi['label']}.")
        self._print_surroundings()

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
        """[DEBUG] Dump the block map with auto-detected walkability."""
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]

        player_block_y = py // 2
        player_block_x = px // 2
        row_width = W + 2 * MAP_BORDER
        tileset = mem[ADDR_TILESET]

        print(f"\nTileset {tileset} | Map {W}x{H} blocks | Player tile ({py},{px})")
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

        # Auto-detect walkability from ROM
        coll = self._scanner.get_collision_tiles()
        if coll:
            print(f"\nCollision tiles: {', '.join(f'${t:02X}' for t in sorted(coll))}")
            print("\nBlocks:")
            for bid in sorted(seen):
                bt = self._scanner.get_block_tiles(bid)
                if bt is None:
                    print(f"  {bid:02X}: ???")
                    continue
                tl, tr, bl, br = self._scanner.block_walkability(bt, coll)
                w = lambda v: '✓' if v else '✗'
                print(f"  {bid:02X}: [{w(tl)}{w(tr)}/{w(bl)}{w(br)}]")
        else:
            print("\n(No ROM data — cannot auto-detect walkability)")

        # Sprite data dump
        from constants import SPRITE_LABELS
        count = mem[ADDR_NUM_SPRITES]
        print(f"\nSprites ({count}):")
        for i in range(1, count + 1):
            base1 = ADDR_SPRITE_DATA + i * 0x10
            base2 = ADDR_SPRITE_DATA2 + i * 0x10
            pic_id = mem[base1]
            label = SPRITE_LABELS.get(pic_id, "Person")
            sy = mem[base2 + 4] - 4
            sx = mem[base2 + 5] - 4
            d1 = " ".join(f"{mem[base1+b]:02X}" for b in range(16))
            print(f"  #{i}: ({label}) pos=({sy},{sx})")
            print(f"       d1: {d1}")

        # Missable object flags — search likely WRAM locations
        print("\nMissable flags hunt:")
        for label, addr in [("$D5A6", 0xD5A6), ("$D728", 0xD728),
                            ("$D747", 0xD747)]:
            data = " ".join(f"{mem[addr+b]:02X}" for b in range(8))
            print(f"  {label}: {data}")
        # Missable object list (sprite_id, flag_bit pairs, $FF terminated)
        print("  wMissableObjectList candidates:")
        for label, addr in [("$D5CE", 0xD5CE), ("$D5B3", 0xD5B3)]:
            data = " ".join(f"{mem[addr+b]:02X}" for b in range(24))
            print(f"    {label}: {data}")
