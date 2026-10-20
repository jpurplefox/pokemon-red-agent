"""Domain grid movement rules: ledges, tile-pair collisions, door exits."""

import unittest

from adapters.state.overworld import OverworldScanner
from data.constants import TILESET_CAVERN, TILESET_OVERWORLD
from domain.maps import Direction, LedgeTile, MapConnection, Map
from domain.pathfinder import find_path_to_poi

GROUND = 0x2C   # ledge standing tile
LEDGE_DOWN = 0x37
LEDGE_LEFT = 0x27
WALL = 0x00

build = OverworldScanner._build_domain_grid


def _grid(tile_rows, walkable_tiles, tileset=TILESET_OVERWORLD):
    walkable = [[t in walkable_tiles for t in row] for row in tile_rows]
    return build(tile_rows, walkable, tileset)


class LedgeTests(unittest.TestCase):
    def setUp(self):
        # two columns so no tile is isolated (isolated tiles allow every move):
        # ground / ledge / ground on the left, ground / wall / ground on the right
        self.grid = _grid([[GROUND, GROUND], [LEDGE_DOWN, WALL], [GROUND, GROUND]],
                          {GROUND})

    def test_ledge_is_one_way(self):
        self.assertIsInstance(self.grid[1, 0], LedgeTile)
        self.assertTrue(self.grid.can_move((0, 0), Direction.SOUTH))
        self.assertTrue(self.grid.can_move((1, 0), Direction.SOUTH))   # landing
        self.assertFalse(self.grid.can_move((2, 0), Direction.NORTH))  # no climbing
        self.assertFalse(self.grid.can_move((1, 0), Direction.NORTH))

    def test_path_goes_down_the_ledge_but_not_back_up(self):
        from domain.pathfinder import reachable_tiles
        self.assertIn((2, 0), reachable_tiles(self.grid, (0, 0)))
        self.assertNotIn((0, 0), reachable_tiles(self.grid, (2, 0)))

    def test_ledge_needs_standing_tile_on_approach_side(self):
        grid = _grid([[WALL], [LEDGE_DOWN], [GROUND]], {GROUND})
        self.assertNotIsInstance(grid[1, 0], LedgeTile)
        self.assertFalse(grid.can_move((2, 0), Direction.NORTH))

    def test_side_ledge(self):
        grid = _grid([[GROUND, LEDGE_LEFT, GROUND]], {GROUND})
        # LEDGE_LEFT jumps west: approach from the east
        self.assertIsInstance(grid[0, 1], LedgeTile)
        self.assertTrue(grid.can_move((0, 2), Direction.WEST))
        self.assertFalse(grid.can_move((0, 0), Direction.EAST))

    def test_ledges_only_on_overworld_tileset(self):
        grid = _grid([[GROUND], [LEDGE_DOWN], [GROUND]], {GROUND},
                     tileset=TILESET_CAVERN)
        self.assertNotIsInstance(grid[1, 0], LedgeTile)


class TilePairTests(unittest.TestCase):
    def test_cave_elevation_blocks_both_ways(self):
        # 0x20 next to 0x05 is a blocked pair in caves
        grid = _grid([[0x20, 0x05, 0x05]], {0x20, 0x05}, tileset=TILESET_CAVERN)
        self.assertFalse(grid.can_move((0, 0), Direction.EAST))
        self.assertFalse(grid.can_move((0, 1), Direction.WEST))
        self.assertTrue(grid.can_move((0, 1), Direction.EAST))

    def test_same_pair_is_fine_outside_caves(self):
        grid = _grid([[0x20, 0x05]], {0x20, 0x05}, tileset=TILESET_OVERWORLD)
        self.assertTrue(grid.can_move((0, 0), Direction.EAST))


class WallTests(unittest.TestCase):
    def test_cannot_enter_or_leave_walls(self):
        grid = _grid([[GROUND, WALL, GROUND]], {GROUND})
        self.assertFalse(grid.can_move((0, 0), Direction.EAST))
        self.assertFalse(grid.can_move((0, 2), Direction.WEST))


class DoorExitTests(unittest.TestCase):
    def test_door_mat_exit_faces_the_edge(self):
        grid = _grid([[GROUND, GROUND]] * 4, {GROUND})
        bottom = MapConnection(map=Map(name="Pallet Town"), position=(3, 0), kind="exit")
        top = MapConnection(map=Map(name="Route 2"), position=(0, 1), kind="exit")
        self.assertEqual(find_path_to_poi(grid, (2, 0), bottom), (["down"], "down"))
        self.assertEqual(find_path_to_poi(grid, (1, 1), top), (["up"], "up"))

    def test_warps_have_no_face(self):
        grid = _grid([[GROUND, GROUND]], {GROUND})
        stairs = MapConnection(map=Map(name="Red's House 2F"), position=(0, 1), kind="warp")
        self.assertEqual(find_path_to_poi(grid, (0, 0), stairs), (["right"], None))


class EdgeCrossingTests(unittest.TestCase):
    """Which edge tiles let the player cross into the connected map."""

    crossable = staticmethod(OverworldScanner._crossable_tiles)

    def test_needs_a_walkable_tile_across(self):
        tile_ids = [[GROUND, GROUND, GROUND]]
        walkable = [[True, True, True]]
        outside = [(GROUND, True), (WALL, False), (GROUND, True)]
        self.assertEqual(self.crossable("down", tile_ids, walkable, outside, TILESET_OVERWORLD),
                         {(0, 0), (0, 2)})

    def test_ledge_across_only_in_its_jump_direction(self):
        tile_ids = [[GROUND], [GROUND]]
        walkable = [[True], [True]]
        # crossing east (right edge): a left-jumping ledge blocks, a
        # right-jumping one is a jump
        self.assertEqual(self.crossable("right", tile_ids, walkable,
                                        [(LEDGE_LEFT, False), (0x0D, False)],
                                        TILESET_OVERWORLD),
                         {(1, 0)})

    def test_ledge_on_the_edge_jumps_across(self):
        # ground above a down-ledge that sits on the bottom edge
        tile_ids = [[GROUND, GROUND], [LEDGE_DOWN, LEDGE_DOWN]]
        walkable = [[True, True], [False, False]]
        outside = [(GROUND, True), (WALL, False)]
        self.assertEqual(self.crossable("down", tile_ids, walkable, outside, TILESET_OVERWORLD),
                         {(1, 0)})

    def test_blocked_inside_tile_or_pair(self):
        tile_ids = [[0x20, WALL]]
        walkable = [[True, False]]
        outside = [(0x05, True), (GROUND, True)]
        self.assertEqual(self.crossable("down", tile_ids, walkable, outside, TILESET_CAVERN),
                         set())

    def test_pathfinder_only_targets_crossable_tiles(self):
        grid = _grid([[GROUND, GROUND, GROUND]] * 2, {GROUND})
        conn = MapConnection(map=Map(name="Route 3"), position=(1, 1), kind="connection",
                             conn_dir="down", crossable=frozenset({(1, 2)}))
        path, face = find_path_to_poi(grid, (0, 0), conn)
        self.assertEqual(face, "down")
        self.assertEqual(len(path), 3)  # to (1, 2), not the closer (1, 0)


if __name__ == "__main__":
    unittest.main()
