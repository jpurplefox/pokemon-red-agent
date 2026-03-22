"""Inline cutscene/event processing (SRP).

Ticks through events that interrupt gameplay — dialogue sequences,
YES/NO menus, naming keyboards — until the game state stabilises.
"""

from data.constants import (
    ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_MAX_MENU, ADDR_IS_IN_BATTLE,
    ADDR_MART_NUM_ITEMS, ADDR_MART_ITEMS,
    ITEM_CATALOGUE,
)
from dialogue import DialogueAdvancer
from adapters.display.console import prompt_menu, prompt_name, _input_fn


class EventProcessor:
    def __init__(self, pyboy, screen, menu, naming, name_menu_handler,
                 bag_reader=None):
        self._pyboy = pyboy
        self._screen = screen
        self._menu = menu
        self._naming = naming
        self._handle_name_menu = name_menu_handler
        self._dialogue = DialogueAdvancer(pyboy, screen)
        self._bag = bag_reader
        self.auto_accept = False
        self.auto_name_fn = None
        self.auto_buy_fn = None   # callback(items, money, pokeballs) → [(idx, qty)]
        self._exiting_mart = False

    def process(self):
        """Tick through a cutscene/event, handling dialogues and menus.

        Keeps ticking until the game state is fully stable: no dialogue,
        no menu activity, player position and map not changing.
        Returns when ~200 frames pass with no state change.

        Returns a list of all dialogue lines collected during the event.
        """
        mem = self._pyboy.memory
        idle = 0
        last_state = None
        last_text = None
        pending_lines = []
        all_dialogue = []

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
                    self._flush_dialogue(pending_lines, all_dialogue)
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
            self._flush_dialogue(pending_lines, all_dialogue)
            pending_lines = []
            last_text = None

            # Check for standalone menus (e.g. PC menu) that appear
            # without text box content — just a cursor + options
            choice_options = self._menu.read_choice_menu()
            if choice_options:
                self._handle_choice_menu(choice_options)
                idle = 0
                continue

            if state != last_state:
                last_state = state
                idle = 0
                continue

            idle += 1

        return all_dialogue

    def _handle_naming_keyboard(self):
        """Handle the in-game naming keyboard."""
        name = None
        if self.auto_accept and self.auto_name_fn:
            name = self.auto_name_fn()
        if name is None:
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
        # Exiting mart — dismiss any remaining menus (item list or BUY/SELL)
        if self._exiting_mart:
            self._pyboy.button("b")
            self._pyboy.tick(30)
            # Check if we fully exited (no more BUY in options = item list)
            if any("BUY" in opt for opt in options):
                # Back at BUY/SELL/QUIT — select QUIT (last option)
                self._exiting_mart = False
                quit_idx = len(options) - 1
                for _ in range(quit_idx):
                    self._pyboy.button("down")
                    self._pyboy.tick(10)
                self._pyboy.button("a")
                self._pyboy.tick(30)
            return

        # Intercept mart BUY/SELL menu with custom shop interface
        if any("BUY" in opt for opt in options):
            self._handle_mart_menu(options)
            return

        if self.auto_accept and "YES" in options:
            choice = "YES"
            print("  [AUTO] Selecting YES")
        elif self.auto_accept and "HEAL" in options:
            choice = "HEAL"
            print("  [AUTO] Selecting HEAL")
        elif self.auto_accept:
            # Check if it's a PC or similar menu — dismiss with B
            opts_text = " ".join(options).upper()
            if any(kw in opts_text for kw in ("LOG OFF", "WITHDRAW", "DEPOSIT",
                                               "BILL", "SOMEONE", "PROF.OAK")):
                print(f"  [AUTO] Closing menu: {options}")
                self._pyboy.button("b")
                self._pyboy.tick(30)
                return
            # Otherwise select first option (safer than B for dialogues)
            print(f"  [AUTO] Selecting first option: {options[0]}")
            choice = options[0]
        else:
            options_with_cancel = options + ["CANCEL"]
            choice = prompt_menu(options_with_cancel)
            if choice == "CANCEL":
                self._pyboy.button("b")
                self._pyboy.tick(30)
                return
        # Navigate: cursor starts at top (index 0), press down to target
        target_idx = options.index(choice)
        for _ in range(target_idx):
            self._pyboy.button("down")
            self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(30)

    def _read_money(self):
        """Read player money."""
        return self._bag.read_money()

    def _count_pokeballs(self):
        """Count total Poké Balls of all types in the bag."""
        return self._bag.count_pokeballs()

    def _get_mart_items(self):
        """Read the mart's item list with names and prices."""
        mem = self._pyboy.memory
        num = mem[ADDR_MART_NUM_ITEMS]
        if num == 0 or num > 10:
            return []
        items = []
        for i in range(num):
            item_id = mem[ADDR_MART_ITEMS + i]
            name, price = ITEM_CATALOGUE.get(item_id, (f"Item 0x{item_id:02X}", 0))
            items.append({"name": name, "price": price, "index": i})
        return items

    def _print_mart_inventory(self, items, money):
        """Print the mart's item list with prices and affordability."""
        print(f"\n  💰 Your money: ¥{money:,}")
        print("  ┌─────────────────────────────────────┐")
        for i, item in enumerate(items):
            max_qty = money // item["price"] if item["price"] > 0 else 0
            qty_str = f"(max {max_qty})" if max_qty > 0 else "(can't afford)"
            print(f"  │ {i+1:>2}. {item['name']:<16} ¥{item['price']:>6,}  {qty_str:<15}│")
        print(f"  │  0. Leave shop                       │")
        print("  └─────────────────────────────────────┘")

    def _handle_mart_menu(self, options):
        """Custom shop interface: show items, pick, buy, repeat."""
        items = self._get_mart_items()
        if not items:
            # Fallback to normal menu
            self._select_option(options, options[-1])
            return

        # Select BUY in the game menu first
        buy_idx = next(i for i, o in enumerate(options) if "BUY" in o)
        for _ in range(buy_idx):
            self._pyboy.button("down")
            self._pyboy.tick(10)
        self._pyboy.button("a")
        self._pyboy.tick(60)

        # Auto-buy or manual buy loop
        if self.auto_buy_fn:
            money = self._read_money()
            self._print_mart_inventory(items, money)
            purchases = self.auto_buy_fn(items, money, self._count_pokeballs())
            for idx, qty in purchases:
                if 0 <= idx < len(items) and qty > 0:
                    item = items[idx]
                    self._buy_item_in_game(idx, qty, len(items))
                    print(f"  ✓ Bought {qty}x {item['name']} for ¥{item['price'] * qty:,}")
        else:
            # Manual buy loop
            while True:
                money = self._read_money()
                self._print_mart_inventory(items, money)

                try:
                    choice = int(_input_fn("  Buy item #: "))
                except (ValueError, EOFError):
                    choice = -1

                if choice == 0 or choice < 0 or choice > len(items):
                    break

                item = items[choice - 1]
                if item["price"] <= 0 or money < item["price"]:
                    print("  Can't afford that!")
                    continue

                max_qty = money // item["price"]
                try:
                    qty = int(_input_fn(f"  Quantity (1-{max_qty}): "))
                except (ValueError, EOFError):
                    qty = 0

                if qty <= 0 or qty > max_qty or qty > 99:
                    print("  Cancelled.")
                    continue

                self._buy_item_in_game(choice - 1, qty, len(items))
                print(f"  ✓ Bought {qty}x {item['name']} for ¥{item['price'] * qty:,}")

        # Exit item list: first B dismisses any dialogue, second B exits list
        self._pyboy.button("b")
        self._pyboy.tick(60)
        self._pyboy.button("b")
        self._pyboy.tick(60)
        # Flag so next BUY/SELL detection auto-selects QUIT
        self._exiting_mart = True

    def _buy_item_in_game(self, item_index, quantity, total_items):
        """Navigate the game's mart buy menu to purchase an item.

        The buy list cursor starts at item 0. We navigate down to item_index,
        press A, set quantity, then confirm YES.
        """
        # Reset cursor to top
        for _ in range(total_items):
            self._pyboy.button("up")
            self._pyboy.tick(5)

        # Navigate to desired item
        for _ in range(item_index):
            self._pyboy.button("down")
            self._pyboy.tick(10)

        # Select item
        self._pyboy.button("a")
        self._pyboy.tick(30)

        # Quantity screen: starts at ×01, press up to increase
        for _ in range(quantity - 1):
            self._pyboy.button("up")
            self._pyboy.tick(5)

        # Confirm quantity
        self._pyboy.button("a")
        self._pyboy.tick(30)

        # YES/NO confirmation — YES is at top
        self._pyboy.button("a")
        self._pyboy.tick(60)

        # Process purchase dialogue ("Here you are! Thank you!")
        for _ in range(5):
            self._pyboy.tick(10)
            if self._screen.read_text_box():
                self._pyboy.button("a", delay=8)
                self._pyboy.tick(20)

    def _flush_dialogue(self, lines, all_dialogue=None):
        """Deduplicate and print accumulated dialogue lines."""
        if not lines:
            return
        line = DialogueAdvancer.deduplicate(lines)
        if line:
            print(f"\n{line}")
            if all_dialogue is not None:
                all_dialogue.append(line)
        lines.clear()
