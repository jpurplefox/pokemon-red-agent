"""World memory: entrances, reachability per arrival, nesting, persistence.

The fixture is a tiny Route 4: the Pokecenter door and Route 3 are in the
west half; Mt. Moon B1F lands in the east half, whose ledges drop to a
south strip with the way to Cerulean. From the west you can't reach
Cerulean; from B1F you can't reach the west.
"""

import unittest

from domain.maps import (
    Direction, Interactable, LedgeTile, Map, MapConnection, PassableTile,
    WalkabilityGrid,
)
from domain.world import World

ROUTE_4_ROWS = [
    "...#...",
    "...#...",
    "####vvv",
    ".......",
]


def _grid(rows):
    tiles = []
    for row in rows:
        out = []
        for ch in row:
            if ch == ".":
                out.append(PassableTile(passable=Direction.ALL))
            elif ch == "v":
                out.append(LedgeTile(jump_direction=Direction.SOUTH))
            else:
                out.append(PassableTile(passable=Direction.NONE))
        tiles.append(out)
    return WalkabilityGrid(tiles=tiles)


def _map(name, rows, interactables=(), exits=()):
    return Map(
        name=name,
        grid=_grid(rows),
        interactables=[Interactable(n, pos, "sprite") for n, pos in interactables],
        connected_maps=[MapConnection(map=Map(name=label), position=pos, kind="warp")
                        for label, pos in exits],
    )


ROUTE_4 = _map(
    "Route 4", ROUTE_4_ROWS,
    interactables=[("Woman (west)", (1, 1)), ("Woman (east)", (1, 5))],
    exits=[("Mt. Moon Pokecenter", (0, 0)), ("Route 3", (1, 0)),
           ("Mt. Moon B1F", (0, 6)), ("Cerulean City", (3, 6))],
)
POKECENTER = _map("Mt. Moon Pokecenter", ["...", "..."],
                  interactables=[("Nurse", (0, 1))],
                  exits=[("Route 4", (1, 0))])
B1F = _map("Mt. Moon B1F", ["...", "..."],
           exits=[("Route 4", (1, 2)), ("Mt. Moon 1F", (0, 0))])
ROUTE_3 = _map("Route 3", ["....", "...."], interactables=[("Lass", (0, 2))],
               exits=[("Route 4", (0, 3)), ("Pewter City", (0, 0))])


class MemoryStore:
    def __init__(self):
        self.data = []

    def load(self):
        return self.data

    def save(self, data):
        import copy
        self.data = copy.deepcopy(data)


def _exits(node):
    return {e["exit"]: e for e in node["exits"]}


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.world = World()
        for m in (ROUTE_4, POKECENTER, B1F, ROUTE_3):
            self.world.visit(m)

    def test_untaken_exit_is_unvisited_and_not_expanded(self):
        self.assertFalse(self.world.exit_taken("Mt. Moon Pokecenter", (1, 0)))
        self.assertIsNone(self.world.leads_to("Mt. Moon Pokecenter", (0, 0), (1, 0)))

    def test_only_what_is_reachable_from_the_arrival(self):
        self.world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        node = self.world.leads_to("Mt. Moon Pokecenter", (0, 0), (1, 0))
        self.assertEqual(node["map"], "Route 4")
        self.assertEqual([i["name"] for i in node["interactables"]], ["Woman (west)"])
        # the door back into the Pokecenter is omitted; Cerulean is unreachable
        self.assertEqual(set(_exits(node)), {"Route 3"})

    def test_same_map_through_another_exit_shows_another_part(self):
        self.world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        self.world.record_transition("Mt. Moon B1F", (1, 2), "Route 4", (0, 6), (1, 2))
        node = self.world.leads_to("Mt. Moon B1F", (0, 0), (1, 2))
        self.assertEqual([i["name"] for i in node["interactables"]], ["Woman (east)"])
        # down the ledges to Cerulean, but never back west
        self.assertEqual(set(_exits(node)), {"Cerulean City"})

    def test_exit_unvisited_even_if_destination_map_is_known(self):
        self.world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        self.assertIsNone(self.world.leads_to("Mt. Moon B1F", (0, 0), (1, 2)))

    def test_exit_arrived_through_counts_as_visited(self):
        self.world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        self.assertTrue(self.world.exit_taken("Route 4", (0, 0)))
        node = self.world.leads_to("Route 4", (0, 1), (0, 0))
        self.assertEqual(node["map"], "Mt. Moon Pokecenter")
        self.assertEqual([i["name"] for i in node["interactables"]], ["Nurse"])

    def test_arrival_before_first_scan_applies_on_visit(self):
        world = World()
        world.visit(POKECENTER)
        world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        self.assertFalse(world.exit_taken("Route 4", (0, 0)))  # not scanned yet
        world.visit(ROUTE_4)
        self.assertTrue(world.exit_taken("Route 4", (0, 0)))
        self.assertFalse(world.exit_taken("Route 4", (1, 0)))

    def test_map_edge_arrival_marks_the_edge_connection(self):
        world = World()
        a = Map(name="Viridian City", grid=_grid(["...", "..."]), connected_maps=[
            MapConnection(map=Map(name="Route 1"), position=(1, 1), kind="connection", conn_dir="down")])
        b = Map(name="Route 1", grid=_grid(["...", "..."]), connected_maps=[
            MapConnection(map=Map(name="Viridian City"), position=(0, 1), kind="connection", conn_dir="up"),
            MapConnection(map=Map(name="Route 1 House"), position=(1, 0), kind="warp")])
        world.visit(a)
        world.record_transition("Viridian City", (1, 1), "Route 1", (0, 2), (1, 2),
                                via_connection=True)
        world.visit(b)
        self.assertTrue(world.exit_taken("Route 1", (0, 1)))
        self.assertFalse(world.exit_taken("Route 1", (1, 0)))
        self.assertEqual(world.leads_to("Route 1", (0, 2), (0, 1))["map"], "Viridian City")

    def _chain_to_pewter(self):
        self.world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        self.world.record_transition("Route 4", (1, 0), "Route 3", (0, 3), (1, 0))
        self.world.record_transition("Route 3", (0, 0), "Pewter City", (0, 0), (0, 0))

    def test_nesting_stops_at_the_level_limit(self):
        self._chain_to_pewter()
        node = self.world.leads_to("Mt. Moon Pokecenter", (0, 0), (1, 0), levels=3)
        route_3 = _exits(node)["Route 3"]
        self.assertTrue(route_3["visited"])
        self.assertEqual(route_3["leads_to"]["level"], 3)
        self.assertEqual([i["name"] for i in route_3["leads_to"]["interactables"]], ["Lass"])
        # last level: exits are listed with their status, not expanded
        pewter = _exits(route_3["leads_to"])["Pewter City"]
        self.assertEqual(pewter, {"exit": "Pewter City", "visited": True})

    def test_default_view_goes_six_levels_deep(self):
        self._chain_to_pewter()
        node = self.world.leads_to("Mt. Moon Pokecenter", (0, 0), (1, 0))
        route_3 = _exits(node)["Route 3"]["leads_to"]
        self.assertEqual(_exits(route_3)["Pewter City"]["leads_to"]["level"], 4)

    def test_exit_back_into_current_area_is_omitted(self):
        self.world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        self.world.record_transition("Route 4", (0, 0), "Mt. Moon Pokecenter", (1, 0), (0, 0))
        node = self.world.leads_to("Mt. Moon Pokecenter", (0, 1), (1, 0))
        self.assertEqual(set(_exits(node)), {"Route 3"})

    def test_return_to_any_area_above_is_omitted(self):
        world = World()
        world.visit(_map("Mt. Moon 1F", ["..."], exits=[("Mt. Moon B1F", (0, 2))]))
        world.visit(_map("Mt. Moon B1F", ["...", "..."],
                         exits=[("Mt. Moon 1F", (0, 0)), ("Mt. Moon B2F (south)", (1, 2))]))
        world.visit(_map("Mt. Moon B2F", ["..."], interactables=[("Rocket", (0, 1))],
                         exits=[("Mt. Moon B1F (south)", (0, 0))]))
        world.record_transition("Mt. Moon 1F", (0, 2), "Mt. Moon B1F", (0, 0), (0, 2))
        world.record_transition("Mt. Moon B1F", (1, 2), "Mt. Moon B2F", (0, 0), (1, 2))
        b1f = world.leads_to("Mt. Moon 1F", (0, 0), (0, 2))
        # the ladder back up to 1F and, inside B2F, the ladder back to B1F
        self.assertEqual(set(_exits(b1f)), {"Mt. Moon B2F (south)"})
        b2f = _exits(b1f)["Mt. Moon B2F (south)"]["leads_to"]
        self.assertEqual(b2f["interactables"], [{"name": "Rocket", "interacted": False}])
        self.assertEqual(b2f["exits"], [])

    def test_sprites_blocking_the_way_hide_what_is_behind(self):
        world = World()
        world.visit(_map("Mt. Moon B1F", ["..."], exits=[("Mt. Moon B2F", (0, 2))]))
        world.visit(_map("Mt. Moon B2F", ["....", "#..#"],
                         interactables=[("Fossil (north-west)", (0, 1)),
                                        ("Fossil (north-west)", (1, 1))],
                         exits=[("Mt. Moon B1F (west)", (0, 0)), ("Mt. Moon B1F", (0, 3))]))
        world.record_transition("Mt. Moon B1F", (0, 2), "Mt. Moon B2F", (0, 3), (0, 2))
        b2f = world.leads_to("Mt. Moon B1F", (0, 0), (0, 2))
        # the fossils wall off the west exit, but can still be picked up
        self.assertEqual(_exits(b2f), {})
        self.assertEqual([i["name"] for i in b2f["interactables"]],
                         ["Fossil (north-west)", "Fossil (north-west)"])
        # only the top fossil frees the way on its own
        self.assertEqual([i.get("blocks_way_to") for i in b2f["interactables"]],
                         [["Mt. Moon B1F (west)"], None])

    def test_objects_blocking_together_are_marked_at_the_edge(self):
        world = World()
        world.visit(_map("Cave A", ["..."], exits=[("Cave B", (0, 2))]))
        world.visit(_map("Cave B", ["....."],
                         interactables=[("Boulder", (0, 1)), ("Hiker", (0, 2))],
                         exits=[("Cave C", (0, 0)), ("Cave A", (0, 4))]))
        world.record_transition("Cave A", (0, 2), "Cave B", (0, 4), (0, 2))
        cave_b = world.leads_to("Cave A", (0, 0), (0, 2))
        # neither frees the way alone; the Hiker is the one in front
        self.assertEqual(cave_b["interactables"],
                         [{"name": "Hiker", "interacted": False,
                           "blocks_way_to": ["Boulder", "Cave C"]}])

    def test_interactions_are_tracked_per_object_even_without_dialogue(self):
        world = World()
        world.visit(_map("Mt. Moon B1F", ["..."], exits=[("Mt. Moon B2F", (0, 2))]))
        b2f_map = _map("Mt. Moon B2F", ["....", "...."],
                       interactables=[("Fossil (north-west)", (0, 0)),
                                      ("Fossil (north-west)", (0, 1))],
                       exits=[("Mt. Moon B1F", (0, 3))])
        world.visit(b2f_map)
        world.record_transition("Mt. Moon B1F", (0, 2), "Mt. Moon B2F", (0, 3), (0, 2))
        world.record_interaction("Mt. Moon B2F", "Fossil (north-west)", position=(0, 1))
        world.visit(b2f_map)  # rescanning keeps which one was checked
        b2f = world.leads_to("Mt. Moon B1F", (0, 0), (0, 2))
        self.assertEqual([i["interacted"] for i in b2f["interactables"]], [False, True])

    def test_edge_connection_round_trip_is_not_shown_again(self):
        # Route 24: an upper strip (row 0) above a ledge (row 1) and the lower
        # area (rows 2-3) that Cerulean opens into. The east edge leads to
        # Route 25; crossing back can land on either part.
        world = World()
        world.visit(_map("Cerulean City", ["...."], exits=[]))
        r24 = Map(name="Route 24", grid=_grid(["....", "vvvv", "....", "...."]),
                  interactables=[Interactable("Rocket", (2, 1), "sprite")],
                  connected_maps=[
                      MapConnection(map=Map(name="Cerulean City"), position=(3, 1),
                                    kind="connection", conn_dir="down"),
                      MapConnection(map=Map(name="Route 25"), position=(1, 3),
                                    kind="connection", conn_dir="right")])
        r25 = Map(name="Route 25", grid=_grid(["....", "....", "....", "...."]),
                  interactables=[Interactable("Hiker", (1, 2), "sprite")],
                  connected_maps=[MapConnection(map=Map(name="Route 24"), position=(1, 0),
                                                kind="connection", conn_dir="left")])
        world.visit(r24)
        world.visit(r25)
        world.visit(Map(name="Cerulean City", grid=_grid(["...."]), connected_maps=[
            MapConnection(map=Map(name="Route 24"), position=(0, 1),
                          kind="connection", conn_dir="up")]))
        world.record_transition("Cerulean City", (0, 1), "Route 24", (3, 1), (0, 1),
                                via_connection=True)
        world.record_transition("Route 24", (1, 3), "Route 25", (3, 0), (3, 3),
                                via_connection=True)
        # came back along the upper strip: the latest landing is up there
        world.record_transition("Route 25", (1, 0), "Route 24", (0, 3), (0, 0),
                                via_connection=True)
        r24_node = world.leads_to("Cerulean City", (0, 0), (0, 1))
        r25_node = _exits(r24_node)["Route 25"]["leads_to"]
        self.assertEqual([i["name"] for i in r25_node["interactables"]], ["Hiker"])
        # the way back west only reaches parts of Route 24 already shown
        self.assertEqual(_exits(r25_node), {})

    def test_npc_memory_shows_in_nested_view(self):
        self.world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        self.world.record_interaction("Route 4", "Woman (west)", "Ouch! I tripped!")
        self.world.visit(ROUTE_4)  # rescanning keeps the memory
        node = self.world.leads_to("Mt. Moon Pokecenter", (0, 0), (1, 0))
        self.assertEqual(node["interactables"],
                         [{"name": "Woman (west)", "said": "Ouch! I tripped!", "interacted": True}])

    def test_persists_through_store(self):
        store = MemoryStore()
        world = World(store=store)
        for m in (ROUTE_4, POKECENTER):
            world.visit(m)
        world.record_transition("Mt. Moon Pokecenter", (1, 0), "Route 4", (0, 0), (1, 0))
        world.record_interaction("Route 4", "Woman (west)", "Ouch!")
        reloaded = World(store=store)
        self.assertTrue(reloaded.exit_taken("Mt. Moon Pokecenter", (1, 0)))
        node = reloaded.leads_to("Mt. Moon Pokecenter", (0, 0), (1, 0))
        self.assertEqual(set(_exits(node)), {"Route 3"})
        self.assertEqual(node["interactables"][0]["said"], "Ouch!")


if __name__ == "__main__":
    unittest.main()
