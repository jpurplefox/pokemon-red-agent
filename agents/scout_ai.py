"""Scout AI — decides whether to catch a wild Pokemon.

Analyzes the wild Pokemon's species, type, evolution potential, and
compares against the trainer's current team to maintain type diversity
and avoid redundancy.
"""

from langchain_core.messages import SystemMessage, HumanMessage
from data.pokemon_data import POKEMON_TYPES
from agents.naming_ai import EVOLUTION_LINES
from adapters.display.ai_logger import AILogger

_log = AILogger("SCOUT")


SYSTEM_PROMPT = """\
You are a Pokemon Red team-building strategist. A wild Pokemon appeared and \
you must decide: CATCH it or DEFEAT it.

Your priorities:
1. TYPE DIVERSITY: Build a balanced team covering many types. \
Having 2 Pokemon of the same type is wasteful.
2. EVOLUTION POTENTIAL: Pokemon that evolve into powerful forms are worth catching. \
A Magikarp evolves into Gyarados! A Caterpie into Butterfree.
3. AVOID DUPLICATES: Never catch a Pokemon you already have (same species or \
same evolution line).
4. TEAM SIZE: A full team is 6 Pokemon. If you have fewer than 6, lean toward catching.
5. UPGRADE POTENTIAL: If the wild Pokemon is strictly better than a team member \
of the same type, consider catching as a replacement.

Respond with EXACTLY this format:
THINK: <1-2 sentences analyzing the Pokemon's value for the team>
DECISION: CATCH or DEFEAT"""


class ScoutAI:
    def __init__(self, llm):
        self._llm = llm

    def should_catch(self, enemy_name, enemy_level, team):
        """Decide whether to catch a wild Pokemon.

        Args:
            enemy_name: species name (e.g. "PIDGEY")
            enemy_level: int
            team: list of dicts with 'name' and 'level' keys

        Returns:
            bool: True if the AI recommends catching
        """
        # Hard override: never catch duplicates from the same evolution line
        if team:
            enemy_evo = EVOLUTION_LINES.get(enemy_name.upper())
            if enemy_evo:
                enemy_line = tuple(enemy_evo)
                for mon in team:
                    team_evo = EVOLUTION_LINES.get(mon['name'].upper())
                    if team_evo and tuple(team_evo) == enemy_line:
                        _log.log_think(f"Already have {mon['name']} from the "
                                  f"{' → '.join(enemy_evo)} line. SKIP!")
                        _log.log_think("Decision: DEFEAT ⚔️")
                        return False

        prompt = self._build_prompt(enemy_name, enemy_level, team)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        _log.log_think(f"[Scout prompt]\n{prompt}")
        response = self._llm.invoke(messages)
        decision = self._parse_decision(response.content)

        # Print reasoning
        for line in response.content.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                _log.log_think(line.strip()[6:].strip())

        if decision:
            _log.log_think("Decision: CATCH! 🔴")
        else:
            _log.log_think("Decision: DEFEAT ⚔️")

        return decision

    def _build_prompt(self, enemy_name, enemy_level, team):
        lines = []

        # Wild Pokemon info
        e_types = POKEMON_TYPES.get(enemy_name.upper(), "Unknown")
        lines.append(f"Wild Pokemon: {enemy_name} (Lv{enemy_level}) — Type: {e_types}")

        # Evolution info
        evo_line = EVOLUTION_LINES.get(enemy_name.upper())
        if evo_line:
            lines.append(f"Evolution line: {' → '.join(evo_line)}")
        else:
            lines.append("This Pokemon does not evolve.")

        # Current team
        if team:
            lines.append(f"\nYour team ({len(team)}/6):")
            for mon in team:
                t = POKEMON_TYPES.get(mon['name'].upper(), "?")
                evo = EVOLUTION_LINES.get(mon['name'].upper())
                evo_str = f" (evolves: {' → '.join(evo)})" if evo else ""
                lines.append(f"  - {mon['name']} Lv{mon['level']} — Type: {t}{evo_str}")

            # Summarize types on team
            team_types = set()
            for mon in team:
                t = POKEMON_TYPES.get(mon['name'].upper(), "")
                for single_type in t.split("/"):
                    if single_type.strip():
                        team_types.add(single_type.strip())
            lines.append(f"Team types covered: {', '.join(sorted(team_types))}")

            # Check for duplicate evolution lines
            team_evo_lines = set()
            for mon in team:
                evo = EVOLUTION_LINES.get(mon['name'].upper())
                if evo:
                    team_evo_lines.add(tuple(evo))
            enemy_evo = EVOLUTION_LINES.get(enemy_name.upper())
            if enemy_evo and tuple(enemy_evo) in team_evo_lines:
                lines.append("⚠️ You already have a Pokemon from this evolution line!")

            # Check type overlap
            new_types = set()
            e_type_str = POKEMON_TYPES.get(enemy_name.upper(), "")
            for t in e_type_str.split("/"):
                if t.strip():
                    new_types.add(t.strip())
            overlap = new_types & team_types
            new = new_types - team_types
            if overlap:
                lines.append(f"⚠️ Type overlap with team: {', '.join(overlap)}")
            if new:
                lines.append(f"✅ New types for team: {', '.join(new)}")
        else:
            lines.append("\nYour team is EMPTY! Catch everything you can.")

        return "\n".join(lines)

    def _parse_decision(self, text):
        """Parse the LLM response into a catch/defeat decision."""
        for line in text.strip().split("\n"):
            line = line.strip().upper()
            if line.startswith("DECISION:"):
                return "CATCH" in line
        # Default: defeat (conservative)
        return False
