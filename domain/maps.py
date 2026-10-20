from __future__ import annotations

from dataclasses import dataclass, field
from enum import Flag, auto
from typing import Protocol

type Coordinates = tuple[int, int]
type POI = Interactable | MapConnection


class Direction(Flag):
    NORTH = auto()
    SOUTH = auto()
    EAST = auto()
    WEST = auto()
    ALL = NORTH | SOUTH | EAST | WEST
    NONE = 0

    @property
    def opposite(self) -> Direction:
        result = Direction.NONE
        if Direction.NORTH in self:
            result |= Direction.SOUTH
        if Direction.SOUTH in self:
            result |= Direction.NORTH
        if Direction.EAST in self:
            result |= Direction.WEST
        if Direction.WEST in self:
            result |= Direction.EAST
        return result


class Tile(Protocol):
    @property
    def symbol(self) -> str: ...
    def can_exit(self, direction: Direction) -> bool: ...
    def can_enter(self, coming_from: Direction) -> bool: ...


_PASSABLE_SYMBOLS: dict[Direction, str] = {
    Direction.ALL: "+",
    Direction.NORTH | Direction.SOUTH | Direction.EAST: "├",
    Direction.NORTH | Direction.SOUTH | Direction.WEST: "┤",
    Direction.NORTH | Direction.EAST | Direction.WEST: "┴",
    Direction.SOUTH | Direction.EAST | Direction.WEST: "┬",
    Direction.NORTH | Direction.SOUTH: "│",
    Direction.EAST | Direction.WEST: "─",
    Direction.NORTH | Direction.EAST: "└",
    Direction.NORTH | Direction.WEST: "┘",
    Direction.SOUTH | Direction.EAST: "┌",
    Direction.SOUTH | Direction.WEST: "┐",
    Direction.NORTH: "╵",
    Direction.SOUTH: "╷",
    Direction.EAST: "╶",
    Direction.WEST: "╴",
    Direction.NONE: "·",
}

_LEDGE_SYMBOLS: dict[Direction, str] = {
    Direction.NORTH: "↑",
    Direction.SOUTH: "↓",
    Direction.EAST: "→",
    Direction.WEST: "←",
}

_DIRECTION_OFFSETS: dict[Direction, Coordinates] = {
    Direction.NORTH: (-1, 0),
    Direction.SOUTH: (1, 0),
    Direction.EAST: (0, 1),
    Direction.WEST: (0, -1),
}


@dataclass
class PassableTile:
    """A tile that allows movement in a set of directions."""
    passable: Direction = Direction.ALL

    @property
    def symbol(self) -> str:
        return _PASSABLE_SYMBOLS.get(self.passable, "?")

    def can_exit(self, direction: Direction) -> bool:
        return direction in self.passable

    def can_enter(self, coming_from: Direction) -> bool:
        return coming_from.opposite in self.passable


@dataclass
class LedgeTile:
    """A directional ledge — can only be crossed in one direction."""
    jump_direction: Direction = Direction.SOUTH

    @property
    def symbol(self) -> str:
        return _LEDGE_SYMBOLS.get(self.jump_direction, "?")

    def can_exit(self, direction: Direction) -> bool:
        return direction in self.jump_direction

    def can_enter(self, coming_from: Direction) -> bool:
        return coming_from in self.jump_direction


@dataclass
class WalkabilityGrid:
    tiles: list[list[Tile]]

    @property
    def height(self) -> int:
        return len(self.tiles)

    @property
    def width(self) -> int:
        return len(self.tiles[0]) if self.tiles else 0

    def __getitem__(self, coord: Coordinates) -> Tile:
        y, x = coord
        return self.tiles[y][x]

    def can_move(self, origin: Coordinates, direction: Direction) -> bool:
        """Check if movement is possible: origin allows exit AND neighbor allows entry."""
        dy, dx = _DIRECTION_OFFSETS[direction]
        oy, ox = origin
        ny, nx = oy + dy, ox + dx
        if not (0 <= ny < self.height and 0 <= nx < self.width):
            return False
        return self[origin].can_exit(direction) and self[ny, nx].can_enter(direction)



@dataclass
class Interactable:
    name: str
    position: Coordinates
    kind: str = "sign"
    sprite_index: int | None = None
    last_interaction: str | None = None


@dataclass
class MapConnection:
    map: Map
    position: Coordinates
    kind: str = "exit"
    conn_dir: str | None = None
    destination: Coordinates | None = None
    # For map-edge connections: edge tiles from which crossing works (the
    # tile across accepts the entry). None = unknown, any edge tile.
    crossable: frozenset[Coordinates] | None = None


@dataclass
class Map:
    name: str
    grid: WalkabilityGrid | None = None
    connected_maps: list[MapConnection] = field(default_factory=list)
    interactables: list[Interactable] = field(default_factory=list)

    def reachable_interactables(
        self, position: Coordinates,
        blocked: set[Coordinates] | None = None,
    ) -> list[Interactable]:
        from domain.pathfinder import find_path_to_poi

        if self.grid is None:
            return list(self.interactables)
        all_pois: list[POI] = list(self.interactables) + list(self.connected_maps)
        return [
            it for it in self.interactables
            if find_path_to_poi(self.grid, position, it,
                                all_pois=all_pois, blocked=blocked) is not None
        ]

    def reachable_connections(
        self, position: Coordinates,
        blocked: set[Coordinates] | None = None,
    ) -> list[MapConnection]:
        from domain.pathfinder import find_path_to_poi

        if self.grid is None:
            return list(self.connected_maps)
        all_pois: list[POI] = list(self.interactables) + list(self.connected_maps)
        return [
            c for c in self.connected_maps
            if find_path_to_poi(self.grid, position, c,
                                all_pois=all_pois, blocked=blocked) is not None
        ]

    def __str__(self) -> str:
        # Render base grid
        grid: list[list[str]] = []
        if self.grid:
            for y in range(self.grid.height):
                grid.append([self.grid[y, x].symbol for x in range(self.grid.width)])

        # Overlay markers: numbers for interactables, letters for connections
        legend: list[str] = []
        for i, interactable in enumerate(self.interactables):
            marker = str(i + 1)
            y, x = interactable.position
            if grid:
                grid[y][x] = marker
            legend.append(f"  {marker}: {interactable.name}")
        for i, connection in enumerate(self.connected_maps):
            marker = chr(ord("a") + i)
            y, x = connection.position
            if grid:
                grid[y][x] = marker
            legend.append(f"  {marker}: {connection.map.name}")

        lines = ["".join(row) for row in grid]
        lines.append("")
        lines.extend(legend)
        return "\n".join(lines)
