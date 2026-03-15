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
    ADDR_OVERWORLD_MAP, MAP_BORDER, BLOCK_LABELS,
)


class OverworldScanner:
    def __init__(self, pyboy):
        self._pyboy = pyboy

    def get_pois(self):
        """Return all nearby points of interest as a list of dicts.

        Each dict: {"label": str, "dir": str}
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
    # Warp scanning
    # ------------------------------------------------------------------

    def _scan_warps(self, py, px):
        """Read warp entries from WRAM (stairs, doors, map exits)."""
        count = self._pyboy.memory[ADDR_NUM_WARPS]
        results = []
        for i in range(count):
            base = ADDR_WARP_ENTRIES + i * 4
            wy = self._pyboy.memory[base]
            wx = self._pyboy.memory[base + 1]
            results.append({
                "label": "Stairs",
                "dir": self._relative_dir(py, px, wy, wx),
            })
        return results

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
                    # Block position in tile coords (top-left of 2x2 block)
                    block_ty = row * 2
                    block_tx = col * 2
                    results.append({
                        "label": labels[block_id],
                        "dir": self._relative_dir(py, px, block_ty, block_tx),
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
