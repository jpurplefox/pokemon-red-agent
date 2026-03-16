"""Overworld navigation — pathfinding, walking, and POI interaction (SRP).

Handles the 'go' command: selecting a POI, finding a path, walking
step-by-step with interrupt detection, and interacting on arrival.
"""

from constants import ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD
from pathfinder import find_best_path
from console import prompt_poi_selection


class Navigator:
    def __init__(self, pyboy, screen, scanner, event_processor):
        self._pyboy = pyboy
        self._screen = screen
        self._scanner = scanner
        self._event_processor = event_processor

    def go(self, print_surroundings):
        """Select a POI, pathfind to it, walk there, and interact.

        Args:
            print_surroundings: callback to display the map after arrival.

        Returns:
            dict with 'map_changed' (bool) and 'show_pois' (bool) flags.
        """
        result = {"map_changed": False, "show_pois": False}
        pois = self._scanner.get_pois()
        poi = prompt_poi_selection(pois)
        if not poi:
            return result

        grid, _, _ = self._scanner.get_walkable_grid()
        blocked = self._scanner.get_npc_tiles()
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]

        path, face = find_best_path(grid, (py, px), poi, blocked)
        if path is None:
            print(f"Cannot reach {poi['label']}.")
            return result

        # Walk step by step, checking for interrupts
        print(f"Walking to {poi['label']} ({len(path)} steps)...")
        start_map = mem[ADDR_MAP_N]
        for direction in path:
            self._pyboy.button(direction, delay=8)
            self._pyboy.tick(30)

            if self._screen.read_text_box():
                print("Interrupted!")
                self._event_processor.process()
                print_surroundings()
                return result
            if mem[ADDR_MAP_N] != start_map:
                # Map changed (warp/connection) — wait for transition
                # (fade out → load → fade in) before reading new map data
                self._pyboy.tick(300)
                result["map_changed"] = True
                result["show_pois"] = True
                return result

        # Interact with the POI based on its kind
        self._interact(poi, face)

        # Poll for event triggered by the interaction
        if self._poll_for_event():
            print(f"Event at {poi['label']}!")
            self._event_processor.process()
            print_surroundings()
            return result

        print(f"Arrived at {poi['label']}.")
        print_surroundings()
        return result

    def _interact(self, poi, face):
        """Perform the appropriate interaction for a POI kind."""
        mem = self._pyboy.memory

        if face is None:
            # Warp (stairs) — walking onto the tile activates it;
            # transition is handled by the walking loop's map-change check
            self._pyboy.tick(300)
        elif poi["kind"] == "connection":
            old_map = mem[ADDR_MAP_N]
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(60)
            if mem[ADDR_MAP_N] == old_map:
                print(f"Cannot cross to {poi['label']} (blocked).")
        elif poi["kind"] == "exit":
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(60)
        else:
            # Sign/Sprite — face the POI and press A
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(30)
            self._pyboy.button("a", delay=8)
            self._pyboy.tick(30)

    def _poll_for_event(self):
        """Wait briefly to see if an interaction triggered a cutscene."""
        for _ in range(20):
            self._pyboy.tick(10)
            if self._screen.read_text_box():
                return True
        return False
