"""Debug memory/ROM inspector (SRP).

Dumps block maps, walkability data, sprite information, and missable
object flags for development and troubleshooting.
"""

from data.constants import (
    ADDR_Y_COORD, ADDR_X_COORD,
    ADDR_MAP_HEIGHT, ADDR_MAP_WIDTH, ADDR_OVERWORLD_MAP,
    ADDR_TILESET, ADDR_TILESET_BANK, ADDR_TILESET_COLL_PTR,
    ADDR_TILESET_BLOCKS_PTR, MAP_BORDER, WALKABLE_BLOCKS,
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
        """Print collision tiles, per-block walkability, and ROM vs manual comparison."""
        tileset = mem[ADDR_TILESET]
        bank = mem[ADDR_TILESET_BANK]
        coll_ptr = mem[ADDR_TILESET_COLL_PTR] | (mem[ADDR_TILESET_COLL_PTR + 1] << 8)
        blocks_ptr = mem[ADDR_TILESET_BLOCKS_PTR] | (mem[ADDR_TILESET_BLOCKS_PTR + 1] << 8)

        print(f"\nTileset {tileset} | Bank ${bank:02X} | CollPtr ${coll_ptr:04X} | BlocksPtr ${blocks_ptr:04X}")

        coll = self._scanner.get_collision_tiles()
        if not coll:
            print("(No ROM data -- cannot auto-detect walkability)")
            return

        print(f"Collision tiles ({len(coll)}): {', '.join(f'${t:02X}' for t in sorted(coll))}")

        manual = WALKABLE_BLOCKS.get(tileset, {})
        w = lambda v: '\u2713' if v else '\u2717'

        print("\nBlocks (ROM vs Manual):")
        mismatches = []
        for bid in sorted(self._seen_blocks):
            bt = self._scanner.get_block_tiles(bid)
            if bt is None:
                print(f"  {bid:02X}: ??? (no ROM block data)")
                continue
            rom_walk = self._scanner.block_walkability(bt, coll)
            rom_str = f"[{w(rom_walk[0])}{w(rom_walk[1])}/{w(rom_walk[2])}{w(rom_walk[3])}]"

            if bid in manual:
                man_walk = manual[bid]
                man_str = f"[{w(man_walk[0])}{w(man_walk[1])}/{w(man_walk[2])}{w(man_walk[3])}]"
                match = "==" if rom_walk == man_walk else "!!"
                print(f"  {bid:02X}: ROM {rom_str}  Manual {man_str}  {match}")
                if rom_walk != man_walk:
                    mismatches.append((bid, bt, rom_walk, man_walk))
            else:
                any_walkable = any(rom_walk)
                flag = " <-- ROM says walkable, no manual entry" if any_walkable else ""
                print(f"  {bid:02X}: ROM {rom_str}  Manual (none){flag}")

        if mismatches:
            print("\nMISMATCH DETAILS:")
            for bid, bt, rom_walk, man_walk in mismatches:
                tiles_hex = " ".join(f"${t:02X}" for t in bt)
                print(f"  Block ${bid:02X} tiles: {tiles_hex}")
                for qi, (label, indices) in enumerate(
                    zip(["TL", "TR", "BL", "BR"],
                        self._scanner._QUAD_INDICES)):
                    rep = self._scanner._QUAD_REP_TILE[qi]
                    rep_tile = bt[rep]
                    rep_walk = rep_tile in coll
                    quad_tiles = [bt[i] for i in indices]
                    in_coll = [t in coll for t in quad_tiles]
                    quad_hex = " ".join(f"${t:02X}({'W' if c else 'X'})"
                                       for t, c in zip(quad_tiles, in_coll))
                    rom_v = rom_walk[qi]
                    man_v = man_walk[qi]
                    flag = " <-- MISMATCH" if rom_v != man_v else ""
                    print(f"    {label}: rep[{rep}]=${rep_tile:02X}({'W' if rep_walk else 'X'}) "
                          f"all={quad_hex} → ROM={w(rom_v)} Manual={w(man_v)}{flag}")

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
