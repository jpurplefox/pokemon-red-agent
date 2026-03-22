"""Overworld scanner — reads WRAM to find nearby points of interest (SRP).

Scans warps (stairs/doors), blocks (PC, SNES), signs, and sprites (NPCs)
from Pokemon Red's WRAM structures.  Dependencies injected via constructor (DIP).
"""

from data.constants import (
    ADDR_MAP_N, ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_NUM_WARPS, ADDR_WARP_ENTRIES,
    ADDR_NUM_SIGNS, ADDR_SIGN_COORDS,
    ADDR_NUM_SPRITES, ADDR_SPRITE_DATA, ADDR_SPRITE_DATA2,
    ADDR_MISSABLE_FLAGS, ADDR_MISSABLE_LIST,
    ADDR_TILESET, ADDR_TILESET_BANK, ADDR_TILESET_BLOCKS_PTR,
    ADDR_TILESET_COLL_PTR, ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH,
    ADDR_OVERWORLD_MAP, MAP_BORDER, BLOCK_LABELS, WALKABLE_BLOCKS,
    BLOCK_DESCRIPTIONS, SPRITE_LABELS, MAP_NAMES, ADDR_GRASS_TILE,
)
from adapters.input.pathfinder import find_best_path

# Oak's Lab (map 0x28) starter Poké Balls by X coordinate
# Left-to-right: Charmander, Squirtle, Bulbasaur
_OAK_LAB_STARTERS = {
    6: "Poké Ball (CHARMANDER)",
    7: "Poké Ball (SQUIRTLE)",
    8: "Poké Ball (BULBASAUR)",
}

# Broken warps: (map_id, warp_index) — warps that are reachable but don't work
_BROKEN_WARPS = {
    (0x2F, 0),  # Viridian Forest North Gate — left door to Route 2
    (0x32, 0),  # Viridian Forest South Gate — left door to Viridian Forest
}


class OverworldScanner:
    # Quadrant tile indices within a 4x4 tile block (row-major layout).
    # Each block is 4x4 tiles; each quadrant is the 2x2 sub-area that
    # corresponds to one player step position.
    _QUAD_INDICES = (
        (0, 1, 4, 5),      # TL: rows 0-1, cols 0-1
        (2, 3, 6, 7),      # TR: rows 0-1, cols 2-3
        (8, 9, 12, 13),    # BL: rows 2-3, cols 0-1
        (10, 11, 14, 15),  # BR: rows 2-3, cols 2-3
    )

    # Representative tile index per quadrant — the bottom-left tile of
    # each 2x2 step area (where the player's feet land).  Pokemon Red
    # checks a single tile per step for collision, not all four.
    _QUAD_REP_TILE = (4, 6, 12, 14)

    def __init__(self, pyboy, rom_path=None):
        self._pyboy = pyboy
        self._rom = None
        if rom_path:
            with open(rom_path, 'rb') as f:
                self._rom = f.read()

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
        all_pois.extend(self._scan_signs(py, px))
        all_pois.extend(self._scan_sprites(py, px))
        all_pois.extend(self._scan_connections(py, px))

        # Filter out unreachable POIs
        grid, _, _ = self.get_walkable_grid()
        reachable = []
        for poi in all_pois:
            path, _ = find_best_path(grid, (py, px), poi)
            if path is not None:
                reachable.append(poi)

        # Add a single grass POI if there's tall grass on this map
        grass_poi = self._find_nearest_grass(py, px, grid)
        if grass_poi:
            path, _ = find_best_path(grid, (py, px), grass_poi)
            if path is not None:
                reachable.append(grass_poi)

        return reachable

    # ------------------------------------------------------------------
    # ROM-based tileset data (auto-detect walkability for any tileset)
    # ------------------------------------------------------------------

    def _rom_offset(self, bank, ptr):
        """Convert a ROM bank:address to a file offset."""
        if ptr < 0x4000:
            return ptr  # Bank 0 — always mapped
        return bank * 0x4000 + (ptr - 0x4000)

    def get_collision_tiles(self):
        """Read the set of walkable tile IDs from ROM collision data."""
        if self._rom is None:
            return set()
        mem = self._pyboy.memory
        bank = mem[ADDR_TILESET_BANK]
        ptr = mem[ADDR_TILESET_COLL_PTR] | (mem[ADDR_TILESET_COLL_PTR + 1] << 8)
        offset = self._rom_offset(bank, ptr)
        tiles = set()
        while offset < len(self._rom) and self._rom[offset] != 0xFF:
            tiles.add(self._rom[offset])
            offset += 1
        return tiles

    def get_block_tiles(self, block_id):
        """Read the 16 tile IDs (4×4) for a block from ROM."""
        if self._rom is None:
            return None
        mem = self._pyboy.memory
        bank = mem[ADDR_TILESET_BANK]
        ptr = mem[ADDR_TILESET_BLOCKS_PTR] | (mem[ADDR_TILESET_BLOCKS_PTR + 1] << 8)
        offset = self._rom_offset(bank, ptr) + block_id * 16
        if offset + 16 > len(self._rom):
            return None
        return self._rom[offset:offset + 16]

    def block_walkability(self, block_tiles, collision_tiles):
        """Return (TL, TR, BL, BR) walkability from block tile data.

        Checks the representative tile per quadrant (bottom-left of each
        2x2 step area, where the player's feet land).  This matches how
        the Pokemon Red engine performs collision detection.
        """
        return tuple(
            block_tiles[rep] in collision_tiles
            for rep in self._QUAD_REP_TILE
        )

    # ------------------------------------------------------------------
    # ROM-based sprite picture IDs (find header by WRAM pattern match)
    # ------------------------------------------------------------------

    # WRAM addresses that mirror the first 9 bytes of the map header:
    # tileset(1) height(1) width(1) map_ptr(2) text_ptr(2) script_ptr(2)
    _HEADER_WRAM_START = 0xD367  # wCurMapTileset
    _HEADER_WRAM_LEN = 9        # 9 bytes: tileset..script_ptr

    def _find_map_header(self):
        """Find the current map's header offset in ROM.

        Searches the ROM for the 9-byte pattern that WRAM mirrors
        (tileset, height, width, map_ptr, text_ptr, script_ptr).
        Returns flat ROM offset, or None.
        """
        if self._rom is None:
            return None
        mem = self._pyboy.memory
        pattern = bytes(
            mem[self._HEADER_WRAM_START + i]
            for i in range(self._HEADER_WRAM_LEN)
        )
        offset = self._rom.find(pattern)
        return offset if offset != -1 else None

    def get_sprite_pic_ids(self):
        """Read original sprite picture IDs from ROM map object data.

        Finds map header by matching WRAM values, then follows the
        object data pointer to read sprite picture IDs.
        Returns list of picture IDs (one per sprite), or empty list.
        """
        header = self._find_map_header()
        if header is None:
            return []
        rom = self._rom
        bank = header // 0x4000

        # Parse connections to find object data pointer
        # Header byte 9 = connection flags (N/S/W/E), each adds 11 bytes
        conn_flags = rom[header + 9]
        num_conn = bin(conn_flags).count('1')
        obj_ptr_addr = header + 10 + num_conn * 11
        obj_ptr = rom[obj_ptr_addr] | (rom[obj_ptr_addr + 1] << 8)
        obj = self._rom_offset(bank, obj_ptr)

        # Parse object data: border(1) warps signs sprites
        pos = obj + 1  # skip border block
        num_warps = rom[pos]; pos += 1
        pos += num_warps * 4  # skip warp entries

        num_signs = rom[pos]; pos += 1
        pos += num_signs * 3  # skip sign entries

        num_sprites = rom[pos]; pos += 1
        pic_ids = []
        for _ in range(num_sprites):
            pic_ids.append(rom[pos])
            # Sprite entry: pic(1) y(1) x(1) movement(1) range/dir(1) text_id(1)
            text_id = rom[pos + 5]
            pos += 6
            if text_id & 0x40:  # trainer: +2 bytes (class, set)
                pos += 2
            elif text_id & 0x80:  # item: +1 byte (item ID)
                pos += 1
        return pic_ids

    # ------------------------------------------------------------------
    # Walkability grid (for A* pathfinding)
    # ------------------------------------------------------------------

    def get_walkable_grid(self):
        """Build a tile-level walkability grid from the block map.

        Uses ROM data (collision tiles + block definitions) when available,
        falls back to manual WALKABLE_BLOCKS otherwise.
        Returns (grid, h_tiles, w_tiles) where grid[ty][tx] is True
        if the tile is walkable.
        """
        mem = self._pyboy.memory
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]
        row_width = W + 2 * MAP_BORDER

        h_tiles = H * 2
        w_tiles = W * 2
        grid = [[False] * w_tiles for _ in range(h_tiles)]

        # Try ROM auto-detection first
        coll = self.get_collision_tiles()
        use_rom = bool(coll)

        # Fallback: manual data
        if not use_rom:
            walkable = WALKABLE_BLOCKS.get(mem[ADDR_TILESET], {})

        for row in range(H):
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                block_id = mem[addr]

                if use_rom:
                    bt = self.get_block_tiles(block_id)
                    if bt is None:
                        continue
                    tl, tr, bl, br = self.block_walkability(bt, coll)
                else:
                    if block_id not in walkable:
                        continue
                    tl, tr, bl, br = walkable[block_id]

                ty = row * 2
                tx = col * 2
                grid[ty][tx] = tl
                grid[ty][tx + 1] = tr
                grid[ty + 1][tx] = bl
                grid[ty + 1][tx + 1] = br

        # Player's current tile is always walkable (so A* can start)
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        if 0 <= py < h_tiles and 0 <= px < w_tiles:
            grid[py][px] = True

        return grid, h_tiles, w_tiles

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

            label = SPRITE_LABELS.get(pic_id, "Person")
            # Override Poké Ball labels in Oak's Lab with starter names
            if label == "Poké Ball" and mem[ADDR_MAP_N] == 0x28:
                label = _OAK_LAB_STARTERS.get(sx, label)
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
        header = self._find_map_header()
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

            # Place POI at the center of the corresponding edge
            if btn == "up":
                ey, ex = 0, W - 1
            elif btn == "down":
                ey, ex = H * 2 - 1, W - 1
            elif btn == "left":
                ey, ex = H - 1, 0
            else:  # right
                ey, ex = H - 1, W * 2 - 1

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
