"""Jev decisions are sampled from the returned probabilities."""

import random
import unittest
from collections import Counter
from types import SimpleNamespace

from agents.jev_ai import _sample_choice


class _Log:
    def log_think(self, msg):
        pass


def _answer(probabilities):
    top = max(probabilities, key=probabilities.get)
    return SimpleNamespace(choice=top, confidence=0.5, probabilities=probabilities)


class SampleChoiceTests(unittest.TestCase):
    def test_follows_probabilities(self):
        random.seed(0)
        answer = _answer({"go_1": 0.7, "go_2": 0.2, "interact_1": 0.1})
        counts = Counter(_sample_choice(_Log(), answer) for _ in range(10_000))
        self.assertAlmostEqual(counts["go_1"] / 10_000, 0.7, delta=0.02)
        self.assertAlmostEqual(counts["go_2"] / 10_000, 0.2, delta=0.02)
        self.assertAlmostEqual(counts["interact_1"] / 10_000, 0.1, delta=0.02)

    def test_certain_option_always_wins(self):
        answer = _answer({"catch": 1.0, "defeat": 0.0})
        self.assertEqual({_sample_choice(_Log(), answer) for _ in range(500)}, {"catch"})

    def test_roll_maps_to_cumulative_band(self):
        answer = _answer({"keep": 0.6, "switch_2": 0.4})
        for roll, expected in ((0.0, "keep"), (0.59, "keep"), (0.61, "switch_2"), (0.99, "switch_2")):
            with self.subTest(roll=roll):
                original = random.random
                random.random = lambda: roll
                try:
                    self.assertEqual(_sample_choice(_Log(), answer), expected)
                finally:
                    random.random = original


if __name__ == "__main__":
    unittest.main()
