"""Poké Mart shopping handler (SRP).

Manages the in-game mart interface: reading inventory, displaying items,
auto/manual purchase loops, and navigating game menus to buy items.
"""

from data.constants import (
    ADDR_MART_NUM_ITEMS, ADDR_MART_ITEMS, ITEM_CATALOGUE,
)
from adapters.display.console import _input_fn


class MartHandler:
    """Handles all Poké Mart shopping logic."""

    def __init__(self, pyboy, screen, bag_reader):
        self._pyboy = pyboy
        self._screen = screen
        self._bag = bag_reader
        self.auto_buy_fn = None  # callback(items, money, pokeballs) → [(idx, qty)]

    def handle(self, options):
        """Custom shop interface: show items, pick, buy, repeat.

        Called when a BUY/SELL menu is detected. Reads the mart inventory,
        lets the user or AI buy items, then exits the mart.
        """
        items = self._get_items()
        if not items:
            return False  # signal caller to handle normally

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
            self._print_inventory(items, money)
            purchases = self.auto_buy_fn(items, money, self._count_pokeballs())
            for idx, qty in purchases:
                if 0 <= idx < len(items) and qty > 0:
                    item = items[idx]
                    self._buy_item_in_game(idx, qty, len(items))
                    print(f"  ✓ Bought {qty}x {item['name']} for ¥{item['price'] * qty:,}")
        else:
            self._manual_buy_loop(items)

        # Exit item list: first B dismisses any dialogue, second B exits list
        self._pyboy.button("b")
        self._pyboy.tick(60)
        self._pyboy.button("b")
        self._pyboy.tick(60)
        return True

    # ------------------------------------------------------------------
    # Data reading
    # ------------------------------------------------------------------

    def _get_items(self):
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

    def _read_money(self):
        return self._bag.read_money()

    def _count_pokeballs(self):
        return self._bag.count_pokeballs()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _print_inventory(self, items, money):
        """Print the mart's item list with prices and affordability."""
        print(f"\n  💰 Your money: ¥{money:,}")
        print("  ┌─────────────────────────────────────┐")
        for i, item in enumerate(items):
            max_qty = money // item["price"] if item["price"] > 0 else 0
            qty_str = f"(max {max_qty})" if max_qty > 0 else "(can't afford)"
            print(f"  │ {i+1:>2}. {item['name']:<16} ¥{item['price']:>6,}  {qty_str:<15}│")
        print(f"  │  0. Leave shop                       │")
        print("  └─────────────────────────────────────┘")

    # ------------------------------------------------------------------
    # Purchase execution
    # ------------------------------------------------------------------

    def _manual_buy_loop(self, items):
        """Interactive loop for manual item purchases."""
        while True:
            money = self._read_money()
            self._print_inventory(items, money)

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

    def _buy_item_in_game(self, item_index, quantity, total_items):
        """Navigate the game's mart buy menu to purchase an item."""
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
