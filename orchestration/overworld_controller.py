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
from domain.maps import Interactable, MapConnection
from domain.models import HUDState


class OverworldAIController:
    """Drives the overworld AI: reads game state, asks AI, executes actions."""

    def __init__(self, overworld_ai, pyboy, scanner, navigator, battle,
                 bag_reader, print_surroundings_fn, handle_game_menu_fn,
                 logger: AILogger | None = None, world=None):
        self._ai = overworld_ai
        self._pyboy = pyboy
        self._scanner = scanner
        self._navigator = navigator
        self._battle = battle
        self._bag = bag_reader
        self._print_surroundings = print_surroundings_fn
        self._handle_game_menu = handle_game_menu_fn
        self._log = logger or AILogger("OW")
        self._world = world
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
            if self._pending_poi.kind == "grass":
                self._pending_poi = None
                self._pending_map = None
            elif mem[ADDR_MAP_N] == self._pending_map:
                poi = self._pending_poi
                self._pending_poi = None
                self._pending_map = None
                self._log.log_event(f"Resuming: GO to {_poi_name(poi)}")
                map_name = MAP_NAMES.get(mem[ADDR_MAP_N], f"Map {mem[ADDR_MAP_N]}")
                self._handle_go_with_poi(poi, map_name, mem)
                return "acted"
            else:
                self._pending_poi = None
                self._pending_map = None

        mem = self._pyboy.memory
        map_id = mem[ADDR_MAP_N]
        map_name = MAP_NAMES.get(map_id, f"Map {map_id}")
        current_map = self._scanner.read_map()
        if self._world:
            self._world.visit(current_map)
        grid, _, _, _ = self._scanner.get_walkable_grid()
        py, px = mem[ADDR_Y_COORD], mem[ADDR_X_COORD]

        # The agent only chooses among POIs it can actually reach
        blocked = self._scanner.get_npc_tiles()
        targets = (current_map.reachable_interactables((py, px), blocked)
                   + current_map.reachable_connections((py, px), blocked))
        all_pois = current_map.interactables + current_map.connected_maps
        # TODO: migrate overworld_ai.decide() to accept Map directly
        pois = [self._poi_dict(t, map_name, (py, px)) for t in targets]

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
        hours = mem[ADDR_PLAY_HOURS]
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
        key_items = self._bag.get_key_items()
        print_metrics()
        result = self._ai.decide(
            map_name, pois, grid=grid, player_y=py, player_x=px,
            party=party, pokeballs=pokeballs, has_pokedex=has_pokedex,
            money=money, badges=mem[ADDR_BADGES],
            player_name=player_name, key_items=key_items,
        )

        # Update HUD again after decide (think time + action count updated)
        hud.action_count = self._ai.iteration
        hud.subgoal = (self._ai.active_subgoal() or {}).get("description", "")
        self._log.update_hud(hud)

        if result is None:
            print("AI couldn't decide — returning control to you.")
            return "pause"

        if len(result) == 3:
            action_type, detail, action_label = result
        else:
            action_type, detail = result
            action_label = ""

        if action_type == "go":
            self._handle_go_with_poi(targets[detail], map_name, mem,
                                     all_pois=all_pois, action_label=action_label)
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

    def _poi_dict(self, poi, map_name, position):
        """Prompt-facing dict for a domain POI (what decide() consumes).

        Exits carry whether they were ever taken and, if so, the known world
        behind them (see World.leads_to).
        """
        d = {"label": _poi_name(poi), "ty": poi.position[0],
             "tx": poi.position[1], "kind": poi.kind}
        if self._world and isinstance(poi, Interactable):
            d["last_interaction"] = self._world.last_interaction(map_name, poi.name)
        if self._world and isinstance(poi, MapConnection):
            d["visited"] = self._world.exit_taken(map_name, poi.position)
            d["leads_to"] = self._world.leads_to(map_name, position, poi.position)
        return d

    def _handle_go_with_poi(self, poi, map_name, mem, all_pois=None,
                                action_label=""):
        """Navigate to a domain POI and record the result."""
        label = _poi_name(poi)
        self._ai.record_poi_visited(map_name, label)
        start_map_id = mem[ADDR_MAP_N]
        exits_here = [p for p in (all_pois or self._scanner.read_map().connected_maps)
                      if isinstance(p, MapConnection)]
        result = self._navigator.go_to(poi, self._print_surroundings,
                                       all_pois=all_pois)

        # User pressed Enter during navigation — pause immediately
        if result.get("user_interrupt"):
            self.pause()
            return

        # If a battle interrupted the walk mid-path, save POI to resume
        # (keep blocked tiles for the resume)
        # Only resume for battles — NPC dialogue interrupts are not resumable
        if self._battle.is_in_battle():
            self._pending_poi = poi
            self._pending_map = mem[ADDR_MAP_N]
            return

        new_map_id = mem[ADDR_MAP_N]
        new_map_name = MAP_NAMES.get(new_map_id, f"Map {new_map_id}")
        dialogue = result.get("dialogue", "")
        # The navigator only flags map changes that happen while walking;
        # door mats and map edges switch maps on the final step.
        map_changed = result.get("map_changed") or new_map_id != start_map_id

        # The exit actually crossed: usually the chosen one, but the walk may
        # step on another warp on the way.
        crossed = poi if isinstance(poi, MapConnection) else None
        if map_changed and result.get("exit_tile"):
            crossed = _exit_at(exits_here, result["exit_tile"]) or crossed

        if self._world and crossed is not None and map_changed:
            via_connection = crossed.kind == "connection"
            back = (result.get("exit_from", crossed.position) if via_connection
                    else crossed.position)
            self._world.record_transition(
                map_name, crossed.position, new_map_name,
                (mem[ADDR_Y_COORD], mem[ADDR_X_COORD]), back,
                via_connection=via_connection)

        if result.get("blocked"):
            action_desc = f"Tried to go to {label}"
            result_desc = "Blocked — cannot reach this area"
        elif (map_changed and crossed is not None
              and tuple(crossed.position) != tuple(poi.position)):
            action_desc = f"Went to {_poi_name(crossed)} on the way to {label}"
            result_desc = f"Arrived at {new_map_name}"
            if dialogue:
                result_desc += f" {dialogue}"
        elif map_changed:
            action_desc = f"Went to {label}"
            result_desc = f"Arrived at {new_map_name}"
            if dialogue:
                result_desc += f" {dialogue}"
        else:
            action_desc = f"Interacted with {label}"
            result_desc = dialogue or ""

        self._ai.record_action(
            action_desc, map_name, result_desc,
            poi_label=label, poi_kind=poi.kind,
            action_label=action_label,
            reason=getattr(self._ai, '_last_think', ''),
        )

        if (self._world and isinstance(poi, Interactable) and poi.kind != "grass"
                and not map_changed and not result.get("blocked")):
            self._world.record_interaction(map_name, poi.name, dialogue or None,
                                           position=poi.position)

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


def _poi_name(poi) -> str:
    return poi.map.name if isinstance(poi, MapConnection) else poi.name


def _exit_at(exits, tile, max_dist=2):
    """The exit on (or, for multi-tile doors, next to) the tile that fired."""
    best, best_dist = None, max_dist + 1
    for conn in exits:
        if conn.conn_dir:
            continue
        dist = abs(conn.position[0] - tile[0]) + abs(conn.position[1] - tile[1])
        if dist < best_dist:
            best, best_dist = conn, dist
    return best
