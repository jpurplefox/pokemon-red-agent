"""Inline cutscene/event processing (SRP).

Ticks through events that interrupt gameplay — dialogue sequences,
YES/NO menus, naming keyboards — until the game state stabilises.
"""

from constants import (
    ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_MAX_MENU, ADDR_IS_IN_BATTLE,
)
from dialogue import DialogueAdvancer
from console import prompt_menu, prompt_name


class EventProcessor:
    def __init__(self, pyboy, screen, menu, naming, name_menu_handler):
        self._pyboy = pyboy
        self._screen = screen
        self._menu = menu
        self._naming = naming
        self._handle_name_menu = name_menu_handler
        self._dialogue = DialogueAdvancer(pyboy, screen)

    def process(self):
        """Tick through a cutscene/event, handling dialogues and menus.

        Keeps ticking until the game state is fully stable: no dialogue,
        no menu activity, player position and map not changing.
        Returns when ~200 frames pass with no state change.
        """
        mem = self._pyboy.memory
        idle = 0
        last_state = None
        last_text = None
        pending_lines = []

        while idle < 20:
            self._pyboy.tick(10)

            # Battle started — stop processing, let battle handler take over
            if mem[ADDR_IS_IN_BATTLE] != 0:
                self._flush_dialogue(pending_lines)
                pending_lines = []
                break

            if self._handle_name_menu():
                idle = 0
                last_text = None
                continue

            # Detect naming keyboard (max_item > 4 = letter grid)
            # Verify by checking for "lower case" / "UPPER CASE" on screen
            if mem[ADDR_MAX_MENU] > 4:
                text_check = self._screen.read_text_box()
                if text_check and ("lower case" in text_check
                                   or "UPPER CASE" in text_check):
                    self._handle_naming_keyboard()
                    idle = 0
                    last_text = None
                    continue

            # Wait for text to stabilise (letter-by-letter animation)
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

                # Brief wait for choice menu to appear after text
                self._pyboy.tick(30)

                # Check if a choice menu (HEAL/CANCEL, YES/NO, etc.)
                # appeared alongside the dialogue text — scan tilemap
                # for cursor tile, no WRAM dependency
                choice_options = self._menu.read_choice_menu()
                if choice_options:
                    self._flush_dialogue(pending_lines)
                    pending_lines = []
                    self._handle_choice_menu(choice_options)
                    idle = 0
                    last_text = None
                    continue

                # Not a menu — press A to advance dialogue
                self._pyboy.button("a", delay=8)
                self._pyboy.tick(20)
                idle = 0
                continue

            # No text on screen — flush accumulated dialogue
            self._flush_dialogue(pending_lines)
            pending_lines = []
            last_text = None

            if state != last_state:
                last_state = state
                idle = 0
                continue

            idle += 1

    def _handle_naming_keyboard(self):
        """Handle the in-game naming keyboard."""
        name = prompt_name()
        if name:
            self._naming.enter(name)
            print(f"Nickname: {name}")
        else:
            self._pyboy.button("start", delay=8)
            print("Using default name.")
        for _ in range(10):
            self._pyboy.tick(10)

    def _handle_choice_menu(self, options):
        """Prompt the user for a choice menu detected on screen."""
        choice = prompt_menu(options)
        # Navigate: cursor starts at top (index 0), press down to target
        target_idx = options.index(choice)
        for _ in range(target_idx):
            self._pyboy.button("down")
            self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(30)

    def _flush_dialogue(self, lines):
        """Deduplicate and print accumulated dialogue lines."""
        if not lines:
            return
        line = DialogueAdvancer.deduplicate(lines)
        if line:
            print(f"\n{line}")
        lines.clear()
