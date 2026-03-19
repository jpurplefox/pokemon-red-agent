"""Centralized bag and money reading from WRAM (DRY).

Consolidates pokeball counting and money reading that was
previously duplicated across game.py, event_processor.py, and battle.py.
"""

from data.constants import (
    ADDR_NUM_BAG_ITEMS, ADDR_BAG_ITEMS, BALL_ITEMS,
    ADDR_PLAYER_MONEY,
)


class BagReader:
    """Read-only accessor for the player's bag and money."""

    def __init__(self, pyboy):
        self._pyboy = pyboy

    def count_pokeballs(self) -> int:
        """Return total count of all Poké Ball types in the bag."""
        mem = self._pyboy.memory
        total = 0
        for i in range(mem[ADDR_NUM_BAG_ITEMS]):
            item_id = mem[ADDR_BAG_ITEMS + i * 2]
            count = mem[ADDR_BAG_ITEMS + i * 2 + 1]
            if item_id in BALL_ITEMS:
                total += count
        return total

    def get_balls(self) -> list:
        """Return [(ball_name, count, bag_index)] for each ball type."""
        mem = self._pyboy.memory
        balls = []
        for i in range(mem[ADDR_NUM_BAG_ITEMS]):
            item_id = mem[ADDR_BAG_ITEMS + i * 2]
            count = mem[ADDR_BAG_ITEMS + i * 2 + 1]
            if item_id in BALL_ITEMS:
                balls.append((BALL_ITEMS[item_id], count, i))
        return balls

    def read_money(self) -> int:
        """Read player money from BCD-encoded 3 bytes."""
        mem = self._pyboy.memory
        b0 = mem[ADDR_PLAYER_MONEY]
        b1 = mem[ADDR_PLAYER_MONEY + 1]
        b2 = mem[ADDR_PLAYER_MONEY + 2]
        return (
            (b0 >> 4) * 100000 + (b0 & 0xF) * 10000
            + (b1 >> 4) * 1000 + (b1 & 0xF) * 100
            + (b2 >> 4) * 10 + (b2 & 0xF)
        )
