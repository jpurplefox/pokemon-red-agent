"""Overworld navigation — pathfinding, walking, and POI interaction (SRP)."""

import sys
import select

from data.constants import ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD, ADDR_IS_IN_BATTLE
from domain.maps import Interactable, MapConnection, POI, Direction, _DIRECTION_OFFSETS
from domain.pathfinder import find_path_to_poi

MAX_NPC_RETRIES = 3

_BUTTON_OFFSETS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def _poi_name(poi: POI) -> str:
    if isinstance(poi, MapConnection):
        return poi.map.name
    return poi.name


def _poi_kind(poi: POI) -> str:
    return poi.kind


def _poi_sprite_index(poi: POI) -> int | None:
    if isinstance(poi, Interactable):
        return poi.sprite_index
    return None


class Navigator:
    def __init__(self, pyboy, screen, scanner, event_processor):
        self._pyboy = pyboy
        self._screen = screen
        self._scanner = scanner
        self._event_processor = event_processor

    def go_to(self, poi: POI, print_surroundings, all_pois: list[POI] | None = None):
        """Navigate directly to a specific POI."""
        result = {"map_changed": False, "show_pois": False}
        self._go_to_poi(poi, print_surroundings, result, all_pois=all_pois)
        return result

    def _go_to_poi(self, poi: POI, print_surroundings, result, attempt=1,
                   all_pois: list[POI] | None = None):
        """Walk to a POI and interact. Retries if NPC moved."""
        mem = self._pyboy.memory
        current_map = self._scanner.read_map()
        grid = current_map.grid
        blocked = self._scanner.get_npc_tiles()
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        # Always route around the other POIs (warps especially): stepping on
        # one by accident changes map. Resumed walks don't pass them in.
        if all_pois is None:
            all_pois = current_map.interactables + current_map.connected_maps

        name = _poi_name(poi)
        kind = _poi_kind(poi)

        path_result = find_path_to_poi(grid, (py, px), poi,
                                       all_pois=all_pois, blocked=blocked)
        if path_result is None:
            print(f"Cannot reach {name}.")
            return
        path, face = path_result

        # Already standing on a warp tile — step off first, then walk back
        if not path and kind in ("warp", "exit") and (py, px) == poi.position:
            for direction in (Direction.NORTH, Direction.SOUTH,
                              Direction.WEST, Direction.EAST):
                if grid.can_move((py, px), direction):
                    dy, dx = _DIRECTION_OFFSETS[direction]
                    dir_name = {Direction.NORTH: "up", Direction.SOUTH: "down",
                                Direction.WEST: "left", Direction.EAST: "right"}[direction]
                    self._pyboy.button(dir_name, delay=8)
                    self._pyboy.tick(20)
                    path = [dir_name]
                    face = None
                    break

        if attempt == 1:
            print(f"Walking to {name} ({len(path)} steps)...")
        else:
            print(f"Retrying... ({len(path)} steps)")
        start_map = mem[ADDR_MAP_N]
        consecutive_fails = 0
        while path:
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                result["user_interrupt"] = True
                return

            if kind == "sprite":
                updated = self._find_same_npc(poi)
                if updated:
                    poi = updated

            # Recalculate path from current position with fresh grid
            current_map = self._scanner.read_map()
            grid = current_map.grid
            blocked = self._scanner.get_npc_tiles()
            py, px = mem[ADDR_Y_COORD], mem[ADDR_X_COORD]
            new_result = find_path_to_poi(grid, (py, px), poi,
                                          all_pois=all_pois, blocked=blocked)
            if new_result is not None:
                path, face = new_result
            if not path:
                break

            direction = path.pop(0)
            old_py, old_px = py, px
            self._pyboy.button(direction, delay=8)
            self._pyboy.tick(20)

            new_py, new_px = mem[ADDR_Y_COORD], mem[ADDR_X_COORD]
            if (new_py, new_px) == (old_py, old_px) and mem[ADDR_MAP_N] == start_map:
                if mem[ADDR_IS_IN_BATTLE] != 0:
                    return
                if self._screen.read_text_box():
                    print("Interrupted!")
                    lines = self._event_processor.process()
                    result["dialogue"] = " ".join(lines) if lines else ""
                    print_surroundings()
                    return
                consecutive_fails += 1
                if consecutive_fails >= 5:
                    print("Too many failed moves — aborting navigation.")
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
                result["exit_from"] = (old_py, old_px)
                dy, dx = _BUTTON_OFFSETS[direction]
                result["exit_tile"] = (old_py + dy, old_px + dx)
                result["show_pois"] = True
                new_map = mem[ADDR_MAP_N]
                wait_cycles = 60 if new_map == 0x58 else 3
                for _ in range(wait_cycles):
                    self._pyboy.tick(20)
                    if self._screen.read_text_box() or self._poll_for_event():
                        lines = self._event_processor.process()
                        result["dialogue"] = " ".join(lines) if lines else ""
                        break
                return

        if kind == "sprite" and face is not None:
            if not self._is_npc_adjacent(poi):
                if attempt < MAX_NPC_RETRIES:
                    new_poi = self._find_same_npc(poi)
                    if new_poi:
                        print(f"{name} moved!")
                        self._go_to_poi(new_poi, print_surroundings,
                                        result, attempt + 1)
                        return
                print(f"{name} moved away. Try again.")
                print_surroundings()
                return

        self._interact(poi, face, result)

        if self._poll_for_event():
            print(f"Event at {name}!")
            lines = self._event_processor.process()
            result["dialogue"] = " ".join(lines) if lines else ""
            if mem[ADDR_IS_IN_BATTLE] != 0:
                return
            for _ in range(120):
                self._pyboy.tick(10)
                if mem[ADDR_IS_IN_BATTLE] != 0:
                    return
                new_text = self._screen.read_text_box()
                new_menu = self._event_processor.menu.read_choice_menu() if not new_text else None
                if new_text or new_menu:
                    extra = self._event_processor.process()
                    if extra:
                        result["dialogue"] += " " + " ".join(extra)
            print_surroundings()
            return

        text = self._screen.read_text_box()
        if text:
            lines = self._event_processor.process()
            result["dialogue"] = " ".join(lines) if lines else ""
            if mem[ADDR_IS_IN_BATTLE] != 0:
                return
            for _ in range(120):
                self._pyboy.tick(10)
                if mem[ADDR_IS_IN_BATTLE] != 0:
                    return
                new_text = self._screen.read_text_box()
                new_menu = self._event_processor.menu.read_choice_menu() if not new_text else None
                if new_text or new_menu:
                    extra = self._event_processor.process()
                    if extra:
                        result["dialogue"] += " " + " ".join(extra)
        else:
            print(f"Arrived at {name}.")
        print_surroundings()

    def _is_npc_adjacent(self, poi: POI) -> bool:
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        current_map = self._scanner.read_map()
        sprite_idx = _poi_sprite_index(poi)
        for it in current_map.interactables:
            if it.kind == "sprite" and it.sprite_index == sprite_idx:
                dy = abs(it.position[0] - py)
                dx = abs(it.position[1] - px)
                return (dy + dx) <= 2
        return False

    def _find_same_npc(self, poi: POI) -> Interactable | None:
        current_map = self._scanner.read_map()
        sprite_idx = _poi_sprite_index(poi)
        for it in current_map.interactables:
            if it.kind == "sprite" and it.sprite_index == sprite_idx:
                return it
        return None

    def _interact(self, poi: POI, face, result=None):
        mem = self._pyboy.memory
        kind = _poi_kind(poi)
        name = _poi_name(poi)

        if kind == "grass":
            self._walk_in_grass()
        elif face is None:
            self._pyboy.tick(100)
        elif kind == "connection":
            old_map = mem[ADDR_MAP_N]
            if result is not None:
                result["exit_from"] = (mem[ADDR_Y_COORD], mem[ADDR_X_COORD])
            self._pyboy.button(face, delay=8)
            for _ in range(20):
                self._pyboy.tick(10)
                if mem[ADDR_MAP_N] != old_map:
                    break
            if mem[ADDR_MAP_N] == old_map:
                print(f"Cannot cross to {name} (blocked).")
                if result is not None:
                    result["blocked"] = True
        elif kind == "exit":
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(30)
        else:
            self._pyboy.button(face, delay=8)
            self._pyboy.tick(20)
            self._pyboy.button("a", delay=8)
            self._pyboy.tick(20)

    def _walk_in_grass(self):
        from data.constants import ADDR_IS_IN_BATTLE
        mem = self._pyboy.memory
        print("Searching for wild Pokémon...")
        directions = ["left", "right", "right", "left"]
        for _ in range(50):
            for d in directions:
                self._pyboy.button(d, delay=8)
                self._pyboy.tick(20)
                if mem[ADDR_IS_IN_BATTLE] != 0:
                    return
                if self._screen.read_text_box():
                    return

    def _poll_for_event(self):
        for _ in range(20):
            self._pyboy.tick(10)
            if self._screen.read_text_box():
                return True
        return False
