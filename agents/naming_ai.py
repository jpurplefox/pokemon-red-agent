"""Naming AI — uses a local LLM to generate creative Pokemon nicknames.

Considers the Pokemon's species, evolution line, potential, and existing
team nicknames to avoid duplicates.  Names are limited to 10 characters
(Pokemon Red constraint).
"""

from langchain_core.messages import SystemMessage, HumanMessage
from adapters.display.ai_logger import AILogger

_log = AILogger("NAME")


# Gen 1 evolution lines (species → [stage1, stage2, stage3])
EVOLUTION_LINES = {
    "BULBASAUR": ["BULBASAUR", "IVYSAUR", "VENUSAUR"],
    "IVYSAUR": ["BULBASAUR", "IVYSAUR", "VENUSAUR"],
    "VENUSAUR": ["BULBASAUR", "IVYSAUR", "VENUSAUR"],
    "CHARMANDER": ["CHARMANDER", "CHARMELEON", "CHARIZARD"],
    "CHARMELEON": ["CHARMANDER", "CHARMELEON", "CHARIZARD"],
    "CHARIZARD": ["CHARMANDER", "CHARMELEON", "CHARIZARD"],
    "SQUIRTLE": ["SQUIRTLE", "WARTORTLE", "BLASTOISE"],
    "WARTORTLE": ["SQUIRTLE", "WARTORTLE", "BLASTOISE"],
    "BLASTOISE": ["SQUIRTLE", "WARTORTLE", "BLASTOISE"],
    "CATERPIE": ["CATERPIE", "METAPOD", "BUTTERFREE"],
    "METAPOD": ["CATERPIE", "METAPOD", "BUTTERFREE"],
    "BUTTERFREE": ["CATERPIE", "METAPOD", "BUTTERFREE"],
    "WEEDLE": ["WEEDLE", "KAKUNA", "BEEDRILL"],
    "KAKUNA": ["WEEDLE", "KAKUNA", "BEEDRILL"],
    "BEEDRILL": ["WEEDLE", "KAKUNA", "BEEDRILL"],
    "PIDGEY": ["PIDGEY", "PIDGEOTTO", "PIDGEOT"],
    "PIDGEOTTO": ["PIDGEY", "PIDGEOTTO", "PIDGEOT"],
    "PIDGEOT": ["PIDGEY", "PIDGEOTTO", "PIDGEOT"],
    "RATTATA": ["RATTATA", "RATICATE"],
    "RATICATE": ["RATTATA", "RATICATE"],
    "SPEAROW": ["SPEAROW", "FEAROW"],
    "FEAROW": ["SPEAROW", "FEAROW"],
    "EKANS": ["EKANS", "ARBOK"],
    "ARBOK": ["EKANS", "ARBOK"],
    "PIKACHU": ["PIKACHU", "RAICHU"],
    "RAICHU": ["PIKACHU", "RAICHU"],
    "SANDSHREW": ["SANDSHREW", "SANDSLASH"],
    "SANDSLASH": ["SANDSHREW", "SANDSLASH"],
    "NIDORAN♀": ["NIDORAN♀", "NIDORINA", "NIDOQUEEN"],
    "NIDORINA": ["NIDORAN♀", "NIDORINA", "NIDOQUEEN"],
    "NIDOQUEEN": ["NIDORAN♀", "NIDORINA", "NIDOQUEEN"],
    "NIDORAN♂": ["NIDORAN♂", "NIDORINO", "NIDOKING"],
    "NIDORINO": ["NIDORAN♂", "NIDORINO", "NIDOKING"],
    "NIDOKING": ["NIDORAN♂", "NIDORINO", "NIDOKING"],
    "CLEFAIRY": ["CLEFAIRY", "CLEFABLE"],
    "CLEFABLE": ["CLEFAIRY", "CLEFABLE"],
    "VULPIX": ["VULPIX", "NINETALES"],
    "NINETALES": ["VULPIX", "NINETALES"],
    "JIGGLYPUFF": ["JIGGLYPUFF", "WIGGLYTUFF"],
    "WIGGLYTUFF": ["JIGGLYPUFF", "WIGGLYTUFF"],
    "ZUBAT": ["ZUBAT", "GOLBAT"],
    "GOLBAT": ["ZUBAT", "GOLBAT"],
    "ODDISH": ["ODDISH", "GLOOM", "VILEPLUME"],
    "GLOOM": ["ODDISH", "GLOOM", "VILEPLUME"],
    "VILEPLUME": ["ODDISH", "GLOOM", "VILEPLUME"],
    "PARAS": ["PARAS", "PARASECT"],
    "PARASECT": ["PARAS", "PARASECT"],
    "VENONAT": ["VENONAT", "VENOMOTH"],
    "VENOMOTH": ["VENONAT", "VENOMOTH"],
    "DIGLETT": ["DIGLETT", "DUGTRIO"],
    "DUGTRIO": ["DIGLETT", "DUGTRIO"],
    "MEOWTH": ["MEOWTH", "PERSIAN"],
    "PERSIAN": ["MEOWTH", "PERSIAN"],
    "PSYDUCK": ["PSYDUCK", "GOLDUCK"],
    "GOLDUCK": ["PSYDUCK", "GOLDUCK"],
    "MANKEY": ["MANKEY", "PRIMEAPE"],
    "PRIMEAPE": ["MANKEY", "PRIMEAPE"],
    "GROWLITHE": ["GROWLITHE", "ARCANINE"],
    "ARCANINE": ["GROWLITHE", "ARCANINE"],
    "POLIWAG": ["POLIWAG", "POLIWHIRL", "POLIWRATH"],
    "POLIWHIRL": ["POLIWAG", "POLIWHIRL", "POLIWRATH"],
    "POLIWRATH": ["POLIWAG", "POLIWHIRL", "POLIWRATH"],
    "ABRA": ["ABRA", "KADABRA", "ALAKAZAM"],
    "KADABRA": ["ABRA", "KADABRA", "ALAKAZAM"],
    "ALAKAZAM": ["ABRA", "KADABRA", "ALAKAZAM"],
    "MACHOP": ["MACHOP", "MACHOKE", "MACHAMP"],
    "MACHOKE": ["MACHOP", "MACHOKE", "MACHAMP"],
    "MACHAMP": ["MACHOP", "MACHOKE", "MACHAMP"],
    "BELLSPROUT": ["BELLSPROUT", "WEEPINBELL", "VICTREEBEL"],
    "WEEPINBELL": ["BELLSPROUT", "WEEPINBELL", "VICTREEBEL"],
    "VICTREEBEL": ["BELLSPROUT", "WEEPINBELL", "VICTREEBEL"],
    "TENTACOOL": ["TENTACOOL", "TENTACRUEL"],
    "TENTACRUEL": ["TENTACOOL", "TENTACRUEL"],
    "GEODUDE": ["GEODUDE", "GRAVELER", "GOLEM"],
    "GRAVELER": ["GEODUDE", "GRAVELER", "GOLEM"],
    "GOLEM": ["GEODUDE", "GRAVELER", "GOLEM"],
    "PONYTA": ["PONYTA", "RAPIDASH"],
    "RAPIDASH": ["PONYTA", "RAPIDASH"],
    "SLOWPOKE": ["SLOWPOKE", "SLOWBRO"],
    "SLOWBRO": ["SLOWPOKE", "SLOWBRO"],
    "MAGNEMITE": ["MAGNEMITE", "MAGNETON"],
    "MAGNETON": ["MAGNEMITE", "MAGNETON"],
    "DODUO": ["DODUO", "DODRIO"],
    "DODRIO": ["DODUO", "DODRIO"],
    "SEEL": ["SEEL", "DEWGONG"],
    "DEWGONG": ["SEEL", "DEWGONG"],
    "GRIMER": ["GRIMER", "MUK"],
    "MUK": ["GRIMER", "MUK"],
    "SHELLDER": ["SHELLDER", "CLOYSTER"],
    "CLOYSTER": ["SHELLDER", "CLOYSTER"],
    "GASTLY": ["GASTLY", "HAUNTER", "GENGAR"],
    "HAUNTER": ["GASTLY", "HAUNTER", "GENGAR"],
    "GENGAR": ["GASTLY", "HAUNTER", "GENGAR"],
    "ONIX": ["ONIX"],
    "DROWZEE": ["DROWZEE", "HYPNO"],
    "HYPNO": ["DROWZEE", "HYPNO"],
    "KRABBY": ["KRABBY", "KINGLER"],
    "KINGLER": ["KRABBY", "KINGLER"],
    "EXEGGCUTE": ["EXEGGCUTE", "EXEGGUTOR"],
    "EXEGGUTOR": ["EXEGGCUTE", "EXEGGUTOR"],
    "CUBONE": ["CUBONE", "MAROWAK"],
    "MAROWAK": ["CUBONE", "MAROWAK"],
    "HORSEA": ["HORSEA", "SEADRA"],
    "SEADRA": ["HORSEA", "SEADRA"],
    "GOLDEEN": ["GOLDEEN", "SEAKING"],
    "SEAKING": ["GOLDEEN", "SEAKING"],
    "STARYU": ["STARYU", "STARMIE"],
    "STARMIE": ["STARYU", "STARMIE"],
    "MAGIKARP": ["MAGIKARP", "GYARADOS"],
    "GYARADOS": ["MAGIKARP", "GYARADOS"],
    "EEVEE": ["EEVEE", "VAPOREON / JOLTEON / FLAREON"],
    "DRATINI": ["DRATINI", "DRAGONAIR", "DRAGONITE"],
    "DRAGONAIR": ["DRATINI", "DRAGONAIR", "DRAGONITE"],
    "DRAGONITE": ["DRATINI", "DRAGONAIR", "DRAGONITE"],
}

SYSTEM_PROMPT = """\
You are a creative Pokemon nickname generator for Pokemon Red.

STRICT RULES:
- The name MUST be 10 characters or fewer (this is a hard game limit).
- The name MUST use only uppercase letters A-Z, spaces, and basic punctuation.
- Do NOT repeat any nickname already used by the team.
- Consider the Pokemon's species, type, and evolution potential when naming.
- Be creative, fun, and memorable. Can reference pop culture, puns, or traits.
- The name should still feel like a good fit even after the Pokemon evolves.

Respond with EXACTLY this format:
THINK: <brief reasoning about the name choice>
NAME: <the nickname in uppercase, 10 chars max>"""


class NamingAI:
    def __init__(self, llm):
        self._llm = llm

    def suggest_name(self, species, team_names=None):
        """Generate a nickname for a caught Pokemon.

        Args:
            species: Pokemon species name (e.g. "WEEDLE")
            team_names: list of (species, nickname) for current team

        Returns:
            str: suggested nickname (max 10 chars, uppercase)
        """
        lines = [f"Pokemon caught: {species}"]

        # Evolution info
        evo_line = EVOLUTION_LINES.get(species.upper())
        if evo_line:
            lines.append(f"Evolution line: {' → '.join(evo_line)}")
        else:
            lines.append("This Pokemon does not evolve.")

        # Team context
        if team_names:
            lines.append("Current team nicknames (DO NOT reuse):")
            for sp, nick in team_names:
                lines.append(f"  - {sp}: {nick}")
        else:
            lines.append("This is the first Pokemon on the team!")

        prompt = "\n".join(lines)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        _log.log_think(f"[Naming prompt]\n{prompt}")
        response = self._llm.invoke(messages)
        name = self._parse_name(response.content)

        # Print AI reasoning
        for line in response.content.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                reasoning = line.strip()[6:].strip()
                _log.log_think(reasoning)

        _log.log_think(f"Nickname → {name}")
        return name

    def _parse_name(self, text):
        """Extract the name from the LLM response."""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("NAME:"):
                name = line[5:].strip().upper()
                # Remove any non-allowed characters
                allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                name = "".join(c for c in name if c in allowed)
                # Enforce 10 char limit
                return name[:10].strip()

        # Fallback: return species name
        return ""
