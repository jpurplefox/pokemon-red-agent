"""Overworld navigation — pathfinding, walking, and POI interaction (SRP).

Handles the 'go' command: selecting a POI, finding a path, walking
step-by-step with interrupt detection, and interacting on arrival.
"""

import sys
import select

from data.constants import ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD, ADDR_IS_IN_BATTLE
from adapters.input.pathfinder import find_best_path
from adapters.display.console import prompt_poi_selection

MAX_NPC_RETRIES = 3


class Navigator:
    def __init__(self, pyboy, screen, scanner, event_processor):
        self._pyboy = pyboy
        self._screen = screen
        self._scanner = scanner
        self._event_processor = event_processor
        self._pending_blocked = set()  # blocked tiles for current action (survives resume)

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

        self._go_to_poi(poi, print_surroundings, result, all_pois=pois)
        return result

    def go_to(self, poi, print_surroundings, all_pois=None):
        """Navigate directly to a specific POI (for AI usage).

        Same as go() but skips interactive POI selection.
        """
        result = {"map_changed": False, "show_pois": False}
        self._go_to_poi(poi, print_surroundings, result, all_pois=all_pois)
        return result

    def clear_blocked(self):
        """Clear discovered blocked tiles (call when action completes)."""
        self._pending_blocked.clear()

    def _go_to_poi(self, poi, print_surroundings, result, attempt=1,
                   all_pois=None, known_blocked=None):
        """Walk to a POI and interact. Retries if NPC moved."""
        mem = self._pyboy.memory
        grid, _, _, ledges = self._scanner.get_walkable_grid()
        blocked = self._scanner.get_npc_tiles()
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]

        if known_blocked is None:
            known_blocked = set()
        known_blocked |= self._pending_blocked
        for by, bx in known_blocked:
            if 0 <= by < len(grid) and 0 <= bx < len(grid[0]):
                grid[by][bx] = False

        # Tiles of other POIs — avoid standing on them to interact
        other_poi_tiles = set()
        # Warp tiles — avoid walking through them to prevent accidental warps
        warp_tiles = set()
        if all_pois:
            for p in all_pois:
                if p is not poi:
                    other_poi_tiles.add((p["ty"], p["tx"]))
                if p["kind"] == "warp" and p is not poi:
                    warp_tiles.add((p["ty"], p["tx"]))

        path, face = find_best_path(grid, (py, px), poi, blocked,
                                    other_poi_tiles, ledges, warp_tiles)
        if path is None:
            print(f"Cannot reach {poi['label']}.")
            return

        # If already standing on a warp tile (0 steps), step off first then walk back
        if not path and poi["kind"] in ("warp", "exit") and (py, px) == (poi["ty"], poi["tx"]):
            dirs = {(-1, 0): "up", (1, 0): "down",
                    (0, -1): "left", (0, 1): "right"}
            for (dy, dx), direction in dirs.items():
                ny, nx = py + dy, px + dx
                if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and grid[ny][nx]:
                    self._pyboy.button(direction, delay=8)
                    self._pyboy.tick(50)
                    path = [(py, px)]  # walk back to the warp tile
                    face = None
                    break

        # Walk step by step, recalculating path before each move
        if attempt == 1:
            print(f"Walking to {poi['label']} ({len(path)} steps)...")
        else:
            print(f"Retrying... ({len(path)} steps)")
        start_map = mem[ADDR_MAP_N]
        consecutive_fails = 0
        while path:
            # Check if user pressed Enter to interrupt
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                result["user_interrupt"] = True
                return

            # Re-scan NPC position if target is a sprite
            if poi["kind"] == "sprite":
                updated = self._find_same_npc(poi)
                if updated:
                    poi = updated
            # Recalculate path from current position
            grid, _, _, ledges = self._scanner.get_walkable_grid()
            for by, bx in known_blocked:
                if 0 <= by < len(grid) and 0 <= bx < len(grid[0]):
                    grid[by][bx] = False
            blocked = self._scanner.get_npc_tiles()
            py, px = mem[ADDR_Y_COORD], mem[ADDR_X_COORD]
            new_path, new_face = find_best_path(grid, (py, px), poi, blocked,
                                                other_poi_tiles, ledges,
                                                warp_tiles)
            if new_path is not None:
                path = new_path
                face = new_face
            if not path:
                break
            # Take the first step
            direction = path.pop(0)
            old_py, old_px = py, px
            self._pyboy.button(direction, delay=8)
            self._pyboy.tick(50)  # Extra frames for walk animation to finish

            # Verify the player actually moved — if not, check why
            new_py, new_px = mem[ADDR_Y_COORD], mem[ADDR_X_COORD]
            if (new_py, new_px) == (old_py, old_px) and mem[ADDR_MAP_N] == start_map:
                # Battle started — not a blocked tile
                if mem[ADDR_IS_IN_BATTLE] != 0:
                    return
                # Check if a trainer stopped us (text on screen)
                if self._screen.read_text_box():
                    print("Interrupted!")
                    lines = self._event_processor.process()
                    result["dialogue"] = " ".join(lines) if lines else ""
                    print_surroundings()
                    return
                # No text — tile is blocked (bad collision data)
                dy = {"up": -1, "down": 1}.get(direction, 0)
                dx = {"left": -1, "right": 1}.get(direction, 0)
                bad_tile = (old_py + dy, old_px + dx)
                known_blocked.add(bad_tile)
                self._pending_blocked.add(bad_tile)
                if 0 <= bad_tile[0] < len(grid) and 0 <= bad_tile[1] < len(grid[0]):
                    grid[bad_tile[0]][bad_tile[1]] = False
                consecutive_fails += 1
                if consecutive_fails >= 5:
                    print("Too many blocked tiles — aborting navigation.")
                    result["interrupted"] = True
                    print_surroundings()
                    return
                continue
            consecutive_fails = 0

            if self._screen.read_text_box():
                print("Interrupted!")
                lines = self._event_processor.process()
                result["dialogue"] = " ".join(lines) if lines else ""
                if path:
                    result["mid_walk_interrupt"] = True
                print_surroundings()
                return
            if mem[ADDR_MAP_N] != start_map:
                result["map_changed"] = True
                result["show_pois"] = True
                # Wait long enough for map-entry events (e.g. Mart parcel)
                # to trigger — NPCs may walk toward the player first
                for _ in range(20):
                    self._pyboy.tick(30)
                    if self._screen.read_text_box() or self._poll_for_event():
                        lines = self._event_processor.process()
                        result["dialogue"] = " ".join(lines) if lines else ""
                        break
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

        if poi["kind"] == "grass":
            self._walk_in_grass()
        elif face is None:
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

    def _walk_in_grass(self):
        """Walk back and forth in tall grass until a wild battle triggers."""
        from data.constants import ADDR_IS_IN_BATTLE
        mem = self._pyboy.memory
        print("Searching for wild Pokémon...")
        directions = ["left", "right", "right", "left"]
        for _ in range(50):  # max 50 steps before giving up
            for d in directions:
                self._pyboy.button(d, delay=8)
                self._pyboy.tick(30)
                if mem[ADDR_IS_IN_BATTLE] != 0:
                    return
                if self._screen.read_text_box():
                    return

    def _poll_for_event(self):
        """Wait briefly to see if an interaction triggered a cutscene."""
        for _ in range(20):
            self._pyboy.tick(10)
            if self._screen.read_text_box():
                return True
        return False
