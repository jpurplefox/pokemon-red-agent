"""A* pathfinder — pure algorithm, no game dependencies (SRP).

Operates on a 2D walkability grid at tile resolution.
Dependencies (grid, obstacles) injected via function arguments (DIP).
"""

import heapq

# (dy, dx, direction_name)
_NEIGHBORS = [(-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")]

# Mapping: if player is at (py, px) and POI tile is at (py+dy, px+dx),
# the player must FACE this direction to interact.
_FACE_DIR = {(-1, 0): "down", (1, 0): "up", (0, -1): "right", (0, 1): "left"}


def find_path(grid, start, goal, blocked=None):
    """Find shortest path from start to goal using A*.

    Args:
        grid:    list[list[bool]] — grid[y][x] is True if walkable.
        start:   (y, x) tuple.
        goal:    (y, x) tuple.
        blocked: set of (y, x) dynamically blocked tiles (NPCs).

    Returns:
        List of direction strings ["up", "down", "left", ...], or None.
    """
    if blocked is None:
        blocked = set()

    h = len(grid)
    w = len(grid[0]) if h else 0

    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    counter = 0
    open_set = [(heuristic(start, goal), counter, start)]
    came_from = {}        # node -> (prev_node, direction_str)
    g_score = {start: 0}

    while open_set:
        _, _, current = heapq.heappop(open_set)

        if current == goal:
            path = []
            node = current
            while node in came_from:
                prev, direction = came_from[node]
                path.append(direction)
                node = prev
            path.reverse()
            return path

        # Skip if we already found a better path to this node
        cy, cx = current
        if g_score.get(current, float("inf")) < g_score.get(current, float("inf")):
            continue

        for dy, dx, direction in _NEIGHBORS:
            ny, nx = cy + dy, cx + dx

            if ny < 0 or ny >= h or nx < 0 or nx >= w:
                continue

            # Goal tile is always reachable (warps may not be in WALKABLE_BLOCKS)
            if (ny, nx) != goal and not grid[ny][nx]:
                continue
            if (ny, nx) != goal and (ny, nx) in blocked:
                continue

            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get((ny, nx), float("inf")):
                g_score[(ny, nx)] = tentative_g
                came_from[(ny, nx)] = (current, direction)
                counter += 1
                f = tentative_g + heuristic((ny, nx), goal)
                heapq.heappush(open_set, (f, counter, (ny, nx)))

    return None


def find_interaction_targets(poi, grid, blocked=None):
    """Determine valid tiles from which the player can interact with a POI.

    For warps:   walk onto the warp tile itself (auto-activates).
    For exits:   walk onto the tile, then press down to go through.
    For others:  walkable tile adjacent to the POI tile, face + press A.

    Returns list of (goal_y, goal_x, face_direction).
    face_direction is None for warps, "down" for exits.
    """
    if blocked is None:
        blocked = set()

    kind = poi["kind"]
    ty, tx = poi["ty"], poi["tx"]
    h = len(grid)
    w = len(grid[0]) if h else 0

    if kind == "warp":
        return [(ty, tx, None)]

    if kind == "exit":
        return [(ty, tx, "down")]

    if kind == "connection":
        # Walk to any walkable edge tile, then step off the map
        conn = poi["conn_dir"]
        if conn == "up":
            return [(0, x, "up") for x in range(w)
                    if grid[0][x] and (0, x) not in blocked]
        if conn == "down":
            return [(h - 1, x, "down") for x in range(w)
                    if grid[h - 1][x] and (h - 1, x) not in blocked]
        if conn == "left":
            return [(y, 0, "left") for y in range(h)
                    if grid[y][0] and (y, 0) not in blocked]
        if conn == "right":
            return [(y, w - 1, "right") for y in range(h)
                    if grid[y][w - 1] and (y, w - 1) not in blocked]
        return []

    # Determine which tiles the POI occupies
    if kind == "block":
        poi_tiles = {(ty, tx), (ty + 1, tx), (ty, tx + 1), (ty + 1, tx + 1)}
    else:
        poi_tiles = {(ty, tx)}

    # Find walkable tiles adjacent to any POI tile
    targets = []
    seen = set()
    for pty, ptx in poi_tiles:
        for (dy, dx), face in _FACE_DIR.items():
            ny, nx = pty + dy, ptx + dx
            if (ny, nx) in seen:
                continue
            seen.add((ny, nx))

            if 0 <= ny < h and 0 <= nx < w:
                if grid[ny][nx] and (ny, nx) not in blocked:
                    if (ny, nx) not in poi_tiles:
                        targets.append((ny, nx, face))

    return targets


def find_best_path(grid, start, poi, blocked=None):
    """Find the shortest path to any valid interaction tile for a POI.

    Returns (path, face_direction) or (None, None) if unreachable.
    path is a list of direction strings, face_direction is the direction
    to face for interaction (None for warps).
    """
    if blocked is None:
        blocked = set()

    targets = find_interaction_targets(poi, grid, blocked)
    if not targets:
        return None, None

    best_path = None
    best_face = None

    for goal_y, goal_x, face in targets:
        path = find_path(grid, start, (goal_y, goal_x), blocked)
        if path is not None:
            if best_path is None or len(path) < len(best_path):
                best_path = path
                best_face = face

    return best_path, best_face
