# Pokemon Red WRAM addresses (pret/pokered disassembly)
ADDR_MAP_N = 0xD35E            # wCurMap: 0 during intro, non-zero in overworld
ADDR_MENU_Y = 0xCC24           # wTopMenuItemY: Y position of first menu item
ADDR_MENU_X = 0xCC25           # wTopMenuItemX: X position of first menu item
ADDR_CURRENT_MENU = 0xCC26     # wCurrentMenuItem: selected item (0 = first)
ADDR_MAX_MENU = 0xCC28         # wMaxMenuItem: index of last item
ADDR_MENU_WATCHED_KEYS = 0xCC29  # wMenuWatchedKeys: non-zero when menu awaits input

ADDR_PLAYER_NAME = 0xD158     # wPlayerName: 11 bytes (up to 7 chars + 0x50 terminator)
ADDR_BADGES = 0xD356           # wObtainedBadges: 8 bits, 1 per badge
ADDR_PLAY_HOURS = 0xDA40       # wPlayTimeHours: 2 bytes (little-endian)
ADDR_PLAY_MINUTES = 0xDA43     # wPlayTimeMinutes: 1 byte
ADDR_PLAY_SECONDS = 0xDA44     # wPlayTimeSeconds: 1 byte
ADDR_TILEMAP = 0xC3A0          # wTileMap: WRAM copy of screen (20 tiles per row)
ADDR_GRASS_TILE = 0xD535       # wGrassTile: tile ID that triggers wild encounters

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
ADDR_SPRITE_DATA = 0xC100      # wSpriteStateData1: 16 bytes per sprite (screen state)
ADDR_SPRITE_DATA2 = 0xC200     # wSpriteStateData2: 16 bytes per sprite (map state)
ADDR_MAP_SPRITE_DATA = 0xD4E4  # wMapSpriteData: original picture IDs (2 bytes each)

# Missable (event-hidden) sprites
ADDR_MISSABLE_FLAGS = 0xD5A6   # wMissableObjectFlags: bit array (bit set = hidden)
ADDR_MISSABLE_LIST = 0xD5CE    # wMissableObjectList: (sprite_idx, flag_bit) pairs, $FF end

# Tileset
ADDR_TILESET = 0xD367          # wCurMapTileset: current tileset ID
ADDR_TILESET_BANK = 0xD52B     # wTilesetBank: ROM bank for tileset data
ADDR_TILESET_BLOCKS_PTR = 0xD52C  # wTilesetBlocksPtr: pointer to block defs (4x4 tiles each)
ADDR_TILESET_COLL_PTR = 0xD530    # wTilesetCollisionPtr: pointer to walkable tile ID list

# Party data
ADDR_PARTY_COUNT = 0xD163     # wPartyCount: number of pokemon in party (0-6)
ADDR_PARTY_SPECIES = 0xD164   # wPartySpecies: 6 bytes, species IDs
ADDR_PARTY_MONS = 0xD16B      # wPartyMon1: 44 bytes per pokemon
PARTY_MON_SIZE = 44           # bytes per party pokemon struct
PARTY_MON_HP = 0x01           # 2 bytes big-endian, current HP
PARTY_MON_LEVEL = 0x21        # offset to level within party mon struct
PARTY_MON_MAX_HP = 0x22       # 2 bytes big-endian, max HP
ADDR_PARTY_NICKS = 0xD2B5     # wPartyMonNick: 11 bytes per nickname (10 chars + 0x50)
PARTY_NICK_SIZE = 11          # bytes per nickname entry

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
    6: {  # Pokecenter
        0x08: ("Person", 0, 0),  # Sitting person on bench (TL tile)
        0x23: ("PC", 1, 1),     # PC terminal at BR of block (far right)
    },
}

# Per-tile walkability within each map block (2x2 tiles per block).
# Format: {tileset_id: {block_id: (top_left, top_right, bottom_left, bottom_right)}}
# True = walkable, False = blocked.  Discovered via `scan` command.
WALKABLE_BLOCKS = {
    0: {  # Pallet Town / outdoor towns
        0x00: (False, False, False, False),
        0x01: (True, True, True, True),
        0x08: (True, True, True, False),
        0x0A: (True, True, True, True),
        0x0B: (True, True, True, True),
        0x0C: (False, False, False, False),
        0x0D: (False, False, False, False),
        0x0E: (False, False, False, False),
        0x10: (False, False, False, False),
        0x1D: (False, False, False, False),
        0x1E: (False, False, False, False),
        0x31: (True, True, True, True),
        0x38: (True, True, False, False),
        0x39: (True, True, False, False),
        0x3A: (False, False, True, False),
        0x3C: (False, False, False, True),
        0x3D: (False, False, False, False),
        0x4D: (True, False, True, False),
        0x4E: (False, True, False, True),
        0x4F: (True, False, False, False),
        0x50: (False, False, False, False),
        0x52: (True, True, False, False),
        0x56: (True, True, False, False),
        0x61: (True, True, False, False),
        0x64: (False, False, False, False),
        0x65: (False, False, False, False),
        0x74: (True, True, True, True),
        0x77: (True, True, False, False),
    },
    1: {  # Overworld (interior towns)
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
    0: {
        0x00: ("lab", "lab", "lab", "lab"),
        0x01: ("floor", "floor", "floor", "floor"),
        0x08: ("floor", "floor", "floor", "sign"),
        0x0A: ("floor", "floor", "floor", "floor"),
        0x0B: ("grass", "grass", "grass", "grass"),
        0x0C: ("lab", "lab", "lab", "lab"),
        0x0D: ("lab", "lab", "lab", "lab"),
        0x0E: ("lab", "lab", "lab", "lab"),
        0x10: ("lab", "lab", "lab", "lab"),
        0x1D: ("water", "water", "water", "water"),
        0x1E: ("water", "water", "water", "water"),
        0x31: ("floor", "floor", "floor", "floor"),
        0x38: ("floor", "floor", "house", "house"),
        0x39: ("floor", "floor", "house", "house"),
        0x3A: ("lab", "lab", "door", "lab"),
        0x3C: ("house", "house", "house", "door"),
        0x3D: ("house", "house", "house", "house"),
        0x4D: ("floor", "fence", "floor", "fence"),
        0x4E: ("fence", "floor", "fence", "floor"),
        0x4F: ("floor", "fence", "fence", "fence"),
        0x50: ("fence", "fence", "fence", "fence"),
        0x52: ("floor", "floor", "fence", "fence"),
        0x56: ("floor", "floor", "fence", "sign"),
        0x61: ("floor", "floor", "fence", "fence"),
        0x64: ("water", "water", "water", "water"),
        0x65: ("water", "water", "water", "water"),
        0x74: ("floor", "floor", "floor", "floor"),
        0x77: ("floor", "floor", "fence", "fence"),
    },
    1: {
        0x01: ("chair", "table", "chair", "table"),
        0x02: ("table", "chair", "table", "chair"),
        0x04: ("bookshelf", "bookshelf", "bookshelf", "bookshelf"),
        0x05: ("wall", "window", "floor", "floor"),
        0x07: ("wall", "window", "floor", "stairs"),
        0x09: ("wall", "window", "floor", "tv"),
        0x0B: ("floor", "floor", "doormat", "doormat"),
        0x0F: ("floor", "floor", "floor", "floor"),
    },
    4: {
        0x08: ("wall", "window", "floor", "stairs"),
        0x0C: ("bed", "floor", "bed", "floor"),
        0x0D: ("floor", "tv", "floor", "snes"),
        0x0F: ("floor", "floor", "floor", "floor"),
        0x10: ("wall", "wall", "pc", "desk"),
        0x11: ("wall", "wall", "desk", "floor"),
        0x12: ("plant", "floor", "plant", "floor"),
    },
}

# Map ID → human-readable name (from pret/pokered map_constants.asm)
MAP_NAMES = {
    0x00: "Pallet Town",
    0x01: "Viridian City",
    0x02: "Pewter City",
    0x03: "Cerulean City",
    0x04: "Lavender Town",
    0x05: "Vermilion City",
    0x06: "Celadon City",
    0x07: "Fuchsia City",
    0x08: "Cinnabar Island",
    0x09: "Indigo Plateau",
    0x0A: "Saffron City",
    0x0C: "Route 1",       0x0D: "Route 2",       0x0E: "Route 3",
    0x0F: "Route 4",       0x10: "Route 5",       0x11: "Route 6",
    0x12: "Route 7",       0x13: "Route 8",       0x14: "Route 9",
    0x15: "Route 10",      0x16: "Route 11",      0x17: "Route 12",
    0x18: "Route 13",      0x19: "Route 14",      0x1A: "Route 15",
    0x1B: "Route 16",      0x1C: "Route 17",      0x1D: "Route 18",
    0x1E: "Route 19",      0x1F: "Route 20",      0x20: "Route 21",
    0x21: "Route 22",      0x22: "Route 23",      0x23: "Route 24",
    0x24: "Route 25",
    0x25: "Red's House 1F",     0x26: "Red's House 2F",
    0x27: "Blue's House",       0x28: "Oak's Lab",
    0x29: "Viridian Pokecenter", 0x2A: "Viridian Mart",
    0x2B: "Viridian School",    0x2C: "Viridian Nickname House",
    0x2D: "Viridian Gym",
    0x2E: "Diglett's Cave (Route 2)", 0x2F: "Viridian Forest North Gate",
    0x30: "Route 2 Trade House", 0x31: "Route 2 Gate",
    0x32: "Viridian Forest South Gate", 0x33: "Viridian Forest",
    0x34: "Museum 1F",          0x35: "Museum 2F",
    0x36: "Pewter Gym",         0x37: "Pewter Nidoran House",
    0x38: "Pewter Mart",        0x39: "Pewter Speech House",
    0x3A: "Pewter Pokecenter",
    0x3B: "Mt. Moon 1F",        0x3C: "Mt. Moon B1F",
    0x3D: "Mt. Moon B2F",
    0x3E: "Cerulean Trashed House", 0x3F: "Cerulean Trade House",
    0x40: "Cerulean Pokecenter", 0x41: "Cerulean Gym",
    0x42: "Bike Shop",          0x43: "Cerulean Mart",
    0x44: "Mt. Moon Pokecenter",
    0x46: "Route 5 Gate",       0x47: "Underground Path (Route 5)",
    0x48: "Daycare",            0x49: "Route 6 Gate",
    0x4A: "Underground Path (Route 6)",
    0x4C: "Route 7 Gate",       0x4D: "Underground Path (Route 7)",
    0x4F: "Route 8 Gate",       0x50: "Underground Path (Route 8)",
    0x51: "Rock Tunnel Pokecenter", 0x52: "Rock Tunnel 1F",
    0x53: "Power Plant",
    0x54: "Route 11 Gate 1F",   0x55: "Diglett's Cave (Route 11)",
    0x56: "Route 11 Gate 2F",   0x57: "Route 12 Gate 1F",
    0x58: "Bill's House",
    0x59: "Vermilion Pokecenter", 0x5A: "Pokemon Fan Club",
    0x5B: "Vermilion Mart",     0x5C: "Vermilion Gym",
    0x5D: "Vermilion Pidgey House", 0x5E: "Vermilion Dock",
    0x5F: "S.S. Anne 1F",      0x60: "S.S. Anne 2F",
    0x61: "S.S. Anne 3F",      0x62: "S.S. Anne B1F",
    0x63: "S.S. Anne Bow",     0x64: "S.S. Anne Kitchen",
    0x65: "S.S. Anne Captain's Room",
    0x66: "S.S. Anne 1F Rooms", 0x67: "S.S. Anne 2F Rooms",
    0x68: "S.S. Anne B1F Rooms",
    0x6C: "Victory Road 1F",   0x71: "Lance's Room",
    0x76: "Hall of Fame",
    0x77: "Underground Path (N-S)", 0x78: "Champion's Room",
    0x79: "Underground Path (W-E)",
    0x7A: "Celadon Mart 1F",   0x7B: "Celadon Mart 2F",
    0x7C: "Celadon Mart 3F",   0x7D: "Celadon Mart 4F",
    0x7E: "Celadon Mart Roof", 0x7F: "Celadon Mart Elevator",
    0x80: "Celadon Mansion 1F", 0x81: "Celadon Mansion 2F",
    0x82: "Celadon Mansion 3F", 0x83: "Celadon Mansion Roof",
    0x84: "Celadon Mansion Roof House",
    0x85: "Celadon Pokecenter", 0x86: "Celadon Gym",
    0x87: "Game Corner",       0x88: "Celadon Mart 5F",
    0x89: "Game Corner Prize Room",
    0x8A: "Celadon Diner",     0x8B: "Celadon Chief House",
    0x8C: "Celadon Hotel",
    0x8D: "Lavender Pokecenter",
    0x8E: "Pokemon Tower 1F",  0x8F: "Pokemon Tower 2F",
    0x90: "Pokemon Tower 3F",  0x91: "Pokemon Tower 4F",
    0x92: "Pokemon Tower 5F",  0x93: "Pokemon Tower 6F",
    0x94: "Pokemon Tower 7F",
    0x95: "Mr. Fuji's House",  0x96: "Lavender Mart",
    0x97: "Lavender Cubone House",
    0x98: "Fuchsia Mart",      0x99: "Fuchsia Bill's Grandpa's House",
    0x9A: "Fuchsia Pokecenter", 0x9B: "Warden's House",
    0x9C: "Safari Zone Gate",  0x9D: "Fuchsia Gym",
    0x9E: "Fuchsia Meeting Room",
    0x9F: "Seafoam Islands B1F", 0xA0: "Seafoam Islands B2F",
    0xA1: "Seafoam Islands B3F", 0xA2: "Seafoam Islands B4F",
    0xA3: "Vermilion Old Rod House", 0xA4: "Fuchsia Good Rod House",
    0xA5: "Pokemon Mansion 1F", 0xA6: "Cinnabar Gym",
    0xA7: "Cinnabar Lab",      0xA8: "Cinnabar Lab Trade Room",
    0xA9: "Cinnabar Lab Metronome Room", 0xAA: "Cinnabar Lab Fossil Room",
    0xAB: "Cinnabar Pokecenter", 0xAC: "Cinnabar Mart",
    0xAE: "Indigo Plateau Lobby",
    0xAF: "Copycat's House 1F", 0xB0: "Copycat's House 2F",
    0xB1: "Fighting Dojo",     0xB2: "Saffron Gym",
    0xB3: "Saffron Pidgey House", 0xB4: "Saffron Mart",
    0xB5: "Silph Co. 1F",      0xB6: "Saffron Pokecenter",
    0xB7: "Mr. Psychic's House",
    0xB8: "Route 15 Gate 1F",  0xB9: "Route 15 Gate 2F",
    0xBA: "Route 16 Gate 1F",  0xBB: "Route 16 Gate 2F",
    0xBC: "Route 16 Fly House", 0xBD: "Route 12 Super Rod House",
    0xBE: "Route 18 Gate 1F",  0xBF: "Route 18 Gate 2F",
    0xC0: "Seafoam Islands 1F", 0xC1: "Route 22 Gate",
    0xC2: "Victory Road 2F",   0xC3: "Route 12 Gate 2F",
    0xC4: "Vermilion Trade House", 0xC5: "Diglett's Cave",
    0xC6: "Victory Road 3F",
    0xC7: "Rocket Hideout B1F", 0xC8: "Rocket Hideout B2F",
    0xC9: "Rocket Hideout B3F", 0xCA: "Rocket Hideout B4F",
    0xCB: "Rocket Hideout Elevator",
    0xCF: "Silph Co. 2F",      0xD0: "Silph Co. 3F",
    0xD1: "Silph Co. 4F",      0xD2: "Silph Co. 5F",
    0xD3: "Silph Co. 6F",      0xD4: "Silph Co. 7F",
    0xD5: "Silph Co. 8F",
    0xD6: "Pokemon Mansion 2F", 0xD7: "Pokemon Mansion 3F",
    0xD8: "Pokemon Mansion B1F",
    0xD9: "Safari Zone East",  0xDA: "Safari Zone North",
    0xDB: "Safari Zone West",  0xDC: "Safari Zone Center",
    0xDD: "Safari Zone Center Rest House",
    0xDE: "Safari Zone Secret House",
    0xDF: "Safari Zone West Rest House",
    0xE0: "Safari Zone East Rest House",
    0xE1: "Safari Zone North Rest House",
    0xE2: "Cerulean Cave 2F",  0xE3: "Cerulean Cave B1F",
    0xE4: "Cerulean Cave 1F",
    0xE5: "Name Rater's House", 0xE6: "Cerulean Badge House",
    0xE8: "Rock Tunnel B1F",
    0xE9: "Silph Co. 9F",      0xEA: "Silph Co. 10F",
    0xEB: "Silph Co. 11F",     0xEC: "Silph Co. Elevator",
    0xEF: "Trade Center",      0xF0: "Colosseum",
    0xF5: "Lorelei's Room",    0xF6: "Bruno's Room",
    0xF7: "Agatha's Room",
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
    # Contraction tiles (single tile for apostrophe + letter)
    0xBB: "'d", 0xBC: "'l", 0xBD: "'s", 0xBE: "'t", 0xBF: "'v",
    0xE0: "'",
    0xE3: "-",
    0xE4: "'r", 0xE5: "'m",
    0xE6: "?", 0xE7: "!", 0xE8: ".",
    # Symbols
    0xEF: "♂", 0xF0: "¥", 0xF1: "×",
    0xF3: "/", 0xF4: ",", 0xF5: "♀",
    # Digits
    0xF6: "0", 0xF7: "1", 0xF8: "2", 0xF9: "3", 0xFA: "4",
    0xFB: "5", 0xFC: "6", 0xFD: "7", 0xFE: "8", 0xFF: "9",
}

# Sprite picture IDs → labels (from pret/pokered sprite_constants.asm).
# Only non-"Person" sprites listed; unlisted IDs default to "Person".
SPRITE_LABELS = {
    # Main characters
    0x01: "Red",            # SPRITE_RED (player — shouldn't appear as NPC)
    0x02: "Rival",          # SPRITE_BLUE
    0x03: "Prof. Oak",      # SPRITE_OAK
    # Human NPCs
    0x04: "Youngster",      # SPRITE_YOUNGSTER
    0x06: "Woman",          # SPRITE_COOLTRAINER_F
    0x07: "Man",            # SPRITE_COOLTRAINER_M
    0x08: "Little Girl",    # SPRITE_LITTLE_GIRL
    0x0A: "Man",            # SPRITE_MIDDLE_AGED_MAN
    0x0B: "Gambler",        # SPRITE_GAMBLER
    0x0C: "Nerd",           # SPRITE_SUPER_NERD
    0x0D: "Girl",           # SPRITE_GIRL
    0x0E: "Hiker",          # SPRITE_HIKER
    0x0F: "Beauty",         # SPRITE_BEAUTY
    0x10: "Gentleman",      # SPRITE_GENTLEMAN
    0x11: "Daisy",          # SPRITE_DAISY
    0x12: "Biker",          # SPRITE_BIKER
    0x13: "Sailor",         # SPRITE_SAILOR
    0x14: "Cook",           # SPRITE_COOK
    0x15: "Bike Shop Clerk",  # SPRITE_BIKE_SHOP_CLERK
    0x16: "Mr. Fuji",       # SPRITE_MR_FUJI
    0x17: "Giovanni",       # SPRITE_GIOVANNI
    0x18: "Rocket",         # SPRITE_ROCKET
    0x19: "Channeler",      # SPRITE_CHANNELER
    0x1A: "Waiter",         # SPRITE_WAITER
    0x1B: "Worker",         # SPRITE_SILPH_WORKER_F
    0x1C: "Woman",          # SPRITE_MIDDLE_AGED_WOMAN
    0x1D: "Girl",           # SPRITE_BRUNETTE_GIRL
    0x1E: "Lance",          # SPRITE_LANCE
    0x1F: "Scientist",      # SPRITE_UNUSED_SCIENTIST
    0x20: "Scientist",      # SPRITE_SCIENTIST
    0x22: "Swimmer",        # SPRITE_SWIMMER
    0x23: "Safari Worker",  # SPRITE_SAFARI_ZONE_WORKER
    0x24: "Gym Guide",      # SPRITE_GYM_GUIDE
    0x25: "Old Man",        # SPRITE_GRAMPS
    0x27: "Fishing Guru",   # SPRITE_FISHING_GURU
    0x28: "Old Woman",      # SPRITE_GRANNY
    0x2B: "Silph President",  # SPRITE_SILPH_PRESIDENT
    0x2D: "Warden",         # SPRITE_WARDEN
    0x2E: "Captain",        # SPRITE_CAPTAIN
    0x2F: "Fisher",         # SPRITE_FISHER
    0x30: "Koga",           # SPRITE_KOGA
    0x31: "Guard",          # SPRITE_GUARD
    0x33: "Mom",            # SPRITE_MOM
    0x34: "Balding Man",    # SPRITE_BALDING_GUY
    0x35: "Little Boy",     # SPRITE_LITTLE_BOY
    0x37: "Gameboy Kid",    # SPRITE_GAMEBOY_KID
    0x39: "Agatha",         # SPRITE_AGATHA
    0x3A: "Bruno",          # SPRITE_BRUNO
    0x3B: "Lorelei",        # SPRITE_LORELEI
    # Pokémon sprites
    0x05: "Pokémon",        # SPRITE_MONSTER (Slowbro)
    0x09: "Pokémon",        # SPRITE_BIRD (Pidgey)
    0x21: "Pokémon",        # SPRITE_ROCKER (Clefairy)
    0x38: "Pokémon",        # SPRITE_FAIRY (Clefairy)
    0x3C: "Pokémon",        # SPRITE_SEEL
    0x43: "Pokémon",        # SPRITE_SNORLAX
    # Object sprites
    0x26: "Clerk",          # SPRITE_CLERK (shop cashier)
    0x29: "Nurse",          # SPRITE_NURSE
    0x2A: "Cable Club",     # SPRITE_LINK_RECEPTIONIST
    0x2C: "Worker",         # SPRITE_SILPH_WORKER_M
    0x3D: "Poké Ball",      # SPRITE_POKE_BALL
    0x3E: "Fossil",         # SPRITE_FOSSIL
    0x3F: "Boulder",        # SPRITE_BOULDER
    0x40: "Paper",          # SPRITE_PAPER
    0x41: "Book",           # SPRITE_POKEDEX
    0x42: "Note",           # SPRITE_CLIPBOARD
    0x44: "Old Amber",      # SPRITE_UNUSED_OLD_AMBER
    0x45: "Old Amber",      # SPRITE_OLD_AMBER
}

# Battle state
ADDR_IS_IN_BATTLE = 0xD057     # wIsInBattle: 0=no, 1=wild, 2=trainer
ADDR_PLAYER_MON_NUMBER = 0xCC2F  # wPlayerMonNumber: party index of active battle pokemon

# Battle mon structures (battle struct is shorter than party struct:
# no EVs, no OT ID, no experience — just DVs between moves and PP)
ADDR_BATTLE_MON = 0xD014       # wBattleMon: player's active pokemon
ADDR_ENEMY_MON = 0xCFE5        # wEnemyMon: enemy's active pokemon

# Offsets within the BATTLE mon struct (verified via hex dump)
# +00 Species  +01 HP(2)  +03 BoxLvl  +04 Status  +05 Type1  +06 Type2
# +07 CatchRate  +08 Moves(4)  +0C DVs(2)  +0E Level  +0F MaxHP(2)
# +11 Atk(2)  +13 Def(2)  +15 Spd(2)  +17 Spc(2)  +19 PP(4)
BMON_SPECIES = 0x00            # 1 byte: internal species ID
BMON_HP = 0x01                 # 2 bytes big-endian: current HP
BMON_STATUS = 0x04             # 1 byte: status condition
BMON_TYPE1 = 0x05              # 1 byte
BMON_TYPE2 = 0x06              # 1 byte
BMON_MOVES = 0x08              # 4 bytes: move IDs (0 = empty slot)
BMON_LEVEL = 0x0E              # 1 byte
BMON_MAX_HP = 0x0F             # 2 bytes big-endian
BMON_PP = 0x19                 # 4 bytes: PP remaining (lower 6 bits)

# Disable status
ADDR_DISABLED_MOVE = 0xD06D    # wDisabledMove: bits 0-2 = move slot (1-4), bits 4-7 = turns left

# Bag / inventory
ADDR_NUM_BAG_ITEMS = 0xD31D    # wNumBagItems: count of item types in bag
ADDR_BAG_ITEMS = 0xD31E        # wBagItems: pairs of (item_id, count), FF-terminated

# Poké Ball item IDs
ITEM_POKE_BALL = 0x04
ITEM_GREAT_BALL = 0x03
ITEM_ULTRA_BALL = 0x02
ITEM_MASTER_BALL = 0x01

BALL_ITEMS = {
    ITEM_MASTER_BALL: "Master Ball",
    ITEM_ULTRA_BALL: "Ultra Ball",
    ITEM_GREAT_BALL: "Great Ball",
    ITEM_POKE_BALL: "Poké Ball",
}

# Event flags
ADDR_POKEDEX_FLAG = 0xD74B     # bit 5 = has Pokédex

# Player money (3 bytes, BCD encoded)
ADDR_PLAYER_MONEY = 0xD347

# Poké Mart current inventory (loaded per-map)
ADDR_MART_NUM_ITEMS = 0xCF7B   # number of items for sale
ADDR_MART_ITEMS = 0xCF7C       # item IDs listed sequentially

# Item catalogue: id → (name, price)
ITEM_CATALOGUE = {
    0x01: ("Master Ball", 0),
    0x02: ("Ultra Ball", 1200),
    0x03: ("Great Ball", 600),
    0x04: ("Poké Ball", 200),
    0x05: ("Town Map", 0),
    0x06: ("Bicycle", 1000000),
    0x0B: ("Antidote", 100),
    0x0C: ("Burn Heal", 250),
    0x0D: ("Ice Heal", 250),
    0x0E: ("Awakening", 200),
    0x0F: ("Parlyz Heal", 200),
    0x10: ("Full Restore", 3000),
    0x11: ("Max Potion", 2500),
    0x12: ("Hyper Potion", 1500),
    0x13: ("Super Potion", 700),
    0x14: ("Potion", 300),
    0x1D: ("Escape Rope", 550),
    0x1E: ("Repel", 350),
    0x23: ("Full Heal", 600),
    0x24: ("Revive", 1500),
    0x25: ("Max Revive", 0),
    0x2E: ("Fresh Water", 200),
    0x2F: ("Soda Pop", 300),
    0x30: ("Lemonade", 350),
    0x48: ("X Attack", 500),
    0x49: ("X Defend", 550),
    0x4A: ("X Speed", 350),
    0x4B: ("X Special", 350),
    0x50: ("HP Up", 9800),
    0x51: ("Protein", 9800),
    0x52: ("Iron", 9800),
    0x53: ("Carbos", 9800),
    0x54: ("Calcium", 9800),
}

# Name entry keyboard layout (uppercase, Pokemon Red)
NAME_KEYBOARD = [
    "ABCDEFGHI",
    "JKLMNOPQR",
    "STUVWXYZ ",
]
