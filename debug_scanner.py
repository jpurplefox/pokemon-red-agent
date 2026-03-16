"""Debug memory/ROM inspector (SRP).

Dumps block maps, walkability data, sprite information, and missable
object flags for development and troubleshooting.
"""

from constants import (
    ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH, ADDR_OVERWORLD_MAP,
    ADDR_TILESET, MAP_BORDER,
    ADDR_NUM_SPRITES, ADDR_SPRITE_DATA, ADDR_SPRITE_DATA2,
    SPRITE_LABELS,
)


class DebugScanner:
    def __init__(self, pyboy, scanner):
        self._pyboy = pyboy
        self._scanner = scanner

    def dump(self):
        """Print the full debug scan: block map, walkability, sprites."""
        mem = self._pyboy.memory
        py = mem[ADDR_Y_COORD]
        px = mem[ADDR_X_COORD]
        W = mem[ADDR_MAP_WIDTH]
        H = mem[ADDR_MAP_HEIGHT]

        self._dump_block_map(mem, py, px, W, H)
        self._dump_walkability(mem, W, H)
        self._dump_sprites(mem)
        self._dump_missable_flags(mem)

    def _dump_block_map(self, mem, py, px, W, H):
        """Print the block map with player position highlighted."""
        player_block_y = py // 2
        player_block_x = px // 2
        row_width = W + 2 * MAP_BORDER
        tileset = mem[ADDR_TILESET]

        print(f"\nTileset {tileset} | Map {W}x{H} blocks | Player tile ({py},{px})")
        header = "     " + "".join(f" {c:<3}" for c in range(W))
        print(header)

        self._seen_blocks = set()
        for row in range(H):
            cells = []
            for col in range(W):
                addr = ADDR_OVERWORLD_MAP + (row + MAP_BORDER) * row_width + (col + MAP_BORDER)
                bid = mem[addr]
                self._seen_blocks.add(bid)
                if row == player_block_y and col == player_block_x:
                    cells.append(f"[{bid:02X}]")
                else:
                    cells.append(f" {bid:02X} ")
            print(f"  {row}: " + "".join(cells))

    def _dump_walkability(self, mem, W, H):
        """Print collision tiles and per-block walkability from ROM."""
        coll = self._scanner.get_collision_tiles()
        if not coll:
            print("\n(No ROM data -- cannot auto-detect walkability)")
            return

        print(f"\nCollision tiles: {', '.join(f'${t:02X}' for t in sorted(coll))}")
        print("\nBlocks:")
        for bid in sorted(self._seen_blocks):
            bt = self._scanner.get_block_tiles(bid)
            if bt is None:
                print(f"  {bid:02X}: ???")
                continue
            tl, tr, bl, br = self._scanner.block_walkability(bt, coll)
            w = lambda v: '\u2713' if v else '\u2717'
            print(f"  {bid:02X}: [{w(tl)}{w(tr)}/{w(bl)}{w(br)}]")

    def _dump_sprites(self, mem):
        """Print raw sprite data for debugging."""
        count = mem[ADDR_NUM_SPRITES]
        print(f"\nSprites ({count}):")
        for i in range(1, count + 1):
            base1 = ADDR_SPRITE_DATA + i * 0x10
            base2 = ADDR_SPRITE_DATA2 + i * 0x10
            pic_id = mem[base1]
            label = SPRITE_LABELS.get(pic_id, "Person")
            sy = mem[base2 + 4] - 4
            sx = mem[base2 + 5] - 4
            d1 = " ".join(f"{mem[base1+b]:02X}" for b in range(16))
            print(f"  #{i}: ({label}) pos=({sy},{sx})")
            print(f"       d1: {d1}")

    def _dump_missable_flags(self, mem):
        """Print missable object flag candidates for debugging."""
        print("\nMissable flags hunt:")
        for label, addr in [("$D5A6", 0xD5A6), ("$D728", 0xD728),
                            ("$D747", 0xD747)]:
            data = " ".join(f"{mem[addr+b]:02X}" for b in range(8))
            print(f"  {label}: {data}")
        print("  wMissableObjectList candidates:")
        for label, addr in [("$D5CE", 0xD5CE), ("$D5B3", 0xD5B3)]:
            data = " ".join(f"{mem[addr+b]:02X}" for b in range(24))
            print(f"    {label}: {data}")
