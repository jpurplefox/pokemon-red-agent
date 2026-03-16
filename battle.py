"""Battle system — detects battles and manages the combat loop (SRP).

Handles battle state detection, auto-advancing intro dialogue,
displaying battle summaries, and prompting for battle actions.
Dependencies injected via constructor (DIP).
"""

from constants import (
    ADDR_IS_IN_BATTLE, ADDR_BATTLE_MON, ADDR_ENEMY_MON,
    BMON_SPECIES, BMON_HP, BMON_STATUS, BMON_MOVES,
    BMON_PP, BMON_LEVEL, BMON_MAX_HP,
)
from pokemon_data import POKEMON_NAMES, MOVE_NAMES, MOVE_BASE_PP, status_text
from console import prompt_menu


class BattleHandler:
    def __init__(self, pyboy, screen, menu, dialogue):
        self._pyboy = pyboy
        self._screen = screen
        self._menu = menu
        self._dialogue = dialogue
        self._last_move_idx = 0  # move menu cursor starts at 0

    # ------------------------------------------------------------------
    # State detection
    # ------------------------------------------------------------------

    def is_in_battle(self):
        """Check if we're currently in a battle."""
        return self._pyboy.memory[ADDR_IS_IN_BATTLE] != 0

    def is_wild(self):
        return self._pyboy.memory[ADDR_IS_IN_BATTLE] == 1

    def is_trainer(self):
        return self._pyboy.memory[ADDR_IS_IN_BATTLE] == 2

    def has_battle_menu(self):
        """Check if the main battle menu (FIGHT/ITEM/RUN) is on screen.

        Scans the bottom portion of the screen (rows 14-17, cols 8-19)
        for the "FIGHT" text that appears in the battle action menu.
        """
        for row in range(14, 18):
            text = self._screen.decode_tiles(row, 8, 12)
            if "FIGHT" in text:
                return True
        return False

    # ------------------------------------------------------------------
    # Battle intro
    # ------------------------------------------------------------------

    def process_intro(self):
        """Advance through battle intro until the battle menu appears.

        Handles "Wild X appeared!", "Go! Y!", and any pre-battle dialogue.
        Prints all dialogue text, then returns when ready for player input.
        """
        full = self._dialogue.advance_until(
            lambda d, u: self.has_battle_menu()
        )
        if full:
            # Filter out garbage from battle transition animation
            # (screen shows digit tiles during the screen flash)
            clean = " ".join(
                w for w in full.split()
                if not all(c in "0123456789" for c in w)
            )
            if clean.strip():
                print(f"\n{clean.strip()}")

    # ------------------------------------------------------------------
    # Battle summary
    # ------------------------------------------------------------------

    def _read_mon(self, base):
        """Read a battle mon's stats from WRAM."""
        mem = self._pyboy.memory
        species = mem[base + BMON_SPECIES]
        hp = (mem[base + BMON_HP] << 8) | mem[base + BMON_HP + 1]
        max_hp = (mem[base + BMON_MAX_HP] << 8) | mem[base + BMON_MAX_HP + 1]
        level = mem[base + BMON_LEVEL]
        status = status_text(mem[base + BMON_STATUS])
        name = POKEMON_NAMES.get(species, f"#{species:02X}")

        moves = []
        for i in range(4):
            move_id = mem[base + BMON_MOVES + i]
            if move_id == 0:
                continue
            pp_byte = mem[base + BMON_PP + i]
            pp = pp_byte & 0x3F          # lower 6 bits = current PP
            pp_ups = pp_byte >> 6         # upper 2 bits = PP Up count
            base_pp = MOVE_BASE_PP.get(move_id, 0)
            max_pp = base_pp + (base_pp * pp_ups) // 5
            move_name = MOVE_NAMES.get(move_id, f"Move #{move_id}")
            moves.append((move_name, pp, max_pp))

        return {
            "name": name, "level": level,
            "hp": hp, "max_hp": max_hp,
            "status": status, "moves": moves,
        }

    def print_summary(self):
        """Print the current battle state: both pokemon and available moves."""
        player = self._read_mon(ADDR_BATTLE_MON)
        enemy = self._read_mon(ADDR_ENEMY_MON)

        battle_type = "Wild" if self.is_wild() else "Trainer"
        print(f"\n{'=' * 40}")
        print(f"  {battle_type} Battle")
        print(f"{'=' * 40}")

        # Enemy pokemon
        e_status = f" [{enemy['status']}]" if enemy['status'] else ""
        print(f"  Enemy: {enemy['name']} Lv{enemy['level']}"
              f"  HP: {enemy['hp']}/{enemy['max_hp']}{e_status}")

        # Player pokemon
        p_status = f" [{player['status']}]" if player['status'] else ""
        print(f"  Your:  {player['name']} Lv{player['level']}"
              f"  HP: {player['hp']}/{player['max_hp']}{p_status}")

        # Player moves
        print(f"{'-' * 40}")
        print("  Moves:")
        for i, (name, pp, max_pp) in enumerate(player['moves'], 1):
            print(f"    {i}. {name:<14} {pp}/{max_pp} PP")
        print(f"{'=' * 40}")

    # ------------------------------------------------------------------
    # Battle actions
    # ------------------------------------------------------------------

    def prompt_action(self):
        """Prompt the user for a battle action and execute it."""
        player = self._read_mon(ADDR_BATTLE_MON)

        # Build action list: moves + RUN (for wild battles)
        actions = []
        for name, pp, max_pp in player['moves']:
            actions.append(f"{name} ({pp}/{max_pp} PP)")
        if self.is_wild():
            actions.append("RUN")

        choice = prompt_menu(actions)

        if "RUN" in choice:
            self._select_battle_option("RUN")
        else:
            # User picked a move — select FIGHT then the move
            move_name = choice.split(" (")[0]
            move_idx = next(
                i for i, (n, _, _) in enumerate(player['moves'])
                if n == move_name
            )
            self._select_battle_option("FIGHT")
            self._wait_for_move_menu(player['moves'])
            self._select_move(move_idx)

    def _wait_for_move_menu(self, moves):
        """Wait for the move selection menu to appear after selecting FIGHT.

        Polls until the battle action menu (FIGHT/ITEM/RUN) disappears
        and the first move name is visible on screen.
        """
        first_move = moves[0][0] if moves else ""
        for _ in range(60):  # up to ~600 frames
            self._pyboy.tick(10)
            # Battle action menu gone = move menu is loading/loaded
            if not self.has_battle_menu():
                break

        # Now wait for the actual move name to appear on screen
        if first_move:
            for _ in range(30):
                for row in range(14, 18):
                    text = self._screen.decode_tiles(row, 1, 12)
                    if first_move in text:
                        self._pyboy.tick(5)  # small buffer for input readiness
                        return
                self._pyboy.tick(10)

    def _select_battle_option(self, option):
        """Select FIGHT, ITEM, PKMN, or RUN from the battle menu.

        Battle menu layout (2x2 grid):
          FIGHT  PkMn    (row 0: col 0, col 1)
          ITEM   RUN     (row 1: col 0, col 1)

        Navigates by resetting to top-left (FIGHT) first, then
        moving to the target — no memory reads needed.
        """
        targets = {"FIGHT": (0, 0), "PKMN": (0, 1),
                   "ITEM": (1, 0), "RUN": (1, 1)}
        row, col = targets.get(option, (0, 0))

        # Reset to FIGHT (top-left)
        self._pyboy.button("up")
        self._pyboy.tick(8)
        self._pyboy.button("left")
        self._pyboy.tick(8)

        # Navigate to target
        for _ in range(row):
            self._pyboy.button("down")
            self._pyboy.tick(8)
        for _ in range(col):
            self._pyboy.button("right")
            self._pyboy.tick(8)

        self._pyboy.button("a")
        self._pyboy.tick(10)

    def _select_move(self, move_idx):
        """Select a move by index (0-3) from the move menu.

        Navigates from the last known cursor position (the move menu
        in Pokemon Red remembers/wraps, so blind resets don't work).
        """
        # Navigate from last known position
        current = self._last_move_idx
        diff = move_idx - current
        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down")
                self._pyboy.tick(8)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up")
                self._pyboy.tick(8)

        self._pyboy.button("a")
        self._pyboy.tick(10)
        self._last_move_idx = move_idx

    def process_turn(self):
        """Advance through turn messages until the battle menu reappears
        or the battle ends."""
        full = self._dialogue.advance_until(
            lambda d, u: (self.has_battle_menu()
                          or not self.is_in_battle()
                          or (d and u > 30))
        )
        if full:
            print(f"\n{full}")
