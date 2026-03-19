from data.constants import ADDR_TILEMAP, POKEMON_CHARMAP


class ScreenReader:
    def __init__(self, pyboy):
        self._pyboy = pyboy

    def decode_tiles(self, row, col, length=18):
        """Read tiles from wTileMap and decode as Pokemon text."""
        text = ""
        for i in range(length):
            tile = self._pyboy.memory[ADDR_TILEMAP + row * 20 + col + i]
            if tile == 0x50:
                break
            text += POKEMON_CHARMAP.get(tile, "")
        return text.strip()

    def read_text_box(self):
        """Read text from the text box area (bottom of screen, rows 12-17)."""
        lines = []
        for row in range(12, 18):
            line = self.decode_tiles(row, 1, 18)
            if line:
                lines.append(line)
        return " ".join(lines)
