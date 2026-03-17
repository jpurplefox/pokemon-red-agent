"""Game orchestration — manages the game loop and state transitions (SRP).

Each _handle_* method is a self-contained state handler (OCP):
adding a new game state means adding a new handler, not modifying existing ones.
Dependencies are injected via constructor (DIP).
"""

from pyboy import PyBoy
from constants import (
    ADDR_MAP_N, ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH, MAP_NAMES,
    ADDR_Y_COORD, ADDR_X_COORD,
)
from screen import ScreenReader
from menu import MenuReader
from dialogue import DialogueAdvancer
from naming import NameEntry
from overworld import OverworldScanner
from event_processor import EventProcessor
from navigator import Navigator
from battle import BattleHandler
from debug_scanner import DebugScanner
from console import (
    prompt_menu, prompt_name, prompt_command, print_map, BUTTONS,
)


class Game:
    def __init__(self, rom_path, battle_strategy=None, naming_ai=None):
        self._pyboy = PyBoy(rom_path, sound_emulated=False)
        self._screen = ScreenReader(self._pyboy)
        self._menu = MenuReader(self._pyboy, self._screen)
        self._dialogue = DialogueAdvancer(self._pyboy, self._screen)
        self._naming = NameEntry(self._pyboy)
        self._scanner = OverworldScanner(self._pyboy, rom_path)

        self._event_processor = EventProcessor(
            self._pyboy, self._screen, self._menu,
            self._naming, self._handle_name_menu,
        )
        self._navigator = Navigator(
            self._pyboy, self._screen, self._scanner, self._event_processor,
        )
        self._battle = BattleHandler(
            self._pyboy, self._screen, self._menu, self._dialogue,
            strategy=battle_strategy, naming_ai=naming_ai,
        )
        self._debug = DebugScanner(self._pyboy, self._scanner)

        self._in_overworld = False
        self._in_battle = False
        self._show_pois = False
        self._running = True

    # ------------------------------------------------------------------
    # Map / display helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Game lifecycle
    # ------------------------------------------------------------------

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

            if self._handle_battle():
                continue
            if self._handle_name_menu():
                continue
            if self._handle_dialogue():
                continue
            if self._handle_overworld():
                continue

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_name_menu(self):
        """Handle name selection menus (player/rival name)."""
        if self._battle.is_in_battle():
            return False
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

    def _handle_battle(self):
        """Detect and manage Pokemon battles."""
        if not self._battle.is_in_battle():
            if self._in_battle:
                # Battle just ended — use event_processor to handle
                # post-battle dialogue, nickname prompts, menus, etc.
                self._in_battle = False
                print("\nBattle ended!")
                self._event_processor.process()
                self._in_overworld = True
                self._show_pois = True
            return False

        if not self._in_battle:
            # Just entered a battle — advance intro and show summary
            self._in_battle = True
            self._in_overworld = False
            self._battle._last_move_idx = 0  # cursor starts at 0
            self._battle.process_intro()
            self._battle.print_summary()

        # Prompt for battle action
        self._battle.prompt_action()

        # Process the turn result (attack messages, etc.)
        battle_continues = self._battle.process_turn()

        if not battle_continues and self._battle.is_in_battle():
            # Non-battle event mid-battle (e.g. nickname prompt after
            # catching). Hand off to event_processor then re-evaluate.
            self._in_battle = False
            self._event_processor.process()
            return True

        # Show updated state if still in battle
        if battle_continues:
            self._battle.print_summary()

        return True

    def _handle_dialogue(self):
        """Auto-advance dialogue, print text, detect overworld transition."""
        text = self._screen.read_text_box()
        if not text:
            return False

        full = self._dialogue.advance_until(
            lambda d, u: (self._battle.is_in_battle()
                          or self._menu.is_name_menu()
                          or (d and u > 15))
        )
        if full:
            print(f"\n{full}")

        self._pyboy.tick(30)
        if self._map_loaded():
            if not self._in_overworld:
                self._in_overworld = True
                self._show_pois = True

        return True

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
            self._debug.dump()
        elif cmd == "go":
            result = self._navigator.go(self._print_surroundings)
            # Always restore overworld state after navigation — handlers
            # like _handle_name_menu may have cleared it during events.
            self._in_overworld = True
            if result.get("show_pois"):
                self._show_pois = True
        elif cmd == "lead":
            self._change_lead()
        elif cmd == "start":
            self._pyboy.button("start", delay=8)
            self._pyboy.tick(30)
            self._handle_game_menu()
        elif cmd in BUTTONS:
            self._pyboy.button(cmd, delay=8)
            self._pyboy.tick(30)
            if cmd in {"up", "down", "left", "right"}:
                self._print_surroundings()

        return True

    def _change_lead(self):
        """Let the player choose a new lead Pokemon via the in-game party menu."""
        from constants import ADDR_CURRENT_MENU

        party = self._battle._read_party()
        if len(party) <= 1:
            print("Only one Pokemon in party.")
            return

        # Show party and ask who should lead
        print("\n--- Choose Lead ---")
        options = []
        for i, mon in enumerate(party):
            label = mon['nickname']
            if mon['nickname'] != mon['name']:
                label = f"{mon['name']} ({mon['nickname']})"
            lead = " ⭐" if i == 0 else ""
            fainted = " 💀" if mon['hp'] <= 0 else ""
            options.append(
                f"{label} Lv{mon['level']}"
                f"  {mon['hp']}/{mon['max_hp']} HP{lead}{fainted}"
            )
        options.append("Cancel")
        choice = prompt_menu(options)

        if choice == "Cancel":
            return

        # Find the selected party index
        selected_idx = options.index(choice)
        if selected_idx == 0:
            print("Already the lead!")
            return

        # Open START menu
        self._pyboy.button("start", delay=8)
        self._pyboy.tick(30)

        # Select POKéMON from start menu using menu reader
        start_opts = self._menu.get_options()
        pokemon_opt = next(
            (o for o in start_opts
             if "POK" in o.upper() and "DEX" not in o.upper()),
            None,
        )
        if not pokemon_opt:
            print(f"Could not find POKéMON in start menu: {start_opts}")
            self._pyboy.button("b", delay=8)
            self._pyboy.tick(15)
            return
        self._menu.select(pokemon_opt, start_opts)
        self._pyboy.tick(40)

        # Navigate party list to the target pokemon
        current = self._pyboy.memory[ADDR_CURRENT_MENU]
        diff = selected_idx - current
        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down")
                self._pyboy.tick(10)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up")
                self._pyboy.tick(10)

        # Press A to open the sub-menu for this pokemon
        self._pyboy.button("a")
        self._pyboy.tick(40)

        # Read sub-menu and select SWITCH
        sub_opts = self._menu.get_options()
        switch_opt = next(
            (o for o in sub_opts if "SWITCH" in o.upper()),
            None,
        )
        if not switch_opt:
            print(f"Could not find SWITCH in sub-menu: {sub_opts}")
            for _ in range(5):
                self._pyboy.button("b", delay=8)
                self._pyboy.tick(30)
            return
        self._menu.select(switch_opt, sub_opts)
        self._pyboy.tick(40)

        # Pick the swap target: navigate to position 0 (the lead)
        current = self._pyboy.memory[ADDR_CURRENT_MENU]
        for _ in range(current):
            self._pyboy.button("up")
            self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(30)

        # Close remaining menus: party list → START menu → overworld
        for _ in range(5):
            self._pyboy.button("b", delay=8)
            self._pyboy.tick(30)

        # Verify the swap
        new_party = self._battle._read_party()
        new_lead = new_party[0]
        label = new_lead['nickname']
        if new_lead['nickname'] != new_lead['name']:
            label = f"{new_lead['name']} ({new_lead['nickname']})"
        print(f"New lead: {label} Lv{new_lead['level']}!")
        self._show_pois = True

    def _handle_game_menu(self):
        """Handle the start menu and any sub-menus/dialogues it triggers."""
        while True:
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
