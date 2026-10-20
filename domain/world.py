"""World memory — what the player has discovered, as a graph of entrances.

Every map the player stands on is stored with its walkability grid, its
interactables (keeping what each one said) and its exits. An exit only
knows where it leads — destination map and arrival tile — once the player
has used it: taken it, or arrived through it (the way back leads to where
the player came from). Until then it is unvisited, even if the destination
map is known through another exit.

What is visible through an exit depends on where it lands: the part of the
destination map reachable from the arrival tile (ledges and tile-pair rules
included). `leads_to()` expands an exit of the current map into that view,
nesting the exits found there, up to a number of levels (the current map is
level 1).
"""

from __future__ import annotations

from typing import Protocol

from domain.maps import (
    Coordinates, Direction, Interactable, LedgeTile, Map, MapConnection,
    PassableTile, WalkabilityGrid,
)
from domain.pathfinder import as_tiles, interaction_tiles, poi_reachable, reachable_tiles

DEFAULT_VIEW_LEVELS = 6

# Grid serialization: one char per tile. 'a'+mask for passable tiles,
# 'A'+direction for ledges (Direction values are single bits 1..8).
_PASSABLE_BASE = ord("a")
_LEDGE_BASE = ord("A")


class JSONStore(Protocol):
    def load(self) -> list: ...
    def save(self, data: list) -> None: ...


def _encode_grid(grid: WalkabilityGrid) -> list[str]:
    rows = []
    for y in range(grid.height):
        row = []
        for x in range(grid.width):
            tile = grid[y, x]
            if isinstance(tile, LedgeTile):
                row.append(chr(_LEDGE_BASE + tile.jump_direction.value))
            else:
                row.append(chr(_PASSABLE_BASE + tile.passable.value))
        rows.append("".join(row))
    return rows


def _decode_grid(rows: list[str]) -> WalkabilityGrid:
    tiles = []
    for row in rows:
        decoded = []
        for ch in row:
            code = ord(ch)
            if code >= _PASSABLE_BASE:
                decoded.append(PassableTile(passable=Direction(code - _PASSABLE_BASE)))
            else:
                decoded.append(LedgeTile(jump_direction=Direction(code - _LEDGE_BASE)))
        tiles.append(decoded)
    return WalkabilityGrid(tiles=tiles)


class World:
    def __init__(self, store: JSONStore | None = None):
        self._store = store
        self._maps: dict[str, dict] = {}
        self._grids: dict[str, WalkabilityGrid] = {}
        if store:
            for rec in store.load():
                # Skip records from the old map-level format (no grid)
                if "grid" in rec and isinstance(rec.get("interactables"), list):
                    self._maps[rec["name"]] = rec

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def visit(self, current: Map) -> None:
        """Store a freshly scanned map, keeping NPC memory and taken exits."""
        old = self._maps.get(current.name, {})
        memory = _interaction_memory(old.get("interactables", []))
        taken = {tuple(ex["pos"]): ex.get("leads_to")
                 for ex in old.get("exits", [])}
        rec = {
            "name": current.name,
            "grid": _encode_grid(current.grid) if current.grid else old.get("grid", []),
            "interactables": [
                {"name": it.name, "kind": it.kind, "pos": list(it.position),
                 **memory(it.name, it.position)}
                for it in current.interactables
            ],
            "exits": [
                {"label": c.map.name, "kind": c.kind, "pos": list(c.position),
                 "conn_dir": c.conn_dir, "leads_to": taken.get(tuple(c.position)),
                 "crossable": (sorted(map(list, c.crossable))
                               if c.crossable is not None else None)}
                for c in current.connected_maps
            ],
            "arrivals": old.get("arrivals", []),
        }
        _apply_arrivals(rec)
        if rec == old:
            return
        self._maps[current.name] = rec
        self._grids.pop(current.name, None)
        # The grid changes slightly as the player moves (their tile is always
        # walkable); persist only when something else changed.
        without_grid = lambda r: {k: v for k, v in r.items() if k != "grid"}
        if without_grid(rec) != without_grid(old):
            self._save()

    def record_transition(self, map_name: str, exit_position: Coordinates,
                          dest_map: str, arrival: Coordinates,
                          back_position: Coordinates,
                          via_connection: bool = False) -> None:
        """Remember where a taken exit leads, and the way back.

        `back_position` is where the player reappears in map_name when
        going back through the exit they arrived by: the warp tile itself,
        or for map-edge connections the tile they crossed from.
        """
        ex = self._exit(map_name, exit_position)
        lead = {"map": dest_map, "pos": list(arrival)}
        back = {"map": map_name, "pos": list(back_position)}
        if via_connection:
            # Map edges keep a fixed offset between the two maps: crossing
            # at any other tile of the edge lands at that tile + offset.
            lead["offset"] = [arrival[0] - back_position[0], arrival[1] - back_position[1]]
            back["offset"] = [-lead["offset"][0], -lead["offset"][1]]
        if ex is not None:
            ex["leads_to"] = lead
        dest = self._maps.setdefault(dest_map, {
            "name": dest_map, "grid": [], "interactables": [], "exits": [],
            "arrivals": []})
        dest.setdefault("arrivals", [])
        dest["arrivals"] = [a for a in dest["arrivals"] if a["pos"] != list(arrival)]
        dest["arrivals"].append({
            "pos": list(arrival),
            "via": "connection" if via_connection else "warp",
            "from": back,
        })
        _apply_arrivals(dest)
        self._save()

    def record_interaction(self, map_name: str, name: str,
                           text: str | None = None,
                           position: Coordinates | None = None) -> None:
        """Remember an interaction and what it said (latest text wins).

        Matched by name and position when given, since several interactables
        can share a name (two "Fossil (north-west)").
        """
        items = self._maps.get(map_name, {}).get("interactables", [])
        same_name = [it for it in items if it["name"] == name]
        match = next((it for it in same_name
                      if position is not None and tuple(it["pos"]) == tuple(position)),
                     same_name[0] if same_name else None)
        if match is None:
            return
        match["interacted"] = True
        if text:
            match["last_interaction"] = text
        self._save()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def last_interaction(self, map_name: str, name: str) -> str | None:
        for it in self._maps.get(map_name, {}).get("interactables", []):
            if it["name"] == name:
                return it.get("last_interaction")
        return None

    def exit_taken(self, map_name: str, exit_position: Coordinates) -> bool:
        ex = self._exit(map_name, exit_position)
        return bool(ex and ex.get("leads_to"))

    def leads_to(self, map_name: str, position: Coordinates,
                 exit_position: Coordinates,
                 levels: int = DEFAULT_VIEW_LEVELS) -> dict | None:
        """What lies behind an exit of the current map, or None if never taken.

        `position` is the player's tile; it is used to recognize exits that
        lead back into the part of the current map the player is in.
        """
        ex = self._exit(map_name, exit_position)
        if not ex or not ex.get("leads_to"):
            return None
        reached = self._reach(map_name, position)
        landings = self._landings(map_name, reached, ex)
        return self._node(ex["leads_to"]["map"], landings, 2, levels,
                          [(map_name, reached)])

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _node(self, map_name: str, arrivals: list[Coordinates], level: int,
              levels: int, areas: list) -> dict:
        """Expand the area reached by arriving at any of `arrivals`.

        `areas` are the (map, reached tiles) of the current area and of
        every node above this one; exits leading back into any of them are
        omitted, since they add nothing (e.g. the ladder you came down).
        """
        rec = self._maps.get(map_name)
        if rec is None:
            return {"map": map_name}
        grid = self._grid(map_name)
        reached = self._reach(map_name, arrivals)
        blockers = self._blockers(map_name, arrivals, reached)
        # Parts of this map already shown higher up in the branch: list only
        # what is new compared to them.
        shown = set().union(*(r for m, r in areas if m == map_name))

        def new(poi):
            return (poi_reachable(grid, reached, poi)
                    and not (shown and poi_reachable(grid, shown, poi)))

        interactables = []
        for it in rec["interactables"]:
            poi = Interactable(it["name"], tuple(it["pos"]), it["kind"])
            if new(poi):
                entry = {"name": it["name"]}
                if it.get("last_interaction"):
                    entry["said"] = it["last_interaction"]
                if it["kind"] not in ("grass", "cut_tree"):
                    entry["interacted"] = bool(it.get("interacted"))
                if blockers.get(tuple(it["pos"])):
                    entry["blocks_way_to"] = blockers[tuple(it["pos"])]
                interactables.append(entry)
        exits = []
        areas = areas + [(map_name, reached)]
        for ex in rec["exits"]:
            conn = _conn(ex)
            if not poi_reachable(grid, reached, conn):
                continue
            # an edge connection reachable before may still open new landings
            if shown and not ex.get("conn_dir") and poi_reachable(grid, shown, conn):
                continue
            dest = ex.get("leads_to")
            landings = []
            if dest:
                # Drop landings back into an area already shown above; an
                # exit with none left is just the way back.
                landings = [p for p in self._landings(map_name, reached, ex)
                            if not _lands_in(dest["map"], p, areas)]
                if not landings:
                    continue
            entry = {"exit": ex["label"], "visited": dest is not None}
            if dest and level < levels:
                child = self._node(dest["map"], landings, level + 1, levels, areas)
                if child.get("nothing_new"):
                    continue
                entry["leads_to"] = child
            exits.append(entry)
        node = {"map": map_name, "level": level,
                "interactables": interactables, "exits": exits}
        if shown and not interactables and not exits:
            node["nothing_new"] = True
        return node

    def _exit(self, map_name: str, exit_position: Coordinates) -> dict | None:
        for ex in self._maps.get(map_name, {}).get("exits", []):
            if tuple(ex["pos"]) == tuple(exit_position):
                return ex
        return None

    def _grid(self, map_name: str) -> WalkabilityGrid:
        if map_name not in self._grids:
            self._grids[map_name] = _decode_grid(self._maps[map_name]["grid"])
        return self._grids[map_name]

    def _sprites(self, map_name: str) -> set[Coordinates]:
        return {tuple(it["pos"]) for it in self._maps[map_name]["interactables"]
                if it["kind"] == "sprite"}

    def _trees(self, map_name: str) -> set[Coordinates]:
        return {tuple(it["pos"]) for it in self._maps[map_name]["interactables"]
                if it["kind"] == "cut_tree"}

    def _reach(self, map_name: str, positions,
               blocked: set[Coordinates] | None = None,
               open_tiles: set[Coordinates] | None = None) -> set[Coordinates]:
        """Tiles reachable from a position (or several), with NPCs and items
        (sprites, as last seen) blocking the way unless `blocked` says
        otherwise; `open_tiles` (cut trees) are treated as cleared."""
        starts = as_tiles(positions)
        rec = self._maps.get(map_name)
        if not rec or not rec["grid"]:
            return starts
        if blocked is None:
            blocked = self._sprites(map_name)
        return reachable_tiles(self._grid(map_name), starts, blocked - starts,
                               open_tiles)

    def _landings(self, map_name: str, reached: set[Coordinates],
                  ex: dict) -> list[Coordinates]:
        """Where taking exit `ex` from the reached area lands.

        A warp always lands on the same tile. A map-edge connection lands
        wherever the player crosses: each reachable edge tile shifted by the
        connection's offset.
        """
        dest = ex["leads_to"]
        if ex.get("conn_dir") and dest.get("offset"):
            conn = _conn(ex)
            dy, dx = dest["offset"]
            dest_grid = self._maps.get(dest["map"], {}).get("grid") or []
            h, w = len(dest_grid), len(dest_grid[0]) if dest_grid else 0
            landings = sorted(
                (y + dy, x + dx)
                for y, x in interaction_tiles(self._grid(map_name), conn) & reached
                if not dest_grid or (0 <= y + dy < h and 0 <= x + dx < w))
            if landings:
                return landings
        return [tuple(dest["pos"])]

    def _blockers(self, map_name: str, arrival,
                  reached: set[Coordinates]) -> dict[Coordinates, list[str]]:
        """Sprites and cut trees at the edge of the reached area that hide
        something.

        Maps each blocker's tile to the names of the exits and interactables
        it keeps out of reach (a sprite by standing there, a tree until CUT
        clears it). Blockers that only work together (none frees the way
        alone) share whatever stays hidden.
        """
        rec = self._maps[map_name]
        grid = self._grid(map_name)
        sprites = self._sprites(map_name)
        trees = self._trees(map_name)

        def visible(reach):
            names = set()
            for ex in rec["exits"]:
                conn = _conn(ex)
                if poi_reachable(grid, reach, conn):
                    names.add(("exit", ex["label"], tuple(ex["pos"])))
            for it in rec["interactables"]:
                poi = Interactable(it["name"], tuple(it["pos"]), it["kind"])
                if poi_reachable(grid, reach, poi):
                    names.add(("it", it["name"], tuple(it["pos"])))
            return names

        now = visible(reached)
        hidden = visible(self._reach(map_name, arrival, blocked=set(),
                                     open_tiles=trees)) - now
        if not hidden:
            return {}
        frontier = [pos for pos in sprites | trees
                    if any((pos[0] + dy, pos[1] + dx) in reached
                           for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)))]
        result, freed = {}, set()
        for pos in frontier:
            if pos in trees:
                without = self._reach(map_name, arrival, sprites, open_tiles={pos})
            else:
                without = self._reach(map_name, arrival, sprites - {pos})
            opened = (visible(without) - now) & hidden
            opened = {h for h in opened if h[2] != pos}  # not the sprite itself
            if opened:
                result[pos] = opened
                freed |= opened
        leftover = hidden - freed
        if leftover:
            for pos in frontier:
                result.setdefault(pos, set()).update(
                    h for h in leftover if h[2] != pos)
        return {pos: sorted(name for _, name, _ in items)
                for pos, items in result.items() if items}

    def _save(self) -> None:
        if self._store:
            self._store.save(list(self._maps.values()))


def _apply_arrivals(rec: dict) -> None:
    """Mark the exits the player arrived through as leading back."""
    for arrival in rec.get("arrivals", []):
        ex = _arrival_exit(rec, arrival)
        if ex is not None and not ex.get("leads_to"):
            ex["leads_to"] = dict(arrival["from"])


def _arrival_exit(rec: dict, arrival: dict) -> dict | None:
    """The exit of rec matching an arrival: the warp on/next to the arrival
    tile, or the connection on the map edge the player appeared at."""
    y, x = arrival["pos"]
    if arrival["via"] == "connection":
        h = len(rec["grid"])
        w = len(rec["grid"][0]) if h else 0
        edge = ("up" if y == 0 else "down" if y == h - 1
                else "left" if x == 0 else "right" if x == w - 1 else None)
        return next((ex for ex in rec["exits"] if ex.get("conn_dir") == edge), None)
    best, best_dist = None, 2
    for ex in rec["exits"]:
        if ex.get("conn_dir"):
            continue
        dist = abs(ex["pos"][0] - y) + abs(ex["pos"][1] - x)
        if dist < best_dist:
            best, best_dist = ex, dist
    return best


def _lands_in(dest_map: str, pos: Coordinates, areas: list) -> bool:
    """Whether landing at pos in dest_map falls in one of the given areas.

    Landing on a tile next to the area counts too: stairs and doors are
    often not walkable tiles themselves.
    """
    y, x = pos
    landing = {(y, x), (y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)}
    return any(map_name == dest_map and landing & reached
               for map_name, reached in areas)


def _interaction_memory(old_items: list[dict]):
    """Lookup of what was remembered about each interactable on a rescan:
    by name and position first (NPCs can share a name), then by name."""
    by_key = {(it["name"], tuple(it["pos"])): it for it in old_items}
    by_name = {}
    for it in old_items:
        by_name.setdefault(it["name"], it)

    def memory(name: str, position: Coordinates) -> dict:
        old = by_key.get((name, tuple(position))) or by_name.get(name) or {}
        return {"last_interaction": old.get("last_interaction"),
                "interacted": bool(old.get("interacted") or old.get("last_interaction"))}
    return memory


def _conn(ex: dict) -> MapConnection:
    """Domain connection for a stored exit record."""
    crossable = ex.get("crossable")
    return MapConnection(map=Map(name=ex["label"]), position=tuple(ex["pos"]),
                         kind=ex["kind"], conn_dir=ex.get("conn_dir"),
                         crossable=(frozenset(map(tuple, crossable))
                                    if crossable is not None else None))
