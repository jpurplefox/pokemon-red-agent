"""Overworld scanner — reads WRAM to find nearby points of interest (SRP).

Scans warps (stairs/doors), blocks (PC, SNES), signs, and sprites (NPCs)
from Pokemon Red's WRAM structures.  Dependencies injected via constructor (DIP).
"""

from constants import (
    ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_NUM_WARPS, ADDR_WARP_ENTRIES,
    ADDR_NUM_SIGNS, ADDR_SIGN_COORDS,
    ADDR_NUM_SPRITES, ADDR_SPRITE_DATA, ADDR_SPRITE_DATA2,
    ADDR_TILESET, ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH,
    ADDR_OVERWORLD_MAP, MAP_BORDER, BLOCK_LABELS, WALKABLE_BLOCKS,
    BLOCK_DESCRIPTIONS,
)


class OverworldScanner:
    def __init__(self, pyboy):
        self._pyboy = pyboy

    def get_pois(self):
        """Return all nearby points of interest as a list of dicts.

        Each dict: {"label": str, "dir": str, "ty": int, "tx": int, "kind": str}
        """
        py = self._pyboy.memory[ADDR_Y_COORD]
        px = self._pyboy.memory[ADDR_X_COORD]

        pois = []
        pois.extend(self._scan_warps(py, px))
        pois.extend(self._scan_blocks(py, px))
        pois.extend(self._scan_signs(py, px))
        pois.extend(self._scan_sprites(py, px))
        return pois

    # ------------------------------------------------------------------
    # Walkability grid (for A* pathfinding)
    # ------------------------------------------------------------------

    def get_walkable_grid(self):
        """Build a tile-level walkability grid from the block map.

        Returns (grid, h_tiles, w_tiles) where grid[ty][tx] is True
        if the tile is walkable.
        """
        mem = self._pyboy.memory
        tileset = mem[ADDR_TILESET]
        walkable = WALKABLE_BLOCKS.get(tileset, {})
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]
        row_width = W + 2 * MAP_BORDER

        h_tiles = H * 2
        w_tiles = W * 2
        grid = [[False] * w_tiles for _ in range(h_tiles)]

        for row in range(H):
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                block_id = mem[addr]
                if block_id in walkable:
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

        blocked = set()
        for i in range(1, count + 1):
            if mem[ADDR_SPRITE_DATA + i * 0x10] == 0:
                continue
            base2 = ADDR_SPRITE_DATA2 + i * 0x10
            sy = mem[base2 + 4] - off
            sx = mem[base2 + 5] - off
            if sy >= 0 and sx >= 0:
                blocked.add((sy, sx))
        return blocked

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

        results = []
        for i in range(count):
            base = ADDR_WARP_ENTRIES + i * 4
            wy = mem[base]
            wx = mem[base + 1]
            label, kind = self._warp_label(wy, wx, descriptions, mem, row_width)
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

    @staticmethod
    def _warp_label(wy, wx, descriptions, mem, row_width):
        """Determine warp label and kind from the block it sits on."""
        block_row = wy // 2
        block_col = wx // 2
        addr = ADDR_OVERWORLD_MAP + (block_row + MAP_BORDER) * row_width + (block_col + MAP_BORDER)
        block_id = mem[addr]
        if block_id not in descriptions:
            return "Warp", "warp"
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
            return "Object"
        tiles = descriptions[block_id]
        # Which tile within the 2x2 block: TL=0, TR=1, BL=2, BR=3
        idx = (sy % 2) * 2 + (sx % 2)
        tile_name = tiles[idx].lower()
        return OverworldScanner._SIGN_MAP.get(tile_name, "Object")

    # ------------------------------------------------------------------
    # Sprite / NPC scanning
    # ------------------------------------------------------------------

    # Sprite map coordinates in wSpriteStateData2 are stored with a +4
    # offset (pokered map object format: Y+4, X+4 for scroll border).
    _SPRITE_COORD_OFFSET = 4

    def _scan_sprites(self, py, px):
        """Read NPC sprites from WRAM (people, trainers).

        Uses wSpriteStateData2 ($C200) for map coordinates instead of
        screen pixel positions ($C100), which are unreliable for off-screen sprites.
        """
        mem = self._pyboy.memory
        count = mem[ADDR_NUM_SPRITES]
        off = self._SPRITE_COORD_OFFSET

        results = []
        for i in range(1, count + 1):  # skip sprite 0 (player)
            # Check picture ID from wSpriteStateData1 (0 = empty slot)
            if mem[ADDR_SPRITE_DATA + i * 0x10] == 0:
                continue

            # Map coordinates from wSpriteStateData2 (+4 = Y, +5 = X)
            # Subtract offset to get tile coordinates matching wYCoord/wXCoord
            base2 = ADDR_SPRITE_DATA2 + i * 0x10
            sy = mem[base2 + 4] - off
            sx = mem[base2 + 5] - off

            # Skip uninitialized or same-as-player sprites
            if sy < 0 or sx < 0 or (sy == py and sx == px):
                continue

            results.append({
                "label": "Person",
                "dir": self._relative_dir(py, px, sy, sx),
                "ty": sy,
                "tx": sx,
                "kind": "sprite",
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
