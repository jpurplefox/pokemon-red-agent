"""Overworld scanner — reads WRAM to build domain Map objects.

Orchestrates scanning of warps, blocks, signs, sprites, and connections.
Delegates walkability grid building, label disambiguation, and sprite
resolution to dedicated classes (SRP).
"""

from data.constants import (
    ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_NUM_WARPS, ADDR_WARP_ENTRIES,
    ADDR_NUM_SIGNS, ADDR_SIGN_COORDS,
    ADDR_NUM_SPRITES, ADDR_SPRITE_DATA, ADDR_SPRITE_DATA2,
    ADDR_MISSABLE_FLAGS, ADDR_MISSABLE_LIST,
    ADDR_TILESET, ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH,
    ADDR_OVERWORLD_MAP, MAP_BORDER, BLOCK_LABELS,
    BLOCK_DESCRIPTIONS, MAP_NAMES, ADDR_GRASS_TILE,
)
from domain.maps import (
    Map, Interactable, MapConnection,
    WalkabilityGrid as DomainGrid, PassableTile, LedgeTile, Direction,
)
from adapters.input.pathfinder import find_best_path
from adapters.state.walkability import WalkabilityGrid
from adapters.state.poi_disambiguator import dedup_warps, disambiguate_labels
from adapters.state.sprite_resolver import SpriteResolver

# Fixed POIs for maps where interactables can't be auto-detected
_FIXED_POIS = {
    0x58: [  # Bill's House — PC on the desk
        {"label": "PC", "ty": 4, "tx": 1, "kind": "sign"},
    ],
}

# Broken warps: (map_id, warp_index) — warps that are reachable but don't work
_BROKEN_WARPS = {
    (0x2F, 0),  # Viridian Forest North Gate — left door to Route 2
    (0x32, 0),  # Viridian Forest South Gate — left door to Viridian Forest
}

# Connections to hide — require HM moves not yet available (e.g. Surf)
# Format: (map_id, destination_label)
_BLOCKED_CONNECTIONS = {
    (0x00, "Route 21"),   # Pallet Town → Route 21 (needs Surf)
}


class OverworldScanner:
    def __init__(self, pyboy, rom_path=None):
        self._pyboy = pyboy
        self._rom = None
        if rom_path:
            with open(rom_path, 'rb') as f:
                self._rom = f.read()
        self._walkability = WalkabilityGrid(pyboy, self._rom)
        self._sprite_resolver = SpriteResolver(pyboy, self._rom)

    # ------------------------------------------------------------------
    # Public API — returns domain objects
    # ------------------------------------------------------------------

    def read_map(self) -> Map:
        """Read the current map from WRAM and return a domain Map object."""
        mem = self._pyboy.memory
        map_id = mem[ADDR_MAP_N]
        map_name = MAP_NAMES.get(map_id, f"Map {map_id}")
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]

        # Build raw POI dicts (legacy format for dedup/disambiguate/pathfinder)
        raw_pois = self._scan_all_raw(py, px)
        raw_pois = dedup_warps(raw_pois, py, px)
        raw_pois = disambiguate_labels(raw_pois, py, px)

        # Filter unreachable POIs
        warp_tiles = {(p["ty"], p["tx"]) for p in raw_pois if p["kind"] == "warp"}
        grid, _, _, ledges = self.get_walkable_grid()
        npc_blocked = self.get_npc_tiles()

        reachable = []
        for poi in raw_pois:
            avoid = warp_tiles - {(poi["ty"], poi["tx"])}
            path, _ = find_best_path(grid, (py, px), poi, blocked=npc_blocked,
                                     ledges=ledges, warps=avoid)
            if path is not None:
                reachable.append(poi)

        # Add grass POI if available
        current_map_name = MAP_NAMES.get(mem[ADDR_MAP_N], "")
        if current_map_name != "Pallet Town":
            grass = self._find_nearest_grass_raw(py, px, grid)
            if grass:
                path, _ = find_best_path(grid, (py, px), grass,
                                         blocked=npc_blocked, ledges=ledges,
                                         warps=warp_tiles)
                if path is not None:
                    reachable.append(grass)

        # Split into domain types
        interactables = []
        connections = []
        for poi in reachable:
            if poi["kind"] in ("exit", "warp", "connection"):
                dest_map = Map(name=poi["label"])
                connections.append(MapConnection(
                    map=dest_map,
                    position=(poi["ty"], poi["tx"]),
                ))
            else:
                interactables.append(Interactable(
                    name=poi["label"],
                    position=(poi["ty"], poi["tx"]),
                ))

        # Build domain grid
        domain_grid = self._build_domain_grid(grid, ledges)

        return Map(
            name=map_name,
            grid=domain_grid,
            connected_maps=connections,
            interactables=interactables,
        )

    def get_pois(self):
        """Return all nearby reachable POIs as dicts (legacy interface).

        Used by overworld_ai, navigator, and console display.
        """
        py = self._pyboy.memory[ADDR_Y_COORD]
        px = self._pyboy.memory[ADDR_X_COORD]

        raw_pois = self._scan_all_raw(py, px)
        raw_pois = dedup_warps(raw_pois, py, px)
        raw_pois = disambiguate_labels(raw_pois, py, px)

        warp_tiles = {(p["ty"], p["tx"]) for p in raw_pois if p["kind"] == "warp"}
        grid, _, _, ledges = self.get_walkable_grid()
        npc_blocked = self.get_npc_tiles()

        reachable = []
        for poi in raw_pois:
            avoid = warp_tiles - {(poi["ty"], poi["tx"])}
            path, _ = find_best_path(grid, (py, px), poi, blocked=npc_blocked,
                                     ledges=ledges, warps=avoid)
            if path is not None:
                reachable.append(poi)

        current_map = MAP_NAMES.get(self._pyboy.memory[ADDR_MAP_N], "")
        grass_poi = self._find_nearest_grass_raw(py, px, grid) if current_map != "Pallet Town" else None
        if grass_poi:
            path, _ = find_best_path(grid, (py, px), grass_poi,
                                     blocked=npc_blocked, ledges=ledges,
                                     warps=warp_tiles)
            if path is not None:
                reachable.append(grass_poi)

        return reachable

    # ------------------------------------------------------------------
    # Delegated methods (kept for backward compatibility)
    # ------------------------------------------------------------------

    _QUAD_INDICES = WalkabilityGrid._QUAD_INDICES
    _QUAD_REP_TILE = WalkabilityGrid._QUAD_REP_TILE

    def get_walkable_grid(self):
        """Delegate to WalkabilityGrid."""
        return self._walkability.get_grid()

    def get_collision_tiles(self):
        """Delegate to WalkabilityGrid."""
        return self._walkability.get_collision_tiles()

    def get_block_tiles(self, block_id):
        """Delegate to WalkabilityGrid."""
        return self._walkability.get_block_tiles(block_id)

    def block_walkability(self, block_tiles, collision_tiles):
        """Delegate to WalkabilityGrid."""
        return self._walkability.block_walkability(block_tiles, collision_tiles)

    def get_npc_tiles(self):
        """Return set of (ty, tx) tiles currently blocked by NPCs."""
        mem = self._pyboy.memory
        count = mem[ADDR_NUM_SPRITES]
        off = self._SPRITE_COORD_OFFSET
        hidden = self._get_hidden_sprites()

        blocked = set()
        for i in range(1, count + 1):
            if i in hidden:
                continue
            base1 = ADDR_SPRITE_DATA + i * 0x10
            if mem[base1] == 0 or mem[base1 + 1] == 0:
                continue
            base2 = ADDR_SPRITE_DATA2 + i * 0x10
            sy = mem[base2 + 4] - off
            sx = mem[base2 + 5] - off
            if sy >= 0 and sx >= 0:
                blocked.add((sy, sx))
        return blocked

    # ------------------------------------------------------------------
    # Internal: scan all raw POIs as dicts
    # ------------------------------------------------------------------

    def _scan_all_raw(self, py, px):
        """Collect all POIs as dicts (warps, blocks, fixed, sprites, connections)."""
        all_pois = []
        all_pois.extend(self._scan_warps(py, px))
        all_pois.extend(self._scan_blocks(py, px))
        map_id = self._pyboy.memory[ADDR_MAP_N]
        for fp in _FIXED_POIS.get(map_id, []):
            poi = dict(fp)
            poi["dir"] = self._relative_dir(py, px, poi["ty"], poi["tx"])
            all_pois.append(poi)
        all_pois.extend(self._scan_sprites(py, px))
        all_pois.extend(self._scan_connections(py, px))
        return all_pois

    # ------------------------------------------------------------------
    # Domain grid builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_domain_grid(bool_grid, ledges) -> DomainGrid:
        """Convert a bool grid + ledge set into a domain WalkabilityGrid."""
        h = len(bool_grid)
        w = len(bool_grid[0]) if h else 0

        ledge_lookup = {}
        if ledges:
            _DIR_MAP = {
                "down": Direction.SOUTH,
                "left": Direction.WEST,
                "right": Direction.EAST,
                "up": Direction.NORTH,
            }
            for entry in ledges:
                ly, lx, direction = entry
                ledge_lookup[(ly, lx)] = _DIR_MAP.get(direction, Direction.SOUTH)

        tiles = []
        for y in range(h):
            row = []
            for x in range(w):
                if (y, x) in ledge_lookup:
                    row.append(LedgeTile(jump_direction=ledge_lookup[(y, x)]))
                elif bool_grid[y][x]:
                    passable = Direction.NONE
                    if y > 0 and bool_grid[y - 1][x]:
                        passable |= Direction.NORTH
                    if y < h - 1 and bool_grid[y + 1][x]:
                        passable |= Direction.SOUTH
                    if x > 0 and bool_grid[y][x - 1]:
                        passable |= Direction.WEST
                    if x < w - 1 and bool_grid[y][x + 1]:
                        passable |= Direction.EAST
                    if passable == Direction.NONE:
                        passable = Direction.ALL
                    row.append(PassableTile(passable=passable))
                else:
                    row.append(PassableTile(passable=Direction.NONE))
            tiles.append(row)

        return DomainGrid(tiles=tiles)

    # ------------------------------------------------------------------
    # Grass scanning
    # ------------------------------------------------------------------

    def _find_nearest_grass_raw(self, py, px, grid):
        """Find the nearest tall grass tile and return a POI dict or None."""
        mem = self._pyboy.memory
        grass_tile = mem[ADDR_GRASS_TILE]
        if grass_tile == 0:
            return None

        if self._rom is None:
            return None

        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]
        row_width = W + 2 * MAP_BORDER

        grass_tiles = []
        for row in range(H):
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                block_id = mem[addr]
                bt = self.get_block_tiles(block_id)
                if bt is None:
                    continue
                positions = [
                    (row * 2, col * 2, bt[0]),
                    (row * 2, col * 2 + 1, bt[1]),
                    (row * 2 + 1, col * 2, bt[2]),
                    (row * 2 + 1, col * 2 + 1, bt[3]),
                ]
                for ty, tx, tile_id in positions:
                    if tile_id == grass_tile:
                        grass_tiles.append((ty, tx))

        if not grass_tiles:
            return None

        best = None
        best_dist = float("inf")
        for ty, tx in grass_tiles:
            if not grid[ty][tx]:
                continue
            dist = abs(ty - py) + abs(tx - px)
            if dist < best_dist:
                best_dist = dist
                best = (ty, tx)

        if best is None:
            return None

        return {
            "kind": "grass",
            "label": "Wild Pokémon (tall grass)",
            "ty": best[0],
            "tx": best[1],
            "dir": self._relative_dir(py, px, best[0], best[1]),
        }

    # ------------------------------------------------------------------
    # Warp scanning
    # ------------------------------------------------------------------

    def _scan_warps(self, py, px):
        """Read warp entries from WRAM (stairs, doors, map exits)."""
        mem = self._pyboy.memory
        count = mem[ADDR_NUM_WARPS]
        tileset = mem[ADDR_TILESET]
        descriptions = BLOCK_DESCRIPTIONS.get(tileset, {})
        W = mem[ADDR_MAP_WIDTH]
        row_width = W + 2 * MAP_BORDER

        map_id = mem[ADDR_MAP_N]
        results = []
        for i in range(count):
            if (map_id, i) in _BROKEN_WARPS:
                continue
            base = ADDR_WARP_ENTRIES + i * 4
            wy = mem[base]
            wx = mem[base + 1]
            dest_map = mem[base + 3]
            label, kind = self._warp_label(
                wy, wx, dest_map, descriptions, mem, row_width
            )
            results.append({
                "label": label,
                "dir": self._relative_dir(py, px, wy, wx),
                "ty": wy,
                "tx": wx,
                "kind": kind,
            })
        return results

    _BUILDING_MAP = {
        "house": "House",
        "lab": "Lab",
    }
    _GENERIC_TILES = {"floor", "door", "fence", "sign", "grass", "water",
                      "wall", "window"}

    _SIGN_MAP = {
        "sign": "Sign",
        "tv": "TV",
        "bookshelf": "Bookshelf",
        "pc": "PC",
        "snes": "SNES",
        "desk": "Desk",
        "plant": "Plant",
        "bed": "Bed",
    }

    _DEST_BUILDING_MAP = {
        "pokecenter": "Pokecenter",
        "mart": "Mart",
        "gym": "Gym",
        "lab": "Lab",
        "museum": "Museum",
    }

    @staticmethod
    def _warp_label(wy, wx, dest_map, descriptions, mem, row_width):
        """Determine warp label and kind from destination map or block."""
        if dest_map == 0xFF:
            dest_map = mem[0xD365]
        dest_name = MAP_NAMES.get(dest_map)
        if dest_name:
            block_row = wy // 2
            block_col = wx // 2
            addr = ADDR_OVERWORLD_MAP + (block_row + MAP_BORDER) * row_width + (block_col + MAP_BORDER)
            block_id = mem[addr]
            if block_id in descriptions:
                tile_names = {t.lower() for t in descriptions[block_id]}
                if "stairs" in tile_names:
                    return dest_name, "warp"
            return dest_name, "exit"

        block_row = wy // 2
        block_col = wx // 2
        addr = ADDR_OVERWORLD_MAP + (block_row + MAP_BORDER) * row_width + (block_col + MAP_BORDER)
        block_id = mem[addr]

        if block_id in descriptions:
            tiles = descriptions[block_id]
            tile_names = {t.lower() for t in tiles}
            if "stairs" in tile_names:
                return "Stairs", "warp"
            if "doormat" in tile_names:
                return "Exit", "exit"
            if "door" in tile_names:
                building = OverworldScanner._identify_building(
                    tiles, descriptions, mem, row_width, block_row, block_col
                )
                return building, "exit"

        H = mem[ADDR_MAP_HEIGHT]
        if wy >= H * 2 - 2:
            return "Exit", "exit"

        return "Warp", "warp"

    @staticmethod
    def _identify_building(tiles, descriptions, mem, row_width, block_row, block_col):
        """Identify building type from the door's block and its neighbours."""
        bmap = OverworldScanner._BUILDING_MAP
        generic = OverworldScanner._GENERIC_TILES

        for t in tiles:
            name = t.lower()
            if name not in generic and name in bmap:
                return bmap[name]

        for dr, dc in [(-1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1)]:
            nr, nc = block_row + dr, block_col + dc
            if nr < 0 or nc < 0:
                continue
            naddr = ADDR_OVERWORLD_MAP + (nr + MAP_BORDER) * row_width + (nc + MAP_BORDER)
            neighbor_id = mem[naddr]
            if neighbor_id in descriptions:
                for t in descriptions[neighbor_id]:
                    name = t.lower()
                    if name not in generic and name in bmap:
                        return bmap[name]

        return "Door"

    # ------------------------------------------------------------------
    # Block map scanning (tile-based interactables: PC, SNES, etc.)
    # ------------------------------------------------------------------

    def _scan_blocks(self, py, px):
        """Scan the overworld block map for known interactable objects."""
        mem = self._pyboy.memory
        tileset = mem[ADDR_TILESET]
        labels = BLOCK_LABELS.get(tileset, {})
        if not labels:
            return []

        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]
        row_width = W + 2 * MAP_BORDER

        results = []
        for row in range(H):
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                block_id = mem[addr]
                if block_id in labels:
                    label, dy, dx = labels[block_id]
                    tile_ty = row * 2 + dy
                    tile_tx = col * 2 + dx
                    results.append({
                        "label": label,
                        "dir": self._relative_dir(py, px, tile_ty, tile_tx),
                        "ty": tile_ty,
                        "tx": tile_tx,
                        "kind": "sign",
                    })
        return results

    # ------------------------------------------------------------------
    # Sign scanning
    # ------------------------------------------------------------------

    def _scan_signs(self, py, px):
        """Read sign entries from WRAM (coordinate-based interactables)."""
        mem = self._pyboy.memory
        tileset = mem[ADDR_TILESET]
        descriptions = BLOCK_DESCRIPTIONS.get(tileset, {})
        W = mem[ADDR_MAP_WIDTH]
        row_width = W + 2 * MAP_BORDER

        count = mem[ADDR_NUM_SIGNS]
        results = []
        for i in range(count):
            base = ADDR_SIGN_COORDS + i * 2
            sy = mem[base]
            sx = mem[base + 1]
            label = self._sign_label(sy, sx, descriptions, mem, row_width)
            results.append({
                "label": label,
                "dir": self._relative_dir(py, px, sy, sx),
                "ty": sy,
                "tx": sx,
                "kind": "sign",
            })
        return results

    @staticmethod
    def _sign_label(sy, sx, descriptions, mem, row_width):
        """Identify a sign/object from the tile it sits on."""
        block_row = sy // 2
        block_col = sx // 2
        addr = ADDR_OVERWORLD_MAP + (block_row + MAP_BORDER) * row_width + (block_col + MAP_BORDER)
        block_id = mem[addr]
        if block_id not in descriptions:
            return "Sign"
        tiles = descriptions[block_id]
        idx = (sy % 2) * 2 + (sx % 2)
        tile_name = tiles[idx].lower()
        return OverworldScanner._SIGN_MAP.get(tile_name, "Sign")

    # ------------------------------------------------------------------
    # Sprite / NPC scanning
    # ------------------------------------------------------------------

    _SPRITE_COORD_OFFSET = 4

    def _get_hidden_sprites(self):
        """Return set of sprite indices hidden by game-event flags."""
        mem = self._pyboy.memory
        hidden = set()
        addr = ADDR_MISSABLE_LIST
        for _ in range(16):
            sprite_idx = mem[addr]
            if sprite_idx == 0xFF:
                break
            flag_bit = mem[addr + 1]
            byte_idx = flag_bit // 8
            bit_idx = flag_bit % 8
            if mem[ADDR_MISSABLE_FLAGS + byte_idx] & (1 << bit_idx):
                hidden.add(sprite_idx)
            addr += 2
        return hidden

    def _scan_sprites(self, py, px):
        """Read NPC sprites from WRAM."""
        mem = self._pyboy.memory
        count = mem[ADDR_NUM_SPRITES]
        off = self._SPRITE_COORD_OFFSET
        hidden = self._get_hidden_sprites()

        results = []
        for i in range(1, count + 1):
            if i in hidden:
                continue

            base1 = ADDR_SPRITE_DATA + i * 0x10
            pic_id = mem[base1]
            if pic_id == 0 or mem[base1 + 1] == 0:
                continue

            base2 = ADDR_SPRITE_DATA2 + i * 0x10
            sy = mem[base2 + 4] - off
            sx = mem[base2 + 5] - off

            if sy < 0 or sx < 0 or (sy == py and sx == px):
                continue

            label = self._sprite_resolver.resolve_label(pic_id, mem[ADDR_MAP_N], sx)
            results.append({
                "label": label,
                "dir": self._relative_dir(py, px, sy, sx),
                "ty": sy,
                "tx": sx,
                "kind": "sprite",
                "sprite_index": i,
            })
        return results

    # ------------------------------------------------------------------
    # Map connection scanning (adjacent maps via edge walking)
    # ------------------------------------------------------------------

    _CONN_FLAGS = [(0x08, "up"), (0x04, "down"), (0x02, "left"), (0x01, "right")]

    def _scan_connections(self, py, px):
        """Read map connections from the ROM header."""
        header = self._sprite_resolver.find_map_header()
        if header is None:
            return []

        rom = self._rom
        mem = self._pyboy.memory
        conn_flags = rom[header + 9]
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]

        pos = header + 10
        results = []
        for flag, btn in self._CONN_FLAGS:
            if not (conn_flags & flag):
                continue
            dest_map_id = rom[pos]
            pos += 11

            map_name = MAP_NAMES.get(dest_map_id, f"Map {dest_map_id}")

            if btn == "up":
                ey, ex = 0, W
            elif btn == "down":
                ey, ex = H * 2 - 1, W
            elif btn == "left":
                ey, ex = H, 0
            else:
                ey, ex = H, W * 2 - 1

            current_map = mem[ADDR_MAP_N]
            if (current_map, map_name) in _BLOCKED_CONNECTIONS:
                continue

            results.append({
                "label": map_name,
                "dir": self._relative_dir(py, px, ey, ex),
                "ty": ey,
                "tx": ex,
                "kind": "connection",
                "conn_dir": btn,
            })
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _relative_dir(py, px, ty, tx):
        """Return human-readable direction, e.g. '2 south, 1 east'."""
        dy, dx = ty - py, tx - px
        parts = []
        if dy < 0:
            parts.append(f"{-dy} north")
        elif dy > 0:
            parts.append(f"{dy} south")
        if dx < 0:
            parts.append(f"{-dx} west")
        elif dx > 0:
            parts.append(f"{dx} east")
        return ", ".join(parts) if parts else "here"
