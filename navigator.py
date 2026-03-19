"""Overworld navigation — pathfinding, walking, and POI interaction (SRP).

Handles the 'go' command: selecting a POI, finding a path, walking
step-by-step with interrupt detection, and interacting on arrival.
"""

from constants import ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD
from pathfinder import find_best_path
from console import prompt_poi_selection

MAX_NPC_RETRIES = 3


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

        self._go_to_poi(poi, print_surroundings, result)
        return result

    def go_to(self, poi, print_surroundings):
        """Navigate directly to a specific POI (for AI usage).

        Same as go() but skips interactive POI selection.
        """
        result = {"map_changed": False, "show_pois": False}
        self._go_to_poi(poi, print_surroundings, result)
        return result

    def _go_to_poi(self, poi, print_surroundings, result, attempt=1):
        """Walk to a POI and interact. Retries if NPC moved."""
        mem = self._pyboy.memory
        grid, _, _ = self._scanner.get_walkable_grid()
        blocked = self._scanner.get_npc_tiles()
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]

        path, face = find_best_path(grid, (py, px), poi, blocked)
        if path is None:
            print(f"Cannot reach {poi['label']}.")
            return

        # Walk step by step, checking for interrupts
        if attempt == 1:
            print(f"Walking to {poi['label']} ({len(path)} steps)...")
        else:
            print(f"Retrying... ({len(path)} steps)")
        start_map = mem[ADDR_MAP_N]
        for direction in path:
            self._pyboy.button(direction, delay=8)
            self._pyboy.tick(30)

            if self._screen.read_text_box():
                print("Interrupted!")
                lines = self._event_processor.process()
                result["dialogue"] = " ".join(lines) if lines else ""
                print_surroundings()
                return
            if mem[ADDR_MAP_N] != start_map:
                self._pyboy.tick(300)
                result["map_changed"] = True
                result["show_pois"] = True
                # Capture any dialogue that triggers on map entry
                if self._screen.read_text_box() or self._poll_for_event():
                    lines = self._event_processor.process()
                    result["dialogue"] = " ".join(lines) if lines else ""
                return

        # For sprites (NPCs), verify they're still adjacent
        if poi["kind"] == "sprite" and face is not None:
            if not self._is_npc_adjacent(poi):
                if attempt < MAX_NPC_RETRIES:
                    # Re-scan to find NPC's new position
                    new_poi = self._find_same_npc(poi)
                    if new_poi:
                        print(f"{poi['label']} moved!")
                        self._go_to_poi(new_poi, print_surroundings,
                                        result, attempt + 1)
                        return
                print(f"{poi['label']} moved away. Try again.")
                print_surroundings()
                return

        # Interact with the POI based on its kind
        self._interact(poi, face)

        # Poll for event triggered by the interaction
        if self._poll_for_event():
            print(f"Event at {poi['label']}!")
            lines = self._event_processor.process()
            result["dialogue"] = " ".join(lines) if lines else ""
            print_surroundings()
            return

        # Check for simple dialogue (sign, NPC one-liner)
        text = self._screen.read_text_box()
        if text:
            lines = self._event_processor.process()
            result["dialogue"] = " ".join(lines) if lines else ""
        else:
            print(f"Arrived at {poi['label']}.")
        print_surroundings()

    def _is_npc_adjacent(self, poi):
        """Check if the target NPC is close enough to interact.

        Accepts Manhattan distance <= 2 to support across-counter
        interactions (e.g. Pokecenter nurse behind a counter).
        """
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]

        # Re-scan sprites to find current positions
        pois = self._scanner.get_pois()
        for p in pois:
            if (p["kind"] == "sprite"
                    and p.get("sprite_index") == poi.get("sprite_index")):
                dy = abs(p["ty"] - py)
                dx = abs(p["tx"] - px)
                # Distance 1 = adjacent, 2 = across counter
                return (dy + dx) <= 2
        return False

    def _find_same_npc(self, poi):
        """Find the same NPC in a fresh scan (may have moved)."""
        pois = self._scanner.get_pois()
        for p in pois:
            if (p["kind"] == "sprite"
                    and p.get("sprite_index") == poi.get("sprite_index")):
                return p
        return None

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
