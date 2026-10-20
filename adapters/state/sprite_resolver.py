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

# Gym map ID -> (leader name, leader's trainer class). The leader is told
# apart by trainer class, not by sprite: gym trainers can share the leader's
# sprite (a Gentleman trainer in Vermilion Gym, for instance).
_GYM_LEADERS = {
    0x36: ("BROCK", 34),      # Pewter Gym
    0x41: ("MISTY", 35),      # Cerulean Gym
    0x5C: ("LT. SURGE", 36),  # Vermilion Gym
    0x86: ("ERIKA", 37),      # Celadon Gym
    0x9D: ("KOGA", 38),       # Fuchsia Gym
    0xA6: ("BLAINE", 39),     # Cinnabar Gym
    0xB2: ("SABRINA", 40),    # Saffron Gym
    0x2D: ("GIOVANNI", 29),   # Viridian Gym
}

_OPP_ID_OFFSET = 200  # trainer objects store class + 200


class SpriteResolver:
    """Resolves sprite picture IDs and labels from ROM data."""

    # WRAM addresses for map header pattern matching
    _HEADER_WRAM_START = 0xD367
    _HEADER_WRAM_LEN = 9

    def __init__(self, pyboy, rom=None):
        self._pyboy = pyboy
        self._rom = rom
        self._classes_cache = (None, [])

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

    def get_sprite_trainer_classes(self):
        """Trainer class of each map object (index = sprite index - 1); 0 for
        objects that aren't trainers. Cached per map header."""
        header = self.find_map_header()
        if header is None:
            return []
        if self._classes_cache[0] == header:
            return self._classes_cache[1]
        rom = self._rom
        bank = header // 0x4000
        num_conn = bin(rom[header + 9]).count('1')
        obj_ptr_addr = header + 10 + num_conn * 11
        obj = self._rom_offset(bank, rom[obj_ptr_addr] | (rom[obj_ptr_addr + 1] << 8))
        pos = obj + 1
        pos += 1 + rom[pos] * 4        # warps
        pos += 1 + rom[pos] * 3        # signs
        classes = []
        num_sprites = rom[pos]; pos += 1
        for _ in range(num_sprites):
            text_id = rom[pos + 5]
            trainer_class = 0
            if text_id & 0x40:
                trainer_class = max(rom[pos + 6] - _OPP_ID_OFFSET, 0)
            classes.append(trainer_class)
            pos += 6 + (2 if text_id & 0x40 else 1 if text_id & 0x80 else 0)
        self._classes_cache = (header, classes)
        return classes

    def resolve_label(self, pic_id, map_id, sx, sprite_index=None):
        """Return the display label for a sprite, with special overrides."""
        label = SPRITE_LABELS.get(pic_id, "Person")

        # Override Poké Ball labels in Oak's Lab with starter names
        if label == "Poké Ball" and map_id == 0x28:
            label = _OAK_LAB_STARTERS.get(sx, label)

        # The Gym Leader, recognized by trainer class
        gym_leader = _GYM_LEADERS.get(map_id)
        if gym_leader and sprite_index is not None:
            classes = self.get_sprite_trainer_classes()
            if 0 < sprite_index <= len(classes) and classes[sprite_index - 1] == gym_leader[1]:
                label = f"GYM LEADER {gym_leader[0]}"

        return label

    def _rom_offset(self, bank, ptr):
        if ptr < 0x4000:
            return ptr
        return bank * 0x4000 + (ptr - 0x4000)
