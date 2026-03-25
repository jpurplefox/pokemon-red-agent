"""Naming AI — uses a local LLM to generate creative Pokemon nicknames.

Considers the Pokemon's species, evolution line, potential, and existing
team nicknames to avoid duplicates.  Names are limited to 10 characters
(Pokemon Red constraint).
"""

from langchain_core.messages import SystemMessage, HumanMessage
from data.constants import EVOLUTION_LINES
from adapters.display.ai_logger import AILogger

_log = AILogger("NAME")

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

        _log.log_prompt("NAMING", SYSTEM_PROMPT, prompt)

        for attempt in range(3):
            response = self._llm.invoke(messages)
            content = response.content or ""
            name = self._parse_name(content)
            _log.log_response("NAMING", content)
            if name:
                _log.log_think(f"Nickname → {name}")
                return name
            _log.log_retry()
            messages.append(response)
            messages.append(HumanMessage(
                content="ERROR: Invalid response. Respond with exactly: NAME: <nickname>"
            ))

        # All retries failed — return None for manual naming
        _log.log_think("(couldn't generate name — asking user)")
        return None

    def _parse_name(self, text):
        """Extract the name from the LLM response. Returns empty string on failure."""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("NAME:"):
                name = line[5:].strip().upper()
                allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                name = "".join(c for c in name if c in allowed)
                return name[:10].strip()
        return ""
