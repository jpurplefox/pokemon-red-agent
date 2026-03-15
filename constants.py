# Pokemon Red WRAM addresses (pret/pokered disassembly)
ADDR_MAP_N = 0xD35E            # wCurMap: 0 during intro, non-zero in overworld
ADDR_MENU_Y = 0xCC24           # wTopMenuItemY: Y position of first menu item
ADDR_MENU_X = 0xCC25           # wTopMenuItemX: X position of first menu item
ADDR_CURRENT_MENU = 0xCC26     # wCurrentMenuItem: selected item (0 = first)
ADDR_MAX_MENU = 0xCC28         # wMaxMenuItem: index of last item

ADDR_TILEMAP = 0xC3A0          # wTileMap: WRAM copy of screen (20 tiles per row)

# Player position
ADDR_Y_COORD = 0xD361          # wYCoord: player Y on current map
ADDR_X_COORD = 0xD362          # wXCoord: player X on current map

# Warp data (stairs, doors, map transitions)
ADDR_NUM_WARPS = 0xD3AE        # wNumberOfWarps: count of warps on map
ADDR_WARP_ENTRIES = 0xD3AF     # wWarpEntries: 4 bytes each (Y, X, warpTo, destMap)

# Sign data (interactable objects: TV, PC, bookshelf, etc.)
ADDR_NUM_SIGNS = 0xD4B0        # wNumSigns: count of signs on map
ADDR_SIGN_COORDS = 0xD4B1      # wSignCoords: 2 bytes each (Y, X)

# Sprite / NPC data
ADDR_NUM_SPRITES = 0xD4E1      # wNumSprites: count of sprites on map
ADDR_SPRITE_DATA = 0xC100      # wSpriteStateData1: 16 bytes per sprite

# Tileset
ADDR_TILESET = 0xD367          # wCurMapTileset: current tileset ID

# Map structure (block map)
ADDR_MAP_HEIGHT = 0xD368       # wCurMapHeight (in blocks)
ADDR_MAP_WIDTH = 0xD369        # wCurMapWidth (in blocks)
ADDR_OVERWORLD_MAP = 0xC6E8    # wOverworldMap: block data with border
MAP_BORDER = 3                 # border width in blocks

# Interactable block IDs per tileset (discovered via `scan` command)
# Format: {tileset_id: {block_id: ("label", dy, dx)}}
# dy, dx = tile offset within the 2x2 block (0-1 each: TL=0,0  TR=0,1  BL=1,0  BR=1,1)
BLOCK_LABELS = {
    4: {
        0x10: ("PC", 1, 0),     # compu is at bottom-left tile
        0x0D: ("SNES", 1, 1),   # snes is at bottom-right tile
    },
}

# Per-tile walkability within each map block (2x2 tiles per block).
# Format: {tileset_id: {block_id: (top_left, top_right, bottom_left, bottom_right)}}
# True = walkable, False = blocked.  Discovered via `scan` command.
WALKABLE_BLOCKS = {
    1: {  # Overworld
        0x01: (True, False, True, False),
        0x02: (False, True, False, True),
        0x04: (False, False, False, False),
        0x05: (False, False, True, True),
        0x07: (False, False, True, True),
        0x09: (False, False, True, False),
        0x0B: (True, True, True, True),
        0x0F: (True, True, True, True),
    },
    4: {  # House interior
        0x08: (False, False, True, True),
        0x0C: (False, True, False, True),
        0x0D: (True, False, True, False),
        0x0F: (True, True, True, True),
        0x10: (False, False, False, False),
        0x11: (False, False, False, True),
        0x12: (False, True, False, True),
    },
}

# Human-readable tile descriptions for each mapped block (2x2: TL, TR, BL, BR).
# Used by the scan command to show what's in each block.
BLOCK_DESCRIPTIONS = {
    1: {
        0x01: ("silla", "mesa", "silla", "mesa"),
        0x02: ("mesa", "silla", "mesa", "silla"),
        0x04: ("biblio", "biblio", "biblio", "biblio"),
        0x05: ("pared", "ventana", "piso", "piso"),
        0x07: ("pared", "ventana", "piso", "escalera"),
        0x09: ("pared", "ventana", "piso", "tele"),
        0x0B: ("piso", "piso", "alfombra", "alfombra"),
        0x0F: ("piso", "piso", "piso", "piso"),
    },
    4: {
        0x08: ("pared", "ventana", "piso", "escalera"),
        0x0C: ("cama", "piso", "cama", "piso"),
        0x0D: ("piso", "tele", "piso", "snes"),
        0x0F: ("piso", "piso", "piso", "piso"),
        0x10: ("pared", "pared", "compu", "escritorio"),
        0x11: ("pared", "pared", "escritorio", "piso"),
        0x12: ("planta", "piso", "planta", "piso"),
    },
}

# Pokemon Red character encoding (from pret/pokered charmap.asm)
POKEMON_CHARMAP = {
    0x7F: " ",
    # Uppercase A-Z
    0x80: "A", 0x81: "B", 0x82: "C", 0x83: "D", 0x84: "E",
    0x85: "F", 0x86: "G", 0x87: "H", 0x88: "I", 0x89: "J",
    0x8A: "K", 0x8B: "L", 0x8C: "M", 0x8D: "N", 0x8E: "O",
    0x8F: "P", 0x90: "Q", 0x91: "R", 0x92: "S", 0x93: "T",
    0x94: "U", 0x95: "V", 0x96: "W", 0x97: "X", 0x98: "Y",
    0x99: "Z",
    # Punctuation
    0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";", 0x9E: "[", 0x9F: "]",
    # Lowercase a-z
    0xA0: "a", 0xA1: "b", 0xA2: "c", 0xA3: "d", 0xA4: "e",
    0xA5: "f", 0xA6: "g", 0xA7: "h", 0xA8: "i", 0xA9: "j",
    0xAA: "k", 0xAB: "l", 0xAC: "m", 0xAD: "n", 0xAE: "o",
    0xAF: "p", 0xB0: "q", 0xB1: "r", 0xB2: "s", 0xB3: "t",
    0xB4: "u", 0xB5: "v", 0xB6: "w", 0xB7: "x", 0xB8: "y",
    0xB9: "z",
    # Special characters
    0xBA: "é",
    0xE0: "'", 0xE3: "-", 0xE6: "?", 0xE7: "!", 0xE8: ".",
    0xF4: ",", 0xF5: "/",
    # Digits
    0xF6: "0", 0xF7: "1", 0xF8: "2", 0xF9: "3", 0xFA: "4",
    0xFB: "5", 0xFC: "6", 0xFD: "7", 0xFE: "8", 0xFF: "9",
}

# Name entry keyboard layout (uppercase, Pokemon Red)
NAME_KEYBOARD = [
    "ABCDEFGHI",
    "JKLMNOPQR",
    "STUVWXYZ ",
]
