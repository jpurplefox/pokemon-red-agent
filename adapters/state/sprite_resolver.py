"""Sprite label resolution (SRP).

Reads sprite picture IDs from ROM and resolves labels with special
overrides for Gym Leaders, Oak's Lab starters, etc.
"""

from data.constants import SPRITE_LABELS, MAP_NAMES

# Oak's Lab (map 0x28) starter Poké Balls by X coordinate
_OAK_LAB_STARTERS = {
    6: "Poké Ball (CHARMANDER)",
    7: "Poké Ball (SQUIRTLE)",
    8: "Poké Ball (BULBASAUR)",
}

# Gym map IDs → (leader name, sprite label they use)
_GYM_LEADERS = {
    0x36: ("BROCK", "Nerd"),        # Pewter Gym
    0x41: ("MISTY", "Girl"),         # Cerulean Gym
    0x5C: ("LT. SURGE", "Gentleman"),  # Vermilion Gym
    0x86: ("ERIKA", "Beauty"),      # Celadon Gym
    0x9D: ("KOGA", "Nerd"),         # Fuchsia Gym
    0xB2: ("SABRINA", "Beauty"),    # Saffron Gym
    0xA6: ("BLAINE", "Nerd"),       # Cinnabar Gym
    0x2D: ("GIOVANNI", "Giovanni"), # Viridian Gym
}


class SpriteResolver:
    """Resolves sprite picture IDs and labels from ROM data."""

    # WRAM addresses for map header pattern matching
    _HEADER_WRAM_START = 0xD367
    _HEADER_WRAM_LEN = 9

    def __init__(self, pyboy, rom=None):
        self._pyboy = pyboy
        self._rom = rom

    def find_map_header(self):
        """Find the current map's header offset in ROM."""
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
        """Read original sprite picture IDs from ROM map object data."""
        header = self.find_map_header()
        if header is None:
            return []
        rom = self._rom
        bank = header // 0x4000

        conn_flags = rom[header + 9]
        num_conn = bin(conn_flags).count('1')
        obj_ptr_addr = header + 10 + num_conn * 11
        obj_ptr = rom[obj_ptr_addr] | (rom[obj_ptr_addr + 1] << 8)
        obj = self._rom_offset(bank, obj_ptr)

        pos = obj + 1  # skip border block
        num_warps = rom[pos]; pos += 1
        pos += num_warps * 4

        num_signs = rom[pos]; pos += 1
        pos += num_signs * 3

        num_sprites = rom[pos]; pos += 1
        pic_ids = []
        for _ in range(num_sprites):
            pic_ids.append(rom[pos])
            text_id = rom[pos + 5]
            pos += 6
            if text_id & 0x40:
                pos += 2
            elif text_id & 0x80:
                pos += 1
        return pic_ids

    def resolve_label(self, pic_id, map_id, sx):
        """Return the display label for a sprite, with special overrides."""
        label = SPRITE_LABELS.get(pic_id, "Person")

        # Override Poké Ball labels in Oak's Lab with starter names
        if label == "Poké Ball" and map_id == 0x28:
            label = _OAK_LAB_STARTERS.get(sx, label)

        # Override sprite labels in Gyms with leader names
        gym_leader = _GYM_LEADERS.get(map_id)
        if gym_leader and label == gym_leader[1]:
            label = f"GYM LEADER {gym_leader[0]}"

        return label

    def _rom_offset(self, bank, ptr):
        if ptr < 0x4000:
            return ptr
        return bank * 0x4000 + (ptr - 0x4000)
