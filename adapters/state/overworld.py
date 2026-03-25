"""Overworld scanner — reads WRAM to find nearby points of interest.

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


class OverworldScanner:
    def __init__(self, pyboy, rom_path=None):
        self._pyboy = pyboy
        self._rom = None
        if rom_path:
            with open(rom_path, 'rb') as f:
                self._rom = f.read()
        self._walkability = WalkabilityGrid(pyboy, self._rom)
        self._sprite_resolver = SpriteResolver(pyboy, self._rom)

    def get_pois(self):
        """Return all nearby reachable points of interest as a list of dicts.

        Each dict: {"label": str, "dir": str, "ty": int, "tx": int, "kind": str}
        Unreachable POIs (no path via A*) are excluded.
        """
        py = self._pyboy.memory[ADDR_Y_COORD]
        px = self._pyboy.memory[ADDR_X_COORD]

        all_pois = []
        all_pois.extend(self._scan_warps(py, px))
        all_pois.extend(self._scan_blocks(py, px))
        # Fixed POIs for maps with non-detectable interactables
        map_id = self._pyboy.memory[ADDR_MAP_N]
        for fp in _FIXED_POIS.get(map_id, []):
            poi = dict(fp)
            poi["dir"] = self._relative_dir(py, px, poi["ty"], poi["tx"])
            all_pois.append(poi)
        all_pois.extend(self._scan_sprites(py, px))
        all_pois.extend(self._scan_connections(py, px))

        # Deduplicate adjacent warps with the same label (keep closest)
        all_pois = dedup_warps(all_pois, py, px)

        # Disambiguate duplicate labels by compass direction
        all_pois = disambiguate_labels(all_pois, py, px)

        # Collect warp tiles to avoid walking through them accidentally
        warp_tiles = {(p["ty"], p["tx"]) for p in all_pois if p["kind"] == "warp"}

        # Filter out unreachable POIs
        grid, _, _, ledges = self.get_walkable_grid()
        npc_blocked = self.get_npc_tiles()
        reachable = []
        for poi in all_pois:
            # Exclude this POI's own warp from the avoid set (it's the goal)
            avoid = warp_tiles - {(poi["ty"], poi["tx"])}
            path, _ = find_best_path(grid, (py, px), poi, blocked=npc_blocked,
                                     ledges=ledges, warps=avoid)
            if path is not None:
                reachable.append(poi)
            else:
                pass

        # Add a single grass POI if there's tall grass on this map
        # Skip Pallet Town — no wild Pokémon spawn there
        current_map = MAP_NAMES.get(self._pyboy.memory[ADDR_MAP_N], "")
        grass_poi = self._find_nearest_grass(py, px, grid) if current_map != "Pallet Town" else None
        if grass_poi:
            path, _ = find_best_path(grid, (py, px), grass_poi, blocked=npc_blocked,
                                     ledges=ledges, warps=warp_tiles)
            if path is not None:
                reachable.append(grass_poi)

        return reachable

    # ------------------------------------------------------------------
    # Delegated methods (kept for backward compatibility)
    # ------------------------------------------------------------------

    # Expose WalkabilityGrid constants for backward compatibility
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
    # Grass scanning
    # ------------------------------------------------------------------

    def _find_nearest_grass(self, py, px, grid):
        """Find the nearest tall grass tile and return a single grass POI.

        Uses wGrassTile (0xD535) to identify which tile triggers encounters,
        then scans block data to find tiles matching that ID.
        Returns a POI dict or None if no grass on this map.
        """
        mem = self._pyboy.memory
        grass_tile = mem[ADDR_GRASS_TILE]
        if grass_tile == 0:
            return None

        if self._rom is None:
            return None

        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]
        row_width = W + 2 * MAP_BORDER

        # Scan all blocks for grass tiles
        grass_tiles = []
        for row in range(H):
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                block_id = mem[addr]
                bt = self.get_block_tiles(block_id)
                if bt is None:
                    continue
                # Each block has 4 tiles: TL, TR, BL, BR
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

        # Find the nearest walkable grass tile
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

        dy = best[0] - py
        dx = best[1] - px
        parts = []
        if dy < 0:
            parts.append(f"{-dy} north")
        elif dy > 0:
            parts.append(f"{dy} south")
        if dx < 0:
            parts.append(f"{-dx} west")
        elif dx > 0:
            parts.append(f"{dx} east")
        dir_str = ", ".join(parts) if parts else "here"

        return {
            "kind": "grass",
            "label": "Wild Pokémon (tall grass)",
            "ty": best[0],
            "tx": best[1],
            "dir": dir_str,
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

    # Tile descriptions → building label.
    # Generic tiles (floor, door, fence, etc.) are skipped when identifying.
    _BUILDING_MAP = {
        "house": "House",
        "lab": "Lab",
    }
    _GENERIC_TILES = {"floor", "door", "fence", "sign", "grass", "water",
                      "wall", "window"}

    # Tile descriptions → sign/object label.
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

    # Keywords in MAP_NAMES that identify building types for icons.
    _DEST_BUILDING_MAP = {
        "pokecenter": "Pokecenter",
        "mart": "Mart",
        "gym": "Gym",
        "lab": "Lab",
        "museum": "Museum",
    }

    @staticmethod
    def _warp_label(wy, wx, dest_map, descriptions, mem, row_width):
        """Determine warp label and kind from destination map or block.

        Priority:
        1. Destination map name from MAP_NAMES (most reliable).
        2. BLOCK_DESCRIPTIONS lookup (stairs / doormat / door).
        3. Position heuristic: bottom-edge warps are exits.
        """
        # Use destination map name when available
        # dest_map 0xFF means "return to last map" — read wLastMap
        if dest_map == 0xFF:
            dest_map = mem[0xD365]
        dest_name = MAP_NAMES.get(dest_map)
        if dest_name:
            # Determine kind: interior warps (stairs) vs building entries
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

        # Auto-detect: bottom-edge warps are building exits
        H = mem[ADDR_MAP_HEIGHT]
        if wy >= H * 2 - 2:
            return "Exit", "exit"

        return "Warp", "warp"

    @staticmethod
    def _identify_building(tiles, descriptions, mem, row_width, block_row, block_col):
        """Identify building type from the door's block and its neighbours."""
        bmap = OverworldScanner._BUILDING_MAP
        generic = OverworldScanner._GENERIC_TILES

        # 1. Check the door's own block (non-generic tiles)
        for t in tiles:
            name = t.lower()
            if name not in generic and name in bmap:
                return bmap[name]

        # 2. Check neighbouring blocks (above, left, right, diagonals above)
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
                    # Exact tile of the interactable within the 2x2 block
                    tile_ty = row * 2 + dy
                    tile_tx = col * 2 + dx
                    results.append({
                        "label": label,
                        "dir": self._relative_dir(py, px, tile_ty, tile_tx),
                        "ty": tile_ty,
                        "tx": tile_tx,
                        "kind": "sign",  # single-tile target
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
        # Which tile within the 2x2 block: TL=0, TR=1, BL=2, BR=3
        idx = (sy % 2) * 2 + (sx % 2)
        tile_name = tiles[idx].lower()
        return OverworldScanner._SIGN_MAP.get(tile_name, "Sign")

    # ------------------------------------------------------------------
    # Sprite / NPC scanning
    # ------------------------------------------------------------------

    # Sprite map coordinates in wSpriteStateData2 are stored with a +4
    # offset (pokered map object format: Y+4, X+4 for scroll border).
    _SPRITE_COORD_OFFSET = 4

    def _get_hidden_sprites(self):
        """Return set of sprite indices hidden by game-event flags.

        Reads wMissableObjectList ($D5CE): pairs of (sprite_index, flag_bit),
        terminated by $FF.  Then checks wMissableObjectFlags ($D5A6) bit array:
        if the bit is set the sprite is currently hidden.
        """
        mem = self._pyboy.memory
        hidden = set()
        addr = ADDR_MISSABLE_LIST
        for _ in range(16):  # max 16 sprites per map
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
        """Read NPC sprites from WRAM (people, trainers, items, objects).

        Uses wSpriteStateData2 ($C200) for map coordinates instead of
        screen pixel positions ($C100), which are unreliable for off-screen sprites.
        Picture ID from wSpriteStateData1 byte 0 determines the sprite label.
        Sprites hidden by game-event flags (missable objects) are excluded.
        """
        mem = self._pyboy.memory
        count = mem[ADDR_NUM_SPRITES]
        off = self._SPRITE_COORD_OFFSET
        hidden = self._get_hidden_sprites()

        results = []
        for i in range(1, count + 1):  # skip sprite 0 (player)
            if i in hidden:
                continue  # hidden by game-event flag

            # Picture ID and movement status from wSpriteStateData1
            base1 = ADDR_SPRITE_DATA + i * 0x10
            pic_id = mem[base1]
            if pic_id == 0 or mem[base1 + 1] == 0:
                continue  # empty slot or uninitialized

            # Map coordinates from wSpriteStateData2 (+4 = Y, +5 = X)
            # Subtract offset to get tile coordinates matching wYCoord/wXCoord
            base2 = ADDR_SPRITE_DATA2 + i * 0x10
            sy = mem[base2 + 4] - off
            sx = mem[base2 + 5] - off

            # Skip uninitialized or same-as-player sprites
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

    # Connection flag bits in ROM header byte 9 (order matters for parsing)
    _CONN_FLAGS = [(0x08, "up"), (0x04, "down"), (0x02, "left"), (0x01, "right")]

    def _scan_connections(self, py, px):
        """Read map connections from the ROM header.

        Returns POIs for adjacent maps reachable by walking off the edge.
        Each connection has 11 bytes in the ROM: dest_map_id(1) + strip data(10).
        """
        header = self._sprite_resolver.find_map_header()
        if header is None:
            return []

        rom = self._rom
        mem = self._pyboy.memory
        conn_flags = rom[header + 9]
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]

        pos = header + 10  # connection data starts after the 10-byte header
        results = []
        for flag, btn in self._CONN_FLAGS:
            if not (conn_flags & flag):
                continue
            dest_map_id = rom[pos]
            pos += 11  # skip remaining 10 bytes of this connection

            map_name = MAP_NAMES.get(dest_map_id, f"Map {dest_map_id}")

            # Place POI at the center of the corresponding edge (tile coords)
            if btn == "up":
                ey, ex = 0, W
            elif btn == "down":
                ey, ex = H * 2 - 1, W
            elif btn == "left":
                ey, ex = H, 0
            else:  # right
                ey, ex = H, W * 2 - 1

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
