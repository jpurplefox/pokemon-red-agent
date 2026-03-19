"""Overworld AI controller — coordinates AI decisions with game actions (SRP).

Extracted from Game class to satisfy Single Responsibility Principle.
Game dispatches to this controller; this controller drives the AI agent,
navigator, and records results.
"""

import sys
import select

from data.constants import ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD, ADDR_POKEDEX_FLAG, MAP_NAMES


class OverworldAIController:
    """Drives the overworld AI: reads game state, asks AI, executes actions."""

    def __init__(self, overworld_ai, pyboy, scanner, navigator, battle,
                 bag_reader, print_surroundings_fn, handle_game_menu_fn):
        self._ai = overworld_ai
        self._pyboy = pyboy
        self._scanner = scanner
        self._navigator = navigator
        self._battle = battle
        self._bag = bag_reader
        self._print_surroundings = print_surroundings_fn
        self._handle_game_menu = handle_game_menu_fn
        self._paused = False

    @property
    def paused(self):
        return self._paused

    def pause(self):
        self._paused = True
        print("\n  ⏸️  AI paused — you have control now. Type 'ai' to resume.")

    def resume(self):
        self._paused = False
        print("  ▶️  AI resumed!")

    def check_user_interrupt(self) -> bool:
        """Check if the user pressed Enter to take over from the AI."""
        if select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.readline()
            self.pause()
            return True
        return False

    def tick(self) -> str:
        """Execute one AI decision cycle.

        Returns:
            "paused"       — user interrupted
            "goal_reached" — main goal completed
            "acted"        — action taken normally
        """
        if self.check_user_interrupt():
            return "paused"

        mem = self._pyboy.memory
        map_id = mem[ADDR_MAP_N]
        map_name = MAP_NAMES.get(map_id, f"Map {map_id}")
        pois = self._scanner.get_pois()
        grid, _, _ = self._scanner.get_walkable_grid()
        py, px = mem[ADDR_Y_COORD], mem[ADDR_X_COORD]

        party = self._battle.read_party()
        pokeballs = self._bag.count_pokeballs()
        has_pokedex = bool(mem[ADDR_POKEDEX_FLAG] & (1 << 5))

        action_type, detail = self._ai.decide(
            map_name, pois, grid=grid, player_y=py, player_x=px,
            party=party, pokeballs=pokeballs, has_pokedex=has_pokedex,
        )

        if action_type == "goal_reached":
            print("AI has reached its goal — returning control to you.")
            return "goal_reached"

        if action_type == "go":
            self._handle_go(pois, detail, map_name, mem)
        elif action_type == "move":
            self._pyboy.button(detail, delay=8)
            self._pyboy.tick(30)
            self._ai.record_action(f"Moved {detail}", map_name, "")
            self._print_surroundings()
        elif action_type == "look":
            self._print_surroundings()
        elif action_type == "start":
            self._pyboy.button("start", delay=8)
            self._pyboy.tick(30)
            self._handle_game_menu()

        return "acted"

    def _handle_go(self, pois, detail, map_name, mem):
        """Navigate to a POI and record the result."""
        poi = pois[detail]
        self._ai.record_poi_visited(map_name, poi["label"])
        result = self._navigator.go_to(poi, self._print_surroundings)

        new_map_id = mem[ADDR_MAP_N]
        new_map_name = MAP_NAMES.get(new_map_id, f"Map {new_map_id}")
        dialogue = result.get("dialogue", "")

        if result.get("map_changed"):
            action_desc = f"Went to {poi['label']}"
            result_desc = f"Arrived at {new_map_name}"
        else:
            action_desc = f"Interacted with {poi['label']}"
            result_desc = dialogue or ""

        self._ai.record_action(
            action_desc, map_name, result_desc,
            poi_label=poi['label'], poi_kind=poi['kind'],
            poi_num=detail + 1,
        )

        # Reflect only when there was dialogue
        if dialogue:
            self._ai.reflect(
                map_name, action_desc,
                result=result_desc, dialogue=dialogue,
            )

    def record_battle(self, summary, map_name):
        """Record a battle result in the AI's history and reflect on it."""
        action_desc = f"Battle vs {summary['type']} {summary['enemy']}"
        self._ai.record_action(
            action_desc, map_name,
            result_text=summary['result'],
        )
        self._ai.reflect(
            map_name, action_desc,
            result=summary['result'],
        )
