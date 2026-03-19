"""Battle system — orchestrates the combat loop (SRP).

Delegates state reading to BattleStateReader and menu navigation to
BattleMenuDriver. This class handles flow control only: intro processing,
turn sequencing, switch handling, and strategy dispatch.
Dependencies injected via constructor (DIP).
"""

from data.constants import ADDR_PLAYER_MON_NUMBER
from adapters.display.console import prompt_menu, _input_fn
from adapters.state.battle_state_reader import BattleStateReader
from adapters.input.battle_menu_driver import BattleMenuDriver


class BattleHandler:
    def __init__(self, pyboy, screen, menu, dialogue, strategy=None,
                 naming_ai=None, bag_reader=None):
        self._pyboy = pyboy
        self._screen = screen
        self._menu = menu
        self._dialogue = dialogue
        self._state = BattleStateReader(pyboy)
        self._driver = BattleMenuDriver(pyboy, screen)
        self._strategy = strategy or ManualStrategy()
        self._naming_ai = naming_ai
        self._bag = bag_reader
        self._last_was_wild = True
        self._enemy_name = "unknown"
        self._trainer_name = None
        self._last_battle_summary = None

    # ------------------------------------------------------------------
    # State detection
    # ------------------------------------------------------------------

    def is_in_battle(self):
        return self._state.is_in_battle()

    def reset_move_cursor(self):
        self._driver.reset_move_cursor()

    def is_wild(self):
        return self._state.is_wild()

    def is_trainer(self):
        return self._state.is_trainer()

    def read_party(self):
        return self._state.read_party()

    def notify_battle_end(self):
        """Notify the strategy that the battle ended so it can recap."""
        # Determine result from last turn context
        result = "unknown"
        history = self._strategy.get_history()
        if history:
            last_text = history[-1].get("text", "").lower()
            if "got" in last_text and "for winning" in last_text:
                result = "victory"
            elif "fainted" in last_text:
                if "enemy" in last_text:
                    result = "victory"
                else:
                    result = "defeat"
            elif "got away" in last_text or "ran" in last_text:
                result = "fled"
            elif "gotcha" in last_text or "was caught" in last_text:
                result = "caught"

        is_wild = self._last_was_wild
        enemy_pokemon = self._enemy_name
        trainer_name = self._trainer_name
        battle_type = "Wild" if is_wild else "Trainer"
        enemy_label = trainer_name if trainer_name else enemy_pokemon
        self._last_battle_summary = {
            "type": battle_type,
            "enemy": enemy_label,
            "result": result,
        }

        self._strategy.on_battle_end(is_wild, result)

    # ------------------------------------------------------------------
    # Battle intro
    # ------------------------------------------------------------------

    def process_intro(self):
        """Advance through battle intro until the battle menu appears.

        Handles "Wild X appeared!", "Go! Y!", and any pre-battle dialogue.
        Prints all dialogue text, then returns when ready for player input.
        """
        full = self._dialogue.advance_until(
            lambda d, u: self._driver.has_battle_menu()
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
        active_idx = self._pyboy.memory[ADDR_PLAYER_MON_NUMBER]
        self._strategy.set_team(self._state.read_party(), active_idx)
        self._last_was_wild = self.is_wild()
        enemy = self._state.read_enemy()
        self._enemy_name = enemy.name
        # Extract trainer name from intro text (e.g. "FOLAGOR wants to fight!")
        self._trainer_name = None
        if not self._last_was_wild and full:
            for part in full.split("!"):
                part = part.strip()
                if "wants to fight" in part:
                    self._trainer_name = part.replace("wants to fight", "").strip()
                    break
        player = self._state.read_player()
        enemy = self._state.read_enemy()
        balls = self.get_balls() if self._last_was_wild else []
        self._strategy.on_battle_start(player, enemy, self._last_was_wild, balls)

    # ------------------------------------------------------------------
    # Battle summary
    # ------------------------------------------------------------------

    def print_summary(self):
        """Print the current battle state: both pokemon and available moves."""
        player = self._state.read_player()
        enemy = self._state.read_enemy()

        battle_type = "Wild" if self.is_wild() else "Trainer"
        print(f"\n{'=' * 40}")
        print(f"  {battle_type} Battle")
        print(f"{'=' * 40}")

        # Enemy pokemon
        e_status = f" [{enemy.status}]" if enemy.status else ""
        print(f"  Enemy: {enemy.name} Lv{enemy.level}"
              f"  HP: {enemy.hp}/{enemy.max_hp}{e_status}")

        # Player pokemon
        p_status = f" [{player.status}]" if player.status else ""
        print(f"  Your:  {player.name} Lv{player.level}"
              f"  HP: {player.hp}/{player.max_hp}{p_status}")

        # Player moves
        print(f"{'-' * 40}")
        print("  Moves:")
        for i, m in enumerate(player.moves, 1):
            print(f"    {i}. {m.name:<14} {m.pp}/{m.max_pp} PP")

        # Show balls in wild battles
        if self.is_wild():
            balls = self.get_balls()
            if balls:
                print("  Bag:")
                for ball_name, count, _ in balls:
                    print(f"    🔴 {ball_name} ×{count}")

        # Show party
        party = self._state.read_party()
        active_idx = self._pyboy.memory[ADDR_PLAYER_MON_NUMBER]
        if len(party) > 1:
            print("  Party:")
            for i, mon in enumerate(party):
                is_active = (i == active_idx)
                flag = " ⚔️" if is_active else ""
                fainted = " 💀" if mon.hp <= 0 else ""
                label = mon.nickname
                if mon.nickname != mon.name:
                    label = f"{mon.name} ({mon.nickname})"
                # Show battle HP for active, party HP for others
                hp = player.hp if is_active else mon.hp
                max_hp = player.max_hp if is_active else mon.max_hp
                print(f"    {label} Lv{mon.level}"
                      f"  {hp}/{max_hp} HP{flag}{fainted}")
        print(f"{'=' * 40}")

    # ------------------------------------------------------------------
    # Bag / Poké Balls
    # ------------------------------------------------------------------

    def get_balls(self):
        """Return list of (ball_name, count, bag_index) for Poké Balls."""
        if self._bag:
            return self._bag.get_balls()
        # Fallback for when no BagReader is injected
        from bag_reader import BagReader
        return BagReader(self._pyboy).get_balls()

    def _record_turn(self, text):
        """Pass turn text and current HP to the strategy for history tracking."""
        player = self._state.read_player()
        enemy = self._state.read_enemy()
        self._strategy.add_turn(
            text,
            player.hp, player.max_hp,
            enemy.hp, enemy.max_hp,
        )

    # ------------------------------------------------------------------
    # Battle actions
    # ------------------------------------------------------------------

    def prompt_action(self):
        """Decide and execute a battle action using the injected strategy."""
        player = self._state.read_player()
        enemy = self._state.read_enemy()
        balls = self.get_balls() if self.is_wild() else []
        active_idx = self._pyboy.memory[ADDR_PLAYER_MON_NUMBER]

        # Refresh party data so strategy has current info
        self._strategy.set_team(self._state.read_party(), active_idx)

        action_type, detail = self._strategy.decide(
            player, enemy, self.is_wild(), balls
        )

        if action_type == "cancel":
            self._pyboy.button("b")
            self._pyboy.tick(10)
            return
        elif action_type == "run":
            self._driver.select_battle_option("RUN")
        elif action_type == "ball":
            self._driver.use_ball(detail)
        elif action_type == "switch":
            self._driver.switch_pokemon(detail)
        else:
            move_idx = next(
                (i for i, m in enumerate(player.moves)
                 if m.name == detail),
                0,
            )
            self._driver.select_battle_option("FIGHT")
            self._driver.wait_for_move_menu(player.moves)
            self._driver.select_move(move_idx)

    def _handle_fainted_switch(self):
        """Handle switching after a party pokemon fainted.

        For wild battles: show party + RUN option.
        For trainer battles: show party directly (must choose).
        Auto-selects YES from the "Use next POKéMON?" menu, then
        navigates the party screen to send out the chosen pokemon.

        Returns True to keep processing, False if battle ended/fled.
        """
        from constants import ADDR_CURRENT_MENU

        party = self._state.read_party()
        player = self._state.read_player()
        active_idx = self._pyboy.memory[ADDR_PLAYER_MON_NUMBER]

        # Build options: alive non-active party members
        options = []
        indices = []
        for i, mon in enumerate(party):
            if i == active_idx:
                continue
            if mon.hp <= 0:
                continue
            label = mon.nickname
            if mon.nickname != mon.name:
                label = f"{mon.name} ({mon.nickname})"
            options.append(
                f"{label} Lv{mon.level}"
                f"  {mon.hp}/{mon.max_hp} HP"
            )
            indices.append(i)

        if not options:
            # No alive pokemon left — select NO to end
            self._pyboy.button("down")
            self._pyboy.tick(10)
            self._pyboy.button("a")
            self._pyboy.tick(30)
            return self.is_in_battle()

        # Ask strategy or player which pokemon to send
        if self.is_wild():
            options.append("RUN")

        enemy = self._state.read_enemy()
        choice_idx = self._strategy.choose_switch_in(
            party, indices, self.is_wild(), enemy
        )
        if choice_idx is None:
            print("\n--- Send out which POKéMON? ---")
            choice = prompt_menu(options)
            if choice == "RUN":
                choice_idx = -1  # signal to flee
            else:
                choice_idx = indices[options.index(choice)]

        if choice_idx == -1:
            # Run: select NO from YES/NO menu
            self._pyboy.button("down")
            self._pyboy.tick(10)
            self._pyboy.button("a")
            self._pyboy.tick(30)
            return self.is_in_battle()

        # In wild battles there's a YES/NO menu ("Use next POKéMON?")
        # In trainer battles the party screen opens directly after faint
        if self.is_wild():
            for _ in range(10):
                self._pyboy.button("up")
                self._pyboy.tick(5)
            self._pyboy.button("a")
            self._pyboy.tick(40)
        else:
            # Trainer: party screen is already open, just wait for it
            self._pyboy.tick(40)

        # Navigate the party select screen to the chosen pokemon
        current = self._pyboy.memory[ADDR_CURRENT_MENU]
        diff = choice_idx - current
        if diff > 0:
            for _ in range(diff):
                self._pyboy.button("down")
                self._pyboy.tick(10)
        elif diff < 0:
            for _ in range(-diff):
                self._pyboy.button("up")
                self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(30)

        # Game resets move cursor to 0 when a new pokemon enters battle
        self._last_move_idx = 0

        return self.is_in_battle()

    def _handle_trainer_switch_offer(self):
        """Handle the 'Will X change POKéMON?' YES/NO prompt.

        Appears after defeating a trainer's pokemon before they send
        the next one.  Asks the strategy (AI or manual) whether to
        switch, then selects YES/NO accordingly.

        Returns True to keep processing.
        """
        from constants import ADDR_CURRENT_MENU

        party = self._state.read_party()
        active_idx = self._pyboy.memory[ADDR_PLAYER_MON_NUMBER]

        # Build switchable list
        indices = []
        options = []
        for i, mon in enumerate(party):
            if i == active_idx:
                continue
            if mon.hp <= 0:
                continue
            label = mon.nickname
            if mon.nickname != mon.name:
                label = f"{mon.name} ({mon.nickname})"
            options.append(
                f"{label} Lv{mon.level}"
                f"  {mon.hp}/{mon.max_hp} HP"
            )
            indices.append(i)

        choice_idx = None

        if not indices:
            # No one to switch to — select NO
            pass
        else:
            choice_idx = self._strategy.choose_switch_offer(
                party, active_idx, indices
            )
            if choice_idx is None:
                # Manual: ask the player
                print("\n--- Switch POKéMON before next opponent? ---")
                options.append("NO")
                choice = prompt_menu(options)
                if choice != "NO":
                    choice_idx = indices[options.index(choice)]

        if choice_idx is None:
            # Select NO
            self._pyboy.button("down")
            self._pyboy.tick(10)
            self._pyboy.button("a")
            self._pyboy.tick(30)
        else:
            # Select YES
            for _ in range(10):
                self._pyboy.button("up")
                self._pyboy.tick(5)
            self._pyboy.button("a")
            self._pyboy.tick(40)

            # Navigate party screen to chosen pokemon
            current = self._pyboy.memory[ADDR_CURRENT_MENU]
            diff = choice_idx - current
            if diff > 0:
                for _ in range(diff):
                    self._pyboy.button("down")
                    self._pyboy.tick(10)
            elif diff < 0:
                for _ in range(-diff):
                    self._pyboy.button("up")
                    self._pyboy.tick(10)
            self._pyboy.button("a")
            self._pyboy.tick(30)

            self._last_move_idx = 0

        return True

    def process_turn(self):
        """Advance through turn messages until the battle menu reappears,
        the battle ends, or a choice/naming event appears.

        Handles mid-battle events inline (e.g. nickname prompt after catch).
        Returns True if the battle continues, False if ended.
        """
        turn_texts = []
        while True:
            full = self._dialogue.advance_until(
                lambda d, u: (self._driver.has_battle_menu()
                              or not self.is_in_battle()
                              or self._has_choice_or_naming())
            )
            if full:
                print(f"\n{full}")
                turn_texts.append(full)

            if self._driver.has_battle_menu() and self.is_in_battle():
                self._record_turn(" ".join(turn_texts))
                return True
            if not self.is_in_battle():
                self._record_turn(" ".join(turn_texts))
                return False

            # Handle mid-battle events (choice menu or naming keyboard)
            turn_context = " ".join(turn_texts)
            if not self._handle_mid_battle_event(turn_context):
                self._record_turn(turn_context)
                return False

    def _handle_mid_battle_event(self, turn_context=""):
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
            caught_species = self._state.read_enemy_species()

            if self._naming_ai:
                # Read actual party with real nicknames from WRAM
                # Exclude last entry — it's the Pokemon we just caught
                party = self._state.read_party()[:-1]
                team_context = [
                    (m.name, m.nickname) for m in party
                ]
                name = self._naming_ai.suggest_name(
                    caught_species, team_context
                )
            else:
                name = _input_fn("Enter nickname (empty to skip): ").strip()

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
                    self._driver.type_name(name.upper()[:10])
            elif is_naming_keyboard:
                if not name:
                    self._pyboy.button("b")
                    self._pyboy.tick(60)
                else:
                    self._driver.type_name(name.upper()[:10])
            return not self.is_in_battle()

        # Detect fainted pokemon
        ctx = turn_context.lower()
        if "fainted" in ctx and "is about to use" not in ctx:
            # Our pokemon fainted — need to send replacement
            return self._handle_fainted_switch()
        if "is about to use" in ctx:
            # Enemy pokemon fainted, trainer sending next — offer switch
            return self._handle_trainer_switch_offer()

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

    def __init__(self):
        self._party = []
        self._active_idx = None
        self._history = []

    def set_team(self, party, active_idx=None):
        self._party = party
        self._active_idx = active_idx

    def on_battle_start(self, player, enemy, is_wild, balls=None):
        pass

    def on_battle_end(self, is_wild, result="unknown"):
        pass

    def add_turn(self, text, player_hp, player_max_hp, enemy_hp, enemy_max_hp):
        pass

    def get_history(self):
        return self._history

    def choose_switch_in(self, party, alive_indices, is_wild, enemy=None):
        return None

    def choose_switch_offer(self, party, active_idx, alive_indices):
        return None

    def decide(self, player, enemy, is_wild, balls=None):
        actions = []
        for m in player.moves:
            actions.append(f"{m.name} ({m.pp}/{m.max_pp} PP)")
        if balls:
            for ball_name, count, _ in balls:
                actions.append(f"🔴 {ball_name} ×{count}")
        # Show switchable party members (alive, not currently active)
        for i, mon in enumerate(self._party):
            if i == self._active_idx:
                continue
            if mon.hp <= 0:
                continue  # skip fainted
            label = mon.nickname
            if mon.nickname != mon.name:
                label = f"{mon.name} ({mon.nickname})"
            actions.append(
                f"🔄 {label} Lv{mon.level}"
                f" ({mon.hp}/{mon.max_hp} HP)"
            )
        if is_wild:
            actions.append("RUN")
        actions.append("CANCEL")

        choice = prompt_menu(actions)

        if choice == "CANCEL":
            return ("cancel", None)
        if "RUN" in choice and "🔴" not in choice and "🔄" not in choice:
            return ("run", None)
        if "🔴" in choice:
            ball_label = choice.split("🔴 ")[1].split(" ×")[0]
            for ball_name, _, bag_idx in balls:
                if ball_name == ball_label:
                    return ("ball", bag_idx)
        if "🔄" in choice:
            # Find party index — match the full label before " Lv"
            label = choice.split("🔄 ")[1].split(" Lv")[0]
            for i, mon in enumerate(self._party):
                nick = mon.nickname
                full = (f"{mon.name} ({nick})"
                        if nick != mon.name else nick)
                if full == label:
                    return ("switch", i)
        move_name = choice.split(" (")[0]
        return ("move", move_name)
