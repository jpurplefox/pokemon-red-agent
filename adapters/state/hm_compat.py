"""Which species can learn each HM, from the ROM's base stats (SRP).

Every base stats entry carries a TM/HM bitfield; reading it covers all five
HMs without a hand-written table.
"""

from data.constants import (
    BASE_STATS_SIZE, BASE_STATS_TMHM, HM_BITS, ROM_BASE_STATS,
    ROM_MEW_BASE_STATS, ROM_POKEDEX_ORDER,
)

_MEW = 151


class HMCompatibility:
    def __init__(self, rom: bytes):
        self._rom = rom

    def can_learn(self, species_id: int, move: str) -> bool:
        """Whether the species (internal index) can learn the HM move."""
        bit = HM_BITS.get(move)
        if bit is None or not species_id:
            return False
        dex = self._rom[ROM_POKEDEX_ORDER + species_id - 1]
        if dex == 0:
            return False  # MissingNo. slots
        entry = (ROM_MEW_BASE_STATS if dex == _MEW
                 else ROM_BASE_STATS + (dex - 1) * BASE_STATS_SIZE)
        flags = self._rom[entry + BASE_STATS_TMHM: entry + BASE_STATS_TMHM + 7]
        return bool(flags[bit // 8] >> (bit % 8) & 1)
