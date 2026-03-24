"""Overworld AI controller — coordinates AI decisions with game actions (SRP).

Extracted from Game class to satisfy Single Responsibility Principle.
Game dispatches to this controller; this controller drives the AI agent,
navigator, and records results.
"""

import sys
import select

from data.constants import (
    ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD, ADDR_POKEDEX_FLAG,
    ADDR_BADGES, ADDR_PLAYER_NAME, ADDR_PLAY_HOURS, ADDR_PLAY_MINUTES,
    ADDR_PLAY_SECONDS, MAP_NAMES, POKEMON_CHARMAP,
)
from adapters.display.ai_logger import AILogger, print_metrics
from adapters.openai_llm import CloudLLMError
from domain.models import HUDState


class OverworldAIController:
    """Drives the overworld AI: reads game state, asks AI, executes actions."""

    def __init__(self, overworld_ai, pyboy, scanner, navigator, battle,
                 bag_reader, print_surroundings_fn, handle_game_menu_fn,
                 logger: AILogger | None = None):
        self._ai = overworld_ai
        self._pyboy = pyboy
        self._scanner = scanner
        self._navigator = navigator
        self._battle = battle
        self._bag = bag_reader
        self._print_surroundings = print_surroundings_fn
        self._handle_game_menu = handle_game_menu_fn
        self._log = logger or AILogger("OW")
        self._paused = False
        self._pending_poi = None  # POI to resume after battle interrupt
        self._pending_map = None  # Map ID where the interrupt happened
        self._last_player_name = ""

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
            self._pending_poi = None
            return "paused"

        # Resume interrupted action (e.g. after wild battle)
        if self._pending_poi is not None:
            mem = self._pyboy.memory
            # Don't resume grass POIs — the battle already fulfilled the goal
            if self._pending_poi.get("kind") == "grass":
                self._pending_poi = None
                self._pending_map = None
            elif mem[ADDR_MAP_N] == self._pending_map:
                poi = self._pending_poi
                self._pending_poi = None
                self._pending_map = None
                self._log.log_event(f"Resuming: GO to {poi['label']}")
                map_name = MAP_NAMES.get(mem[ADDR_MAP_N], f"Map {mem[ADDR_MAP_N]}")
                self._handle_go_with_poi(poi, map_name, mem)
                return "acted"
            else:
                self._pending_poi = None
                self._pending_map = None

        mem = self._pyboy.memory
        map_id = mem[ADDR_MAP_N]
        map_name = MAP_NAMES.get(map_id, f"Map {map_id}")
        pois = self._scanner.get_pois()
        grid, _, _, _ = self._scanner.get_walkable_grid()
        py, px = mem[ADDR_Y_COORD], mem[ADDR_X_COORD]

        party = self._battle.read_party()
        pokeballs = self._bag.count_pokeballs()
        has_pokedex = bool(mem[ADDR_POKEDEX_FLAG] & (1 << 5))

        # Read player info for HUD (before AI thinks, so HUD stays visible)
        player_name = ""
        for i in range(11):
            tile = mem[ADDR_PLAYER_NAME + i]
            if tile == 0x50:
                break
            player_name += POKEMON_CHARMAP.get(tile, "")
        self._last_player_name = player_name
        hours = mem[ADDR_PLAY_HOURS] | (mem[ADDR_PLAY_HOURS + 1] << 8)
        minutes = mem[ADDR_PLAY_MINUTES]
        seconds = mem[ADDR_PLAY_SECONDS]
        play_time = f"{hours}:{minutes:02d}:{seconds:02d}"

        active_sg = self._ai.active_subgoal()
        hud = HUDState(
            team=party,
            goal=self._ai.goal,
            subgoal=active_sg["description"] if active_sg else "",
            action_count=self._ai.iteration,
            badges=mem[ADDR_BADGES],
            map_name=map_name,
            player_name=player_name,
            play_time=play_time,
        )
        self._log.update_hud(hud)

        money = self._bag.read_money()
        print_metrics()
        try:
            result = self._ai.decide(
                map_name, pois, grid=grid, player_y=py, player_x=px,
                party=party, pokeballs=pokeballs, has_pokedex=has_pokedex,
                money=money, badges=mem[ADDR_BADGES],
                player_name=player_name,
            )
        except CloudLLMError:
            self.pause()
            return "paused"

        # Update HUD again after decide (think time + action count updated)
        hud.action_count = self._ai.iteration
        hud.subgoal = (self._ai.active_subgoal() or {}).get("description", "")
        self._log.update_hud(hud)

        if result is None:
            print("AI couldn't decide — returning control to you.")
            return "pause"

        action_type, detail = result

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
        self._handle_go_with_poi(poi, map_name, mem, all_pois=pois,
                                 poi_num=detail + 1)

    def _handle_go_with_poi(self, poi, map_name, mem, all_pois=None,
                                poi_num=0):
        """Navigate to a specific POI dict and record the result."""
        self._ai.record_poi_visited(map_name, poi["label"])
        result = self._navigator.go_to(poi, self._print_surroundings,
                                       all_pois=all_pois)

        # User pressed Enter during navigation — pause immediately
        if result.get("user_interrupt"):
            self.pause()
            return

        # If a battle interrupted the walk, save POI to resume after
        # (keep blocked tiles for the resume)
        if self._battle.is_in_battle():
            self._pending_poi = poi
            self._pending_map = mem[ADDR_MAP_N]
            return

        # Action completed — clear blocked tiles
        self._navigator.clear_blocked()

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
            poi_num=poi_num,
            reason=getattr(self._ai, '_last_think', ''),
        )

        # Reflect only when there was dialogue
        if dialogue:
            self._ai.reflect(
                map_name, action_desc,
                result=result_desc, dialogue=dialogue,
                player_name=self._last_player_name,
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
            player_name=self._last_player_name,
        )
