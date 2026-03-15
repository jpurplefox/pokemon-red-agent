"""Overworld scanner — reads WRAM to find nearby points of interest (SRP).

Scans warps (stairs/doors), blocks (PC, SNES), signs, and sprites (NPCs)
from Pokemon Red's WRAM structures.  Dependencies injected via constructor (DIP).
"""

from constants import (
    ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_NUM_WARPS, ADDR_WARP_ENTRIES,
    ADDR_NUM_SIGNS, ADDR_SIGN_COORDS,
    ADDR_NUM_SPRITES, ADDR_SPRITE_DATA,
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
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        count = mem[ADDR_NUM_SPRITES]

        player_y_px = mem[ADDR_SPRITE_DATA + 4]
        player_x_px = mem[ADDR_SPRITE_DATA + 6]

        blocked = set()
        for i in range(1, count + 1):
            base = ADDR_SPRITE_DATA + i * 0x10
            if mem[base] == 0:
                continue
            dy = (mem[base + 4] - player_y_px) // 16
            dx = (mem[base + 6] - player_x_px) // 16
            blocked.add((py + dy, px + dx))
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
        if "escalera" in tile_names:
            return "Stairs", "warp"
        if "alfombra" in tile_names:
            return "Exit", "exit"
        return "Warp", "warp"

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
        count = self._pyboy.memory[ADDR_NUM_SIGNS]
        results = []
        for i in range(count):
            base = ADDR_SIGN_COORDS + i * 2
            sy = self._pyboy.memory[base]
            sx = self._pyboy.memory[base + 1]
            results.append({
                "label": "Object",
                "dir": self._relative_dir(py, px, sy, sx),
                "ty": sy,
                "tx": sx,
                "kind": "sign",
            })
        return results

    # ------------------------------------------------------------------
    # Sprite / NPC scanning
    # ------------------------------------------------------------------

    def _scan_sprites(self, py, px):
        """Read NPC sprites from WRAM (people, trainers)."""
        count = self._pyboy.memory[ADDR_NUM_SPRITES]

        # Player sprite reference (sprite 0)
        player_y_px = self._pyboy.memory[ADDR_SPRITE_DATA + 4]
        player_x_px = self._pyboy.memory[ADDR_SPRITE_DATA + 6]

        results = []
        for i in range(1, count + 1):  # skip sprite 0 (player)
            base = ADDR_SPRITE_DATA + i * 0x10
            picture_id = self._pyboy.memory[base]
            if picture_id == 0:
                continue

            sprite_y_px = self._pyboy.memory[base + 4]
            sprite_x_px = self._pyboy.memory[base + 6]

            # Convert pixel delta to map-cell delta (16 px per map cell)
            dy = (sprite_y_px - player_y_px) // 16
            dx = (sprite_x_px - player_x_px) // 16
            if dy == 0 and dx == 0:
                continue

            results.append({
                "label": "Person",
                "dir": self._relative_dir(0, 0, dy, dx),
                "ty": py + dy,
                "tx": px + dx,
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
