"""Battle system — detects battles and manages the combat loop (SRP).

Handles battle state detection, auto-advancing intro dialogue,
displaying battle summaries, and prompting for battle actions.
Dependencies injected via constructor (DIP).
"""

from constants import (
    ADDR_IS_IN_BATTLE, ADDR_BATTLE_MON, ADDR_ENEMY_MON,
    BMON_SPECIES, BMON_HP, BMON_STATUS, BMON_MOVES,
    BMON_PP, BMON_LEVEL, BMON_MAX_HP,
    ADDR_NUM_BAG_ITEMS, ADDR_BAG_ITEMS, BALL_ITEMS,
    ADDR_PARTY_COUNT, ADDR_PARTY_SPECIES, ADDR_PARTY_MONS,
    PARTY_MON_SIZE, PARTY_MON_LEVEL,
    ADDR_PARTY_NICKS, PARTY_NICK_SIZE,
)
from pokemon_data import POKEMON_NAMES, MOVE_NAMES, MOVE_BASE_PP, status_text
from constants import POKEMON_CHARMAP
from console import prompt_menu


class BattleHandler:
    def __init__(self, pyboy, screen, menu, dialogue, strategy=None,
                 naming_ai=None):
        self._pyboy = pyboy
        self._screen = screen
        self._menu = menu
        self._dialogue = dialogue
        self._last_move_idx = 0  # move menu cursor starts at 0
        self._strategy = strategy or ManualStrategy()
        self._naming_ai = naming_ai

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

        # Update strategy with current team roster and notify of battle start
        if hasattr(self._strategy, 'set_team'):
            self._strategy.set_team(self._read_party())
        if hasattr(self._strategy, 'on_battle_start'):
            player = self._read_mon(ADDR_BATTLE_MON)
            enemy = self._read_mon(ADDR_ENEMY_MON)
            balls = self.get_balls() if self.is_wild() else []
            self._strategy.on_battle_start(player, enemy, self.is_wild(), balls)

    # ------------------------------------------------------------------
    # Battle summary
    # ------------------------------------------------------------------

    def _read_enemy_species(self):
        """Read the enemy Pokemon's species name."""
        mem = self._pyboy.memory
        species = mem[ADDR_ENEMY_MON + BMON_SPECIES]
        return POKEMON_NAMES.get(species, f"POKEMON#{species:02X}")

    def _read_party(self):
        """Read the player's party: list of {name, level, nickname}."""
        mem = self._pyboy.memory
        count = mem[ADDR_PARTY_COUNT]
        party = []
        for i in range(min(count, 6)):
            species_id = mem[ADDR_PARTY_SPECIES + i]
            name = POKEMON_NAMES.get(species_id, f"#{species_id:02X}")
            base = ADDR_PARTY_MONS + i * PARTY_MON_SIZE
            level = mem[base + PARTY_MON_LEVEL]
            # Read nickname from WRAM
            nick_base = ADDR_PARTY_NICKS + i * PARTY_NICK_SIZE
            nickname = ""
            for j in range(10):
                tile = mem[nick_base + j]
                if tile == 0x50:
                    break
                nickname += POKEMON_CHARMAP.get(tile, "")
            party.append({
                "name": name,
                "level": level,
                "nickname": nickname.strip() or name,
            })
        return party

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

        # Show balls in wild battles
        if self.is_wild():
            balls = self.get_balls()
            if balls:
                print("  Bag:")
                for ball_name, count, _ in balls:
                    print(f"    🔴 {ball_name} ×{count}")
        print(f"{'=' * 40}")

    # ------------------------------------------------------------------
    # Bag / Poké Balls
    # ------------------------------------------------------------------

    def get_balls(self):
        """Return list of (item_name, count) for Poké Balls in the bag."""
        mem = self._pyboy.memory
        num_items = mem[ADDR_NUM_BAG_ITEMS]
        balls = []
        for i in range(num_items):
            item_id = mem[ADDR_BAG_ITEMS + i * 2]
            count = mem[ADDR_BAG_ITEMS + i * 2 + 1]
            if item_id in BALL_ITEMS:
                balls.append((BALL_ITEMS[item_id], count, i))
        return balls

    # ------------------------------------------------------------------
    # Battle actions
    # ------------------------------------------------------------------

    def prompt_action(self):
        """Decide and execute a battle action using the injected strategy."""
        player = self._read_mon(ADDR_BATTLE_MON)
        enemy = self._read_mon(ADDR_ENEMY_MON)
        balls = self.get_balls() if self.is_wild() else []

        action_type, detail = self._strategy.decide(
            player, enemy, self.is_wild(), balls
        )

        if action_type == "cancel":
            self._pyboy.button("b")
            self._pyboy.tick(10)
            return
        elif action_type == "run":
            self._select_battle_option("RUN")
        elif action_type == "ball":
            self._use_ball(detail)
        else:
            move_idx = next(
                (i for i, (n, _, _) in enumerate(player['moves'])
                 if n == detail),
                0,
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

    def _use_ball(self, bag_index):
        """Select ITEM from battle menu, then select the ball by bag index."""
        self._select_battle_option("ITEM")
        # Wait for item menu to appear
        for _ in range(30):
            self._pyboy.tick(10)
            if not self.has_battle_menu():
                break

        # Navigate to the ball's position in the bag list
        # Reset cursor to top
        for _ in range(10):
            self._pyboy.button("up")
            self._pyboy.tick(5)

        # Move down to the item
        for _ in range(bag_index):
            self._pyboy.button("down")
            self._pyboy.tick(8)

        # Select the item
        self._pyboy.button("a")
        self._pyboy.tick(20)

        # If the game asks "Use this item?" just confirm
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
        """Advance through turn messages until the battle menu reappears,
        the battle ends, or a choice/naming event appears.

        Handles mid-battle events inline (e.g. nickname prompt after catch).
        Returns True if the battle continues, False if ended.
        """
        while True:
            full = self._dialogue.advance_until(
                lambda d, u: (self.has_battle_menu()
                              or not self.is_in_battle()
                              or self._has_choice_or_naming())
            )
            if full:
                print(f"\n{full}")

            if self.has_battle_menu() and self.is_in_battle():
                return True
            if not self.is_in_battle():
                return False

            # Handle mid-battle events (choice menu or naming keyboard)
            if not self._handle_mid_battle_event():
                return False

    def _handle_mid_battle_event(self):
        """Handle a choice menu or naming keyboard that appeared mid-battle.

        Returns True to keep processing, False if battle ended.
        """
        # Wait a bit for menu to fully render
        self._pyboy.tick(30)

        # Detect nickname prompt: YES/NO choice or naming keyboard
        text = self._screen.read_text_box() or ""
        lower_text = text.lower()
        is_nickname_prompt = "nickname" in lower_text
        is_naming_keyboard = "lower case" in lower_text or "upper case" in lower_text

        if is_nickname_prompt or is_naming_keyboard:
            # Get the species of the caught Pokemon from enemy data
            caught_species = self._read_enemy_species()

            if self._naming_ai:
                # Read actual party with real nicknames from WRAM
                # Exclude last entry — it's the Pokemon we just caught
                party = self._read_party()[:-1]
                team_context = [
                    (m['name'], m['nickname']) for m in party
                ]
                name = self._naming_ai.suggest_name(
                    caught_species, team_context
                )
            else:
                name = input("Enter nickname (empty to skip): ").strip()

            if is_nickname_prompt:
                # We're at the YES/NO menu
                options = self._menu.read_choice_menu()
                if not name:
                    # Select NO
                    no_idx = len(options) - 1 if options else 1
                    for _ in range(10):
                        self._pyboy.button("up")
                        self._pyboy.tick(5)
                    for _ in range(no_idx):
                        self._pyboy.button("down")
                        self._pyboy.tick(10)
                    self._pyboy.button("a")
                    self._pyboy.tick(30)
                else:
                    # Select YES (first option)
                    for _ in range(10):
                        self._pyboy.button("up")
                        self._pyboy.tick(5)
                    self._pyboy.button("a")
                    self._pyboy.tick(60)
                    # Now type the name on the keyboard
                    self._type_on_naming_keyboard(name.upper()[:10])
            elif is_naming_keyboard:
                if not name:
                    self._pyboy.button("b")
                    self._pyboy.tick(60)
                else:
                    self._type_on_naming_keyboard(name.upper()[:10])
            return not self.is_in_battle()

        # Check for other choice menus
        options = self._menu.read_choice_menu()
        if options:
            choice = prompt_menu(options)
            target_idx = options.index(choice)
            for _ in range(10):
                self._pyboy.button("up")
                self._pyboy.tick(5)
            for _ in range(target_idx):
                self._pyboy.button("down")
                self._pyboy.tick(10)
            self._pyboy.button("a")
            self._pyboy.tick(30)
            return self.is_in_battle()

        # Nothing detected — keep going
        return self.is_in_battle()

    # Pokemon Red naming keyboard layout (upper case)
    # The keyboard is a 9-column × 5-row grid starting at tile (10, 2)
    _NAMING_GRID = {
        'A': (0, 0), 'B': (0, 1), 'C': (0, 2), 'D': (0, 3), 'E': (0, 4),
        'F': (0, 5), 'G': (0, 6), 'H': (0, 7), 'I': (0, 8),
        'J': (1, 0), 'K': (1, 1), 'L': (1, 2), 'M': (1, 3), 'N': (1, 4),
        'O': (1, 5), 'P': (1, 6), 'Q': (1, 7), 'R': (1, 8),
        'S': (2, 0), 'T': (2, 1), 'U': (2, 2), 'V': (2, 3), 'W': (2, 4),
        'X': (2, 5), 'Y': (2, 6), 'Z': (2, 7), ' ': (2, 8),
    }

    def _type_on_naming_keyboard(self, name):
        """Type a name on the Pokemon Red naming keyboard."""
        cur_row, cur_col = 0, 0  # cursor starts at A
        for ch in name:
            if ch not in self._NAMING_GRID:
                continue
            target_row, target_col = self._NAMING_GRID[ch]
            # Navigate vertically
            dy = target_row - cur_row
            btn = "down" if dy > 0 else "up"
            for _ in range(abs(dy)):
                self._pyboy.button(btn)
                self._pyboy.tick(5)
            # Navigate horizontally
            dx = target_col - cur_col
            btn = "right" if dx > 0 else "left"
            for _ in range(abs(dx)):
                self._pyboy.button(btn)
                self._pyboy.tick(5)
            # Select character
            self._pyboy.button("a")
            self._pyboy.tick(8)
            cur_row, cur_col = target_row, target_col

        # Navigate to END button and confirm
        # END is below the grid — press Start as shortcut to confirm
        self._pyboy.button("start")
        self._pyboy.tick(30)

    def _has_choice_or_naming(self):
        """Check if a choice menu or naming keyboard is on screen."""
        text = self._screen.read_text_box()
        if not text:
            return False
        lower = text.lower()
        if "lower case" in lower or "upper case" in lower:
            return True
        return bool(self._menu.read_choice_menu())


class ManualStrategy:
    """Console-based battle strategy — prompts the player for input."""

    def decide(self, player, enemy, is_wild, balls=None):
        actions = []
        for name, pp, max_pp in player['moves']:
            actions.append(f"{name} ({pp}/{max_pp} PP)")
        if balls:
            for ball_name, count, _ in balls:
                actions.append(f"🔴 {ball_name} ×{count}")
        if is_wild:
            actions.append("RUN")
        actions.append("CANCEL")

        choice = prompt_menu(actions)

        if choice == "CANCEL":
            return ("cancel", None)
        if "RUN" in choice and "🔴" not in choice:
            return ("run", None)
        if "🔴" in choice:
            # Find the bag index for this ball
            ball_label = choice.split("🔴 ")[1].split(" ×")[0]
            for ball_name, _, bag_idx in balls:
                if ball_name == ball_label:
                    return ("ball", bag_idx)
        move_name = choice.split(" (")[0]
        return ("move", move_name)
