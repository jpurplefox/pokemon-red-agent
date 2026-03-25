"""Shared data models and protocols for the Pokemon Red AI project.

Replaces untyped dicts with dataclasses for type safety and clarity.
Defines Protocols for strategy pattern contracts and LLM abstraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


# -- Pokemon & Battle data --------------------------------------------------

@dataclass
class Move:
    """A battle move with PP tracking."""
    name: str
    pp: int
    max_pp: int
    disabled: bool = False


@dataclass
class BattleMon:
    """A pokemon's battle stats (read from WRAM during battle)."""
    name: str
    level: int
    hp: int
    max_hp: int
    status: str
    moves: list[Move] = field(default_factory=list)


@dataclass
class PartyMember:
    """A pokemon in the player's party."""
    name: str
    nickname: str
    level: int
    hp: int
    max_hp: int


# -- Inventory --------------------------------------------------------------

@dataclass
class ShopItem:
    """An item available for purchase in a Poke Mart."""
    name: str
    price: int
    index: int


@dataclass
class BallInfo:
    """Poke Ball type with quantity and bag index."""
    name: str
    count: int
    index: int


# -- Display -----------------------------------------------------------------

@dataclass
class HUDState:
    """Snapshot of game state for the HUD display."""
    team: list[PartyMember] = field(default_factory=list)
    goal: str = ""
    subgoal: str = ""
    badges: int = 0
    map_name: str = ""
    player_name: str = ""
    play_time: str = ""
    action_count: int = 0


# -- Overworld AI ------------------------------------------------------------

@dataclass
class SubGoal:
    """A short-term quest tracked by the overworld AI."""
    description: str
    status: str  # "active", "done", "expired", "replaced"
    added_at: int
    done_at: Optional[int] = None


@dataclass
class HistoryEntry:
    """A single entry in the overworld exploration history."""
    action: str
    map: str
    result: str = ""
    poi: str = ""
    poi_kind: str = ""
    poi_num: int = 0


# -- Driven Ports (what the system needs from the outside) ------------------

class LLMPort(Protocol):
    """Abstract interface for LLM inference.

    Any LLM provider (Ollama, OpenAI, mock) can satisfy this Protocol.
    """

    def invoke(self, messages: list) -> object:
        """Send messages to the LLM and return a response with .content."""
        ...


class GameStatePort(Protocol):
    """Read-only access to battle and party state from the emulator."""

    def is_in_battle(self) -> bool: ...
    def is_wild(self) -> bool: ...
    def is_trainer(self) -> bool: ...
    def active_mon_index(self) -> int: ...
    def read_player(self) -> BattleMon: ...
    def read_enemy(self) -> BattleMon: ...
    def read_enemy_species(self) -> str: ...
    def read_party(self) -> list[PartyMember]: ...


class GameInputPort(Protocol):
    """Execute actions in the emulator via button presses."""

    def has_battle_menu(self) -> bool: ...
    def reset_move_cursor(self) -> None: ...
    def select_battle_option(self, option: str) -> None: ...
    def wait_for_move_menu(self, moves: list[Move]) -> None: ...
    def select_move(self, move_idx: int) -> None: ...
    def use_ball(self, bag_index: int) -> None: ...
    def switch_pokemon(self, party_idx: int) -> None: ...
    def navigate_party_menu(self, target_idx: int) -> None: ...
    def type_name(self, name: str) -> None: ...


class BagPort(Protocol):
    """Read-only access to the player's bag and money."""

    def count_pokeballs(self) -> int: ...
    def get_balls(self) -> list: ...
    def read_money(self) -> int: ...


class DisplayPort(Protocol):
    """Output adapter for showing AI reasoning to the user."""

    def log_prompt(self, label: str, system: str, user: str) -> None: ...
    def log_response(self, label: str, text: str) -> None: ...
    def log_think(self, msg: str) -> None: ...
    def log_event(self, msg: str, kind: str = "") -> None: ...


# -- Agent Ports (inter-agent communication) ---------------------------------

class CatchDecider(Protocol):
    """Decides whether to attempt catching a wild Pokémon."""

    def should_catch(self, enemy_name: str, enemy_level: int,
                     team: list) -> bool: ...


class BattleReflector(Protocol):
    """Extracts lessons from completed battles."""

    def reflect(self, history: list, battle_type: str, result: str,
                enemy_name: str) -> None: ...

    def get_memory(self) -> list: ...


class SubgoalReflector(Protocol):
    """Analyzes gameplay events and manages sub-goals."""

    iteration: int

    def reflect(self, map_name: str, action: str, result: str = "",
                dialogue: str = "", player_name: str = "") -> None: ...

    def active_subgoal(self) -> dict | None: ...


class PurchaseAdvisor(Protocol):
    """Decides what to buy at Poké Marts."""

    def decide_purchases(self, items: list, money: int, pokeballs: int,
                         party: list | None = None) -> list: ...


# -- Persistence Ports -------------------------------------------------------

class JSONStore(Protocol):
    """Abstract persistence for JSON data (lists of dicts)."""

    def load(self) -> list: ...

    def save(self, data: list) -> None: ...


# -- Strategy Protocol -------------------------------------------------------

class BattleDecider(Protocol):
    """Core battle decision making — choose moves and switches."""

    def decide(self, player: BattleMon, enemy: BattleMon,
               is_wild: bool, balls: list | None = None) -> tuple:
        """Choose a battle action: (action_type, detail)."""
        ...

    def choose_switch_in(self, party: list[PartyMember],
                         alive_indices: list[int], is_wild: bool,
                         enemy: BattleMon | None = None) -> tuple:
        """Choose a replacement pokemon after fainting."""
        ...

    def choose_switch_offer(self, party: list[PartyMember],
                            active_idx: int,
                            alive_indices: list[int]) -> tuple:
        """Decide whether to switch when offered (trainer battles)."""
        ...


class BattleTracker(Protocol):
    """Battle state tracking — team roster and turn history."""

    def set_team(self, team: list[PartyMember],
                 active_idx: int | None = None) -> None:
        """Update the current team roster."""
        ...

    def add_turn(self, text: str, player_hp: int, player_max_hp: int,
                 enemy_hp: int, enemy_max_hp: int) -> None:
        """Record a turn's result text and HP changes."""
        ...

    def get_history(self) -> list:
        """Return the battle turn history."""
        ...


class BattleLifecycle(Protocol):
    """Battle lifecycle hooks — start and end callbacks."""

    def on_battle_start(self, player: BattleMon, enemy: BattleMon,
                        is_wild: bool,
                        balls: list | None = None) -> None:
        """Called when a battle begins."""
        ...

    def on_battle_end(self, is_wild: bool,
                      result: str = "unknown") -> None:
        """Called when a battle ends."""
        ...


class BattleStrategy(BattleDecider, BattleTracker, BattleLifecycle, Protocol):
    """Full battle strategy — combines all battle protocols.

    BattleAI implements all three. ManualStrategy or simpler strategies
    can implement only the protocols they need.
    """
    ...
