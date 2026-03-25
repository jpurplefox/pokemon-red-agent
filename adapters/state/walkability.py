"""Walkability grid builder (SRP).

Reads ROM collision data and block definitions to build a tile-level
walkability grid for A* pathfinding, including ledge detection.
"""

from data.constants import (
    ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_TILESET, ADDR_TILESET_BANK, ADDR_TILESET_BLOCKS_PTR,
    ADDR_TILESET_COLL_PTR, ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH,
    ADDR_OVERWORLD_MAP, MAP_BORDER, WALKABLE_BLOCKS,
)


class WalkabilityGrid:
    """Builds tile-level walkability grids from ROM data."""

    # Quadrant tile indices within a 4x4 tile block (row-major layout).
    _QUAD_INDICES = (
        (0, 1, 4, 5),      # TL
        (2, 3, 6, 7),      # TR
        (8, 9, 12, 13),     # BL
        (10, 11, 14, 15),   # BR
    )

    # Representative tile per quadrant (where the player's feet land).
    _QUAD_REP_TILE = (4, 6, 12, 14)

    def __init__(self, pyboy, rom=None):
        self._pyboy = pyboy
        self._rom = rom

    # ------------------------------------------------------------------
    # ROM data access
    # ------------------------------------------------------------------

    def _rom_offset(self, bank, ptr):
        """Convert a ROM bank:address to a file offset."""
        if ptr < 0x4000:
            return ptr
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
        """Return (TL, TR, BL, BR) walkability from block tile data."""
        return tuple(
            block_tiles[rep] in collision_tiles
            for rep in self._QUAD_REP_TILE
        )

    # ------------------------------------------------------------------
    # Grid building
    # ------------------------------------------------------------------

    def get_grid(self):
        """Build a tile-level walkability grid from the block map.

        Returns (grid, h_tiles, w_tiles, ledges).
        """
        mem = self._pyboy.memory
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]
        row_width = W + 2 * MAP_BORDER

        h_tiles = H * 2
        w_tiles = W * 2
        grid = [[False] * w_tiles for _ in range(h_tiles)]
        ledges = set()

        # Try ROM auto-detection first, but manual overrides take priority
        coll = self.get_collision_tiles()
        use_rom = bool(coll)
        manual = WALKABLE_BLOCKS.get(mem[ADDR_TILESET], {})

        for row in range(H):
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                block_id = mem[addr]

                # Manual overrides always take priority
                if block_id in manual:
                    tl, tr, bl, br = manual[block_id]
                elif use_rom:
                    bt = self.get_block_tiles(block_id)
                    if bt is None:
                        continue
                    tl, tr, bl, br = self.block_walkability(bt, coll)
                else:
                    continue

                ty = row * 2
                tx = col * 2
                grid[ty][tx] = tl
                grid[ty][tx + 1] = tr
                grid[ty + 1][tx] = bl
                grid[ty + 1][tx + 1] = br

        # Player's current tile is always walkable
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        if 0 <= py < h_tiles and 0 <= px < w_tiles:
            grid[py][px] = True

        # Detect ledge tiles (tileset 0 only)
        tileset = mem[ADDR_TILESET]
        if tileset == 0 and use_rom:
            self._detect_ledges(grid, ledges, mem, W, H, row_width, coll,
                                h_tiles, w_tiles)

        return grid, h_tiles, w_tiles, ledges

    def _detect_ledges(self, grid, ledges, mem, W, H, row_width, coll,
                       h_tiles, w_tiles):
        """Detect one-way ledge tiles from walkability patterns."""
        manual = WALKABLE_BLOCKS.get(mem[ADDR_TILESET], {})
        for row in range(H):
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                block_id = mem[addr]
                # Skip blocks with manual overrides — they are not ledges
                if block_id in manual:
                    continue
                bt = self.get_block_tiles(block_id)
                if bt is None:
                    continue
                tl, tr, bl, br = self.block_walkability(bt, coll)
                ty = row * 2
                tx = col * 2
                # Pattern [✓✓/✗✗] or [✓✗/✗✗] or [✗✓/✗✗] = ledge down
                if (tl or tr) and not bl and not br:
                    for ly, lx in [(ty + 1, tx), (ty + 1, tx + 1)]:
                        if 0 <= ly < h_tiles and 0 <= lx < w_tiles:
                            ledges.add((ly, lx, "down"))
                            grid[ly][lx] = True
