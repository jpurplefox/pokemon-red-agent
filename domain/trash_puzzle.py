"""Vermilion Gym switch puzzle — what the player learned from the trash cans.

The game hides the 1st switch in one of 15 cans; the 2nd is in a can right
next to it (up, down, left or right in the 3x5 grid). Every other can just
has trash — including, before the 1st switch is found, the one that will
hold the 2nd — so "only trash" marks only rule cans out for the 1st switch
and are cleared once it's found. Checking a wrong can after that resets the
locks and moves the 1st switch. Leaving and re-entering the gym keeps an
open lock open but moves the switches, so earlier findings no longer hold.
"""

from __future__ import annotations

UNCHECKED = "unchecked"
TRASH = "trash"            # checked, nothing there
FIRST_SWITCH = "switch"    # the 1st switch (1st lock open)


class TrashCanPuzzle:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.status: dict[tuple[int, int], str] = {}
        self.first_lock_open = False
        self.solved = False
        self.resets = 0

    def reenter(self) -> None:
        """The player came back into the gym: open locks stay open, but the
        switches were hidden again."""
        self.status = {}

    def record(self, can: tuple[int, int], text: str) -> None:
        """Update from what checking the can at (row, col) said."""
        lower = text.lower()
        if "2nd" in lower and "open" in lower or "door opened" in lower:
            self.solved = True
            self.status[can] = FIRST_SWITCH
        elif "reset" in lower:
            resets = self.resets + 1
            self.reset()
            self.resets = resets
        elif "1st" in lower and "open" in lower or "switch" in lower:
            self.first_lock_open = True
            # earlier "only trash" said nothing about where the 2nd is
            self.status = {can: FIRST_SWITCH}
        elif "trash" in lower:
            self.status[can] = TRASH

    def can_status(self, can: tuple[int, int]) -> str:
        return self.status.get(can, UNCHECKED)
