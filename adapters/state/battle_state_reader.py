"""Battle state reader — reads WRAM to extract battle domain objects (SRP).

Pure read-only adapter: no button presses, no side effects.
Returns domain objects (BattleMon, PartyMember, Move) from models.py.
"""

from data.constants import (
    ADDR_IS_IN_BATTLE, ADDR_BATTLE_MON, ADDR_ENEMY_MON,
    ADDR_PLAYER_MON_NUMBER, ADDR_DISABLED_MOVE,
    BMON_SPECIES, BMON_HP, BMON_STATUS, BMON_MOVES,
    BMON_PP, BMON_LEVEL, BMON_MAX_HP,
    ADDR_PARTY_COUNT, ADDR_PARTY_SPECIES, ADDR_PARTY_MONS,
    PARTY_MON_SIZE, PARTY_MON_LEVEL, PARTY_MON_HP, PARTY_MON_MAX_HP,
    ADDR_PARTY_NICKS, PARTY_NICK_SIZE,
    POKEMON_CHARMAP,
)
from data.pokemon_data import POKEMON_NAMES, MOVE_NAMES, MOVE_BASE_PP, status_text
from domain.models import PartyMember, BattleMon, Move


class BattleStateReader:
    """Read-only accessor for battle and party state from WRAM."""

    def __init__(self, pyboy):
        self._pyboy = pyboy

    def is_in_battle(self) -> bool:
        return self._pyboy.memory[ADDR_IS_IN_BATTLE] != 0

    def is_wild(self) -> bool:
        return self._pyboy.memory[ADDR_IS_IN_BATTLE] == 1

    def is_trainer(self) -> bool:
        return self._pyboy.memory[ADDR_IS_IN_BATTLE] == 2

    def active_mon_index(self) -> int:
        return self._pyboy.memory[ADDR_PLAYER_MON_NUMBER]

    def read_player(self) -> BattleMon:
        mon = self._read_mon(ADDR_BATTLE_MON)
        # Mark disabled move (from DISABLE status effect)
        disabled_byte = self._pyboy.memory[ADDR_DISABLED_MOVE]
        if disabled_byte:
            disabled_slot = (disabled_byte & 0x07) - 1  # 1-based → 0-based
            if 0 <= disabled_slot < len(mon.moves):
                mon.moves[disabled_slot].disabled = True
        return mon

    def read_enemy(self) -> BattleMon:
        return self._read_mon(ADDR_ENEMY_MON)

    def read_enemy_species(self) -> str:
        mem = self._pyboy.memory
        species = mem[ADDR_ENEMY_MON + BMON_SPECIES]
        return POKEMON_NAMES.get(species, f"POKEMON#{species:02X}")

    def read_party(self) -> list[PartyMember]:
        """Read the player's full party from WRAM."""
        mem = self._pyboy.memory
        count = mem[ADDR_PARTY_COUNT]
        party = []
        for i in range(min(count, 6)):
            species_id = mem[ADDR_PARTY_SPECIES + i]
            name = POKEMON_NAMES.get(species_id, f"#{species_id:02X}")
            base = ADDR_PARTY_MONS + i * PARTY_MON_SIZE
            level = mem[base + PARTY_MON_LEVEL]
            hp = (mem[base + PARTY_MON_HP] << 8) | mem[base + PARTY_MON_HP + 1]
            max_hp = (mem[base + PARTY_MON_MAX_HP] << 8) | mem[base + PARTY_MON_MAX_HP + 1]
            nick_base = ADDR_PARTY_NICKS + i * PARTY_NICK_SIZE
            nickname = ""
            for j in range(10):
                tile = mem[nick_base + j]
                if tile == 0x50:
                    break
                nickname += POKEMON_CHARMAP.get(tile, "")
            party.append(PartyMember(
                name=name,
                nickname=nickname.strip() or name,
                level=level, hp=hp, max_hp=max_hp,
            ))
        return party

    def _read_mon(self, base: int) -> BattleMon:
        """Read a battle mon's stats from WRAM at the given base address."""
        mem = self._pyboy.memory
        species = mem[base + BMON_SPECIES]
        hp = (mem[base + BMON_HP] << 8) | mem[base + BMON_HP + 1]
        max_hp = (mem[base + BMON_MAX_HP] << 8) | mem[base + BMON_MAX_HP + 1]
        level = mem[base + BMON_LEVEL]
        status = status_text(mem[base + BMON_STATUS])
        name = POKEMON_NAMES.get(species, f"#{species:02X}")

        moves = []
        for i in range(4):
            move_id = mem[base + BMON_MOVES + i]
            if move_id == 0:
                continue
            pp_byte = mem[base + BMON_PP + i]
            pp = pp_byte & 0x3F
            pp_ups = pp_byte >> 6
            base_pp = MOVE_BASE_PP.get(move_id, 0)
            max_pp = base_pp + (base_pp * pp_ups) // 5
            move_name = MOVE_NAMES.get(move_id, f"Move #{move_id}")
            moves.append(Move(name=move_name, pp=pp, max_pp=max_pp))

        return BattleMon(
            name=name, level=level,
            hp=hp, max_hp=max_hp,
            status=status, moves=moves,
        )
