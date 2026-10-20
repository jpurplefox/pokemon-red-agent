"""HMs and CUT: tree detection, what trees hide, HM options, learner choice."""

import unittest
from types import SimpleNamespace

from adapters.state.overworld import OverworldScanner
from agents.move_ai import MoveAI
from data.constants import TILESET_GYM, TILESET_OVERWORLD
from domain.maps import (
    Direction, Interactable, Map, MapConnection, PassableTile, WalkabilityGrid,
)
from domain.models import PartyMember
from domain.pathfinder import reachable_tiles
from domain.world import World
from orchestration.overworld_controller import OverworldAIController

TREE = 0x3D


def _grid(rows):
    return WalkabilityGrid(tiles=[[PassableTile(Direction.ALL if ch == "." else Direction.NONE)
                                   for ch in row] for row in rows])


class CutTreeScanTests(unittest.TestCase):
    def test_finds_the_tileset_tree_tile(self):
        tiles = [[0x2C, TREE], [0x50, 0x2C]]
        self.assertEqual([(p["ty"], p["tx"]) for p in
                          OverworldScanner._find_cut_trees_raw(tiles, TILESET_OVERWORLD)],
                         [(0, 1)])
        self.assertEqual([(p["ty"], p["tx"]) for p in
                          OverworldScanner._find_cut_trees_raw(tiles, TILESET_GYM)],
                         [(1, 0)])
        self.assertEqual(OverworldScanner._find_cut_trees_raw(tiles, 17), [])


class OpenTileTests(unittest.TestCase):
    def test_open_tile_lets_the_flood_through(self):
        grid = _grid(["..#.."])
        self.assertNotIn((0, 4), reachable_tiles(grid, (0, 0)))
        self.assertIn((0, 4), reachable_tiles(grid, (0, 0), open_tiles={(0, 2)}))


class WorldTreeTests(unittest.TestCase):
    def test_tree_marks_what_it_hides(self):
        world = World()
        world.visit(Map(name="Route 11", grid=_grid(["..."]), connected_maps=[
            MapConnection(map=Map(name="Vermilion City"), position=(0, 0), kind="warp")]))
        world.visit(Map(name="Vermilion City", grid=_grid([".#."]),
                        interactables=[Interactable("Cuttable tree", (0, 1), "cut_tree")],
                        connected_maps=[
                            MapConnection(map=Map(name="Route 11"), position=(0, 0), kind="warp"),
                            MapConnection(map=Map(name="Vermilion Gym"), position=(0, 2), kind="warp")]))
        world.record_transition("Route 11", (0, 0), "Vermilion City", (0, 0), (0, 0))
        city = world.leads_to("Route 11", (0, 2), (0, 0))
        self.assertEqual(city["interactables"],
                         [{"name": "Cuttable tree", "blocks_way_to": ["Vermilion Gym"]}])
        self.assertEqual(city["exits"], [])


class _Bag:
    def __init__(self, items):
        self.items = items

    def get_item_ids(self):
        return self.items


class _Compat:
    def __init__(self, learners):
        self.learners = learners

    def can_learn(self, species_id, move):
        return (species_id, move) in self.learners


def _mon(name, species_id, moves):
    return PartyMember(name=name, nickname=name, level=20, hp=10, max_hp=10,
                       species_id=species_id, moves=tuple(moves))


class HMOptionsTests(unittest.TestCase):
    def _controller(self, bag, learners):
        c = OverworldAIController.__new__(OverworldAIController)
        c._bag = _Bag(bag)
        c._hm_compat = _Compat(learners)
        c._field_moves = object()
        c._move_ai = object()
        return c

    def test_offers_hm_with_its_learners(self):
        c = self._controller([0xC4], {(0x9A, "CUT")})
        options, notes = c._hm_options([_mon("VENUSAUR", 0x9A, ["TACKLE"]),
                                        _mon("PIDGEY", 0x24, ["GUST"])])
        self.assertEqual(options, [{"item": 0xC4, "hm": "HM01", "move": "CUT",
                                    "learners": ["VENUSAUR"]}])
        self.assertEqual(notes, [])

    def test_note_when_nobody_can_learn_it(self):
        c = self._controller([0xC7], set())
        options, notes = c._hm_options([_mon("PIDGEY", 0x24, ["GUST"])])
        self.assertEqual(options, [])
        self.assertEqual(notes, ["HM04 STRENGTH: no team member can learn it"])

    def test_not_offered_when_someone_knows_it(self):
        c = self._controller([0xC4], {(0x9A, "CUT")})
        options, notes = c._hm_options([_mon("VENUSAUR", 0x9A, ["CUT"])])
        self.assertEqual((options, notes), ([], []))


class _ScriptedLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        return SimpleNamespace(content=self.replies.pop(0))


class ChooseHMLearnerTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [(0, _mon("VENUSAUR", 0x9A, ["TACKLE"] * 4)),
                           (3, _mon("ODDISH", 0xB9, ["ABSORB"]))]

    def test_returns_the_party_slot(self):
        ai = MoveAI(_ScriptedLLM("THINK: free slot\nACTION: TEACH 2"))
        self.assertEqual(ai.choose_hm_learner("CUT", self.candidates), 3)

    def test_none_means_dont_teach(self):
        ai = MoveAI(_ScriptedLLM("ACTION: NONE"))
        self.assertIsNone(ai.choose_hm_learner("CUT", self.candidates))

    def test_retries_on_invalid_answer(self):
        ai = MoveAI(_ScriptedLLM("ACTION: TEACH 9", "ACTION: TEACH 1"))
        self.assertEqual(ai.choose_hm_learner("CUT", self.candidates), 0)


if __name__ == "__main__":
    unittest.main()
