"""A* pathfinder over the domain WalkabilityGrid."""

from __future__ import annotations

import heapq
from collections.abc import Iterable

from domain.maps import (
    Coordinates, Direction, WalkabilityGrid,
    Interactable, LedgeTile, MapConnection, POI,
    _DIRECTION_OFFSETS,
)

_DIRECTION_NAMES: dict[Direction, str] = {
    Direction.NORTH: "up",
    Direction.SOUTH: "down",
    Direction.WEST: "left",
    Direction.EAST: "right",
}

_FACE_DIR: dict[tuple[int, int], str] = {
    (-1, 0): "down",
    (1, 0): "up",
    (0, -1): "right",
    (0, 1): "left",
}


def find_path(
    grid: WalkabilityGrid,
    start: Coordinates,
    goal: Coordinates,
    blocked: set[Coordinates] | None = None,
) -> list[str] | None:
    """A* from start to goal. Returns direction strings or None."""
    if blocked is None:
        blocked = set()

    def heuristic(a: Coordinates, b: Coordinates) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    counter = 0
    open_set = [(heuristic(start, goal), counter, start)]
    came_from: dict[Coordinates, tuple[Coordinates, str]] = {}
    g_score: dict[Coordinates, int] = {start: 0}

    while open_set:
        _, _, current = heapq.heappop(open_set)

        if current == goal:
            path: list[str] = []
            node = current
            while node in came_from:
                prev, direction = came_from[node]
                path.append(direction)
                node = prev
            path.reverse()
            return path

        for direction in (Direction.NORTH, Direction.SOUTH,
                          Direction.EAST, Direction.WEST):
            if not grid.can_move(current, direction):
                continue
            dy, dx = _DIRECTION_OFFSETS[direction]
            neighbor = (current[0] + dy, current[1] + dx)

            if neighbor != goal and neighbor in blocked:
                continue

            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                came_from[neighbor] = (current, _DIRECTION_NAMES[direction])
                counter += 1
                heapq.heappush(open_set, (
                    tentative_g + heuristic(neighbor, goal),
                    counter,
                    neighbor,
                ))

    return None


def _interaction_targets(
    poi: POI,
    grid: WalkabilityGrid,
    blocked: set[Coordinates],
) -> list[tuple[int, int, str | None]]:
    """Tiles from which the player can interact with a POI.

    Returns list of (y, x, face_direction).
    face_direction is None for warps (walk onto tile), a direction string
    for everything else.
    """
    if isinstance(poi, MapConnection):
        return _connection_targets(poi, grid, blocked)
    return _interactable_targets(poi, grid, blocked)


def _interactable_targets(
    it: Interactable,
    grid: WalkabilityGrid,
    blocked: set[Coordinates],
) -> list[tuple[int, int, str | None]]:
    ty, tx = it.position

    if it.kind == "warp":
        return [(ty, tx, None)]

    if it.kind == "grass":
        return [(ty, tx, None)]

    if it.kind == "exit":
        face = "up" if ty <= 1 else "down"
        return [(ty, tx, face)]

    if it.kind == "block":
        poi_tiles = {(ty, tx), (ty + 1, tx), (ty, tx + 1), (ty + 1, tx + 1)}
    else:
        poi_tiles = {(ty, tx)}

    targets: list[tuple[int, int, str | None]] = []
    seen: set[Coordinates] = set()
    for pty, ptx in poi_tiles:
        for (dy, dx), face in _FACE_DIR.items():
            ny, nx = pty + dy, ptx + dx
            if (ny, nx) in seen:
                continue
            seen.add((ny, nx))
            if not (0 <= ny < grid.height and 0 <= nx < grid.width):
                continue
            if (ny, nx) in blocked or (ny, nx) in poi_tiles:
                continue
            targets.append((ny, nx, face))

    # Across-counter: Clerk/Nurse behind counters
    if it.kind == "sprite" and any(k in it.name for k in ("Clerk", "Nurse")):
        for pty, ptx in poi_tiles:
            for (dy, dx), face in _FACE_DIR.items():
                mid_y, mid_x = pty + dy, ptx + dx
                if 0 <= mid_y < grid.height and 0 <= mid_x < grid.width:
                    if grid[mid_y, mid_x].can_exit(Direction.ALL):
                        continue
                ny, nx = pty + 2 * dy, ptx + 2 * dx
                if (ny, nx) in seen:
                    continue
                seen.add((ny, nx))
                if not (0 <= ny < grid.height and 0 <= nx < grid.width):
                    continue
                if (ny, nx) in blocked or (ny, nx) in poi_tiles:
                    continue
                targets.append((ny, nx, face))

    return targets


def _connection_targets(
    conn: MapConnection,
    grid: WalkabilityGrid,
    blocked: set[Coordinates],
) -> list[tuple[int, int, str | None]]:
    return [t for t in _edge_targets(conn, grid, blocked)
            if conn.crossable is None or (t[0], t[1]) in conn.crossable]


def _edge_targets(
    conn: MapConnection,
    grid: WalkabilityGrid,
    blocked: set[Coordinates],
) -> list[tuple[int, int, str | None]]:
    h, w = grid.height, grid.width
    d = conn.conn_dir

    if d is None:
        ty, tx = conn.position
        if conn.kind == "exit":
            # Door mats: walk onto the tile, then press toward the edge
            return [(ty, tx, "up" if ty <= 1 else "down")]
        return [(ty, tx, None)]
    if d == "up":
        return [(0, x, "up") for x in range(w) if (0, x) not in blocked]
    if d == "down":
        return [(h - 1, x, "down") for x in range(w) if (h - 1, x) not in blocked]
    if d == "left":
        return [(y, 0, "left") for y in range(h) if (y, 0) not in blocked]
    if d == "right":
        return [(y, w - 1, "right") for y in range(h) if (y, w - 1) not in blocked]
    return []


def find_path_to_poi(
    grid: WalkabilityGrid,
    start: Coordinates,
    target: POI,
    all_pois: list[POI] | None = None,
    blocked: set[Coordinates] | None = None,
) -> tuple[list[str], str | None] | None:
    """Find shortest path to interact with a POI.

    Avoids stepping on tiles occupied by other POIs (warp tiles especially).

    Returns (path, face_direction) or None if unreachable.
    """
    if blocked is None:
        blocked = set()

    # Build set of tiles to avoid: other POIs' positions
    occupied = set(blocked)
    if all_pois:
        for p in all_pois:
            if p is not target:
                occupied.add(p.position)

    targets = _interaction_targets(target, grid, occupied)
    if not targets:
        return None

    best_path: list[str] | None = None
    best_face: str | None = None
    for goal_y, goal_x, face in targets:
        path = find_path(grid, start, (goal_y, goal_x), occupied)
        if path is not None:
            if best_path is None or len(path) < len(best_path):
                best_path = path
                best_face = face

    if best_path is None:
        return None
    return best_path, best_face


def as_tiles(tiles) -> set[Coordinates]:
    """One (y, x) tile, or an iterable of them, as a set of tuples."""
    if isinstance(tiles, (tuple, list)) and len(tiles) == 2 and isinstance(tiles[0], int):
        return {tuple(tiles)}
    return {tuple(t) for t in tiles}


def reachable_tiles(
    grid: WalkabilityGrid,
    start: Coordinates | Iterable[Coordinates],
    blocked: set[Coordinates] | None = None,
    open_tiles: set[Coordinates] | None = None,
) -> set[Coordinates]:
    """All tiles reachable from start (one tile or several), honoring ledges
    and tile-pair rules.

    A start tile may be impassable itself (e.g. arriving on a door tile),
    so leaving it only requires the neighbor to accept the entry.
    `open_tiles` are treated as walkable, to ask what lies behind an
    obstacle that can be removed (a tree CUT can clear).
    """
    if blocked is None:
        blocked = set()
    if open_tiles is None:
        open_tiles = set()
    starts = as_tiles(start)
    reached = set(starts)
    stack = list(starts)
    while stack:
        current = stack.pop()
        for direction, (dy, dx) in _DIRECTION_OFFSETS.items():
            neighbor = (current[0] + dy, current[1] + dx)
            if neighbor in reached or neighbor in blocked:
                continue
            if not (0 <= neighbor[0] < grid.height and 0 <= neighbor[1] < grid.width):
                continue
            if neighbor in open_tiles:
                pass
            elif current in open_tiles:
                # the grid was built with this tile as a wall, so neighbors
                # lack the direction toward it: any walkable neighbor will do
                if not _walkable_toward(grid[neighbor], direction):
                    continue
            elif current in starts:
                # leaving a start tile only needs the neighbor's consent
                if not grid[neighbor].can_enter(direction):
                    continue
            elif not grid.can_move(current, direction):
                continue
            reached.add(neighbor)
            stack.append(neighbor)
    return reached


def _walkable_toward(tile, direction: Direction) -> bool:
    """Whether a tile can be entered moving in direction, ignoring which
    neighbors it was built to connect to."""
    if isinstance(tile, LedgeTile):
        return tile.jump_direction == direction
    return tile.passable != Direction.NONE


def interaction_tiles(grid: WalkabilityGrid, poi: POI) -> set[Coordinates]:
    """Tiles from which the player can use poi (for edge connections, the
    whole walkable edge)."""
    return {(y, x) for y, x, _ in _interaction_targets(poi, grid, set())}


def poi_reachable(grid: WalkabilityGrid, reached: set[Coordinates], poi: POI) -> bool:
    """Whether the player can interact with poi from the reached tiles."""
    return not interaction_tiles(grid, poi).isdisjoint(reached)
