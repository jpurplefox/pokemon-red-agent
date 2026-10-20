"""Vermilion Gym trash can puzzle tracking, with the game's own texts."""

import unittest

from adapters.state.overworld import OverworldScanner
from data.constants import VERMILION_GYM
from domain.trash_puzzle import FIRST_SWITCH, TRASH, UNCHECKED, TrashCanPuzzle

TRASH_TEXT = "Nope, there's only trash here."
FIRST = "Hey! There's a switch under the trash! Turn it on! The 1st electric lock opened!"
SECOND = "The 2nd electric lock opened! The motorized door opened!"
RESET = "Nope! There's only trash here. Hey! The electric locks were reset!"


class TrashCanPuzzleTests(unittest.TestCase):
    def setUp(self):
        self.p = TrashCanPuzzle()

    def test_trash_marks_until_the_first_switch_clears_them(self):
        self.p.record((1, 1), TRASH_TEXT)
        self.assertEqual(self.p.can_status((1, 1)), TRASH)
        self.p.record((3, 5), FIRST)
        self.assertTrue(self.p.first_lock_open)
        self.assertEqual(self.p.can_status((3, 5)), FIRST_SWITCH)
        self.assertEqual(self.p.can_status((1, 1)), UNCHECKED)

    def test_wrong_can_after_first_resets(self):
        self.p.record((3, 5), FIRST)
        self.p.record((3, 4), RESET)
        self.assertFalse(self.p.first_lock_open)
        self.assertEqual(self.p.status, {})
        self.assertEqual(self.p.resets, 1)

    def test_second_switch_solves(self):
        self.p.record((3, 5), FIRST)
        self.p.record((2, 5), SECOND)
        self.assertTrue(self.p.solved)

    def test_reentering_keeps_the_lock_but_forgets_where(self):
        self.p.record((3, 5), FIRST)
        self.p.reenter()
        self.assertTrue(self.p.first_lock_open)
        self.assertEqual(self.p.status, {})


class TrashCanScanTests(unittest.TestCase):
    def test_grid_ignores_the_same_tile_elsewhere(self):
        tiles = [[0x11] * 10 for _ in range(18)]
        for y in (7, 9, 11):
            for x in (1, 3, 5, 7, 9):
                tiles[y][x] = 0x1B
        tiles[1][6] = 0x1B  # same tile in the leader's area
        cans = OverworldScanner._find_trash_cans_raw(tiles, VERMILION_GYM)
        self.assertEqual(len(cans), 15)
        self.assertEqual({c["grid_pos"] for c in cans},
                         {(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4, 5)})
        self.assertEqual(OverworldScanner._find_trash_cans_raw(tiles, 0x5B), [])


if __name__ == "__main__":
    unittest.main()
