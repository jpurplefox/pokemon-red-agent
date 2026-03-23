"""Battle Reflect AI — extracts type effectiveness facts from battles.

Analyzes post-battle logs to learn type matchups (super effective,
not very effective) and persists them to battle_memory.json.
This memory is shared with BattleAI for better decision-making.
"""

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import SystemMessage, HumanMessage

from adapters.display.ai_logger import AILogger

_GREEN = "\033[32m"
_RESET = "\033[0m"

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES),
                   keep_trailing_newline=True)

_log = AILogger("BATTLE-REFLECT")


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


class BattleReflectAI:
    """Analyzes battle logs and extracts type effectiveness knowledge."""

    def __init__(self, llm):
        self._llm = llm
        self._memory_file = Path("battle_memory.json")
        self._memory = self._load_memory()

    def _load_memory(self):
        """Load type effectiveness memory from disk."""
        if self._memory_file.exists():
            try:
                data = json.loads(self._memory_file.read_text())
                print(f"  Loaded {len(data)} battle memory facts from {self._memory_file}")
                return data
            except (json.JSONDecodeError, KeyError):
                pass
        return []

    def _save_memory(self):
        """Persist memory to disk."""
        self._memory_file.write_text(json.dumps(self._memory, indent=2))

    def get_memory(self):
        """Return all known type effectiveness facts."""
        return self._memory

    def get_memory_text(self):
        """Return memory as human-readable lines for prompts."""
        lines = []
        for fact in self._memory:
            eff = fact["effectiveness"]
            lines.append(f"- {fact['move_type']} moves are {eff} against {fact['vs_type']}")
        return lines

    def reflect(self, history, battle_type, result, enemy_name,
                iteration=0):
        """Analyze a completed battle and extract new type effectiveness facts.

        Returns list of newly learned facts (may be empty).
        """
        if not history:
            return []

        existing_text = self.get_memory_text()

        system_prompt = _render("battle_recap.j2",
                                known_facts=existing_text)
        user_prompt = _render("battle_recap_state.j2",
                              battle_type=battle_type,
                              result=result,
                              history=history)

        _log.log_prompt("BATTLE-REFLECT", system_prompt, user_prompt)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self._llm.invoke(messages)
        text = response.content.strip()

        _log.log_response("BATTLE-REFLECT", text)

        # Parse LESSONS
        new_facts = []
        in_lessons = False
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("LESSONS:"):
                rest = stripped[8:].strip()
                if rest.lower() == "none":
                    _log.log_think("--- Battle Reflect: nothing new learned ---")
                    return []
                in_lessons = True
                if rest.startswith("-"):
                    fact = self._parse_fact(rest[1:].strip(), iteration)
                    if fact:
                        new_facts.append(fact)
                continue
            if in_lessons and stripped.startswith("-"):
                fact = self._parse_fact(stripped[1:].strip(), iteration)
                if fact:
                    new_facts.append(fact)

        # Save new facts
        if new_facts:
            _log.log_stat("facts", len(new_facts))
            _log.log_think("--- Battle Reflect: new facts learned ---")
            for fact in new_facts:
                eff = fact["effectiveness"]
                msg = f"💡 {fact['move_type']} → {fact['vs_type']}: {eff}"
                _log.log_think(msg)
                print(f"  {_GREEN}BATTLE: {msg}{_RESET}")
            self._memory.extend(new_facts)
            self._save_memory()
        else:
            _log.log_think("--- Battle Reflect: nothing new learned ---")

        return new_facts

    def _parse_fact(self, text, iteration):
        """Parse a lesson line into a structured fact dict.

        Expected formats:
          "Water moves are super effective against Rock/Ground"
          "Normal moves are not very effective against Rock"
        """
        text_lower = text.lower()

        # Detect effectiveness
        if "super effective" in text_lower:
            effectiveness = "super effective"
        elif "not very effective" in text_lower:
            effectiveness = "not very effective"
        elif "no effect" in text_lower:
            effectiveness = "no effect"
        else:
            return None  # Not a type effectiveness fact

        # Extract move type (before "moves are")
        move_type = ""
        for marker in ["moves are", "type moves are", "type is", "attacks are"]:
            idx = text_lower.find(marker)
            if idx > 0:
                move_type = text[:idx].strip()
                break

        # Extract vs type (after "against")
        vs_type = ""
        idx = text_lower.find("against")
        if idx > 0:
            vs_type = text[idx + 7:].strip().rstrip(".")

        if not move_type or not vs_type:
            return None

        # Capitalize types
        move_type = move_type.title()
        vs_type = vs_type.title()

        # Check for duplicates
        for existing in self._memory:
            if (existing["move_type"].lower() == move_type.lower() and
                    existing["vs_type"].lower() == vs_type.lower()):
                return None  # Already known

        return {
            "move_type": move_type,
            "vs_type": vs_type,
            "effectiveness": effectiveness,
            "learned_at": iteration,
        }
