"""Lead selection AI — chooses which Pokemon should lead the party after battle.

Considers HP, level disparity, and training needs to decide if the current
lead should be swapped for a teammate that needs experience.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import SystemMessage, HumanMessage
from adapters.display.ai_logger import AILogger

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), trim_blocks=True,
                   lstrip_blocks=True)

_log = AILogger("LEAD")


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


class LeadAI:
    """Decides which Pokemon should lead the party after each battle."""

    def __init__(self, llm):
        self._llm = llm

    def choose_lead(self, party):
        """Pick the best lead Pokemon index (0-based), or None if current is fine.

        Args:
            party: list of PartyMember dataclasses

        Returns:
            int index of recommended lead, or None if no change needed
        """
        if len(party) <= 1:
            return None

        # Don't bother if only one alive
        alive = [i for i, m in enumerate(party) if m.hp > 0]
        if len(alive) <= 1:
            return None

        system_prompt = _render("lead_system.j2")
        user_prompt = _render("lead_state.j2", party=party, alive=alive)

        _log.log_prompt("LEAD", system_prompt, user_prompt)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        for attempt in range(3):
            response = self._llm.invoke(messages)
            _log.log_response("LEAD", response.content)
            result = self._parse_response(response.content, party, alive)
            if result is not None:
                return result
            _log.log_retry()
            messages.append(response)
            messages.append(HumanMessage(
                content=f"ERROR: Invalid response. Pick a number from the list (1-{len(party)}), "
                        f"or say KEEP to keep the current lead."
            ))

        return None

    def _parse_response(self, text, party, alive):
        """Parse LLM response. Returns party index or None."""
        for line in text.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                _log.log_think(line.strip()[6:].strip())

        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line[7:].strip().upper()
                if action == "KEEP":
                    lead = party[0]
                    _log.log_think(f"Keeping {lead.nickname} as lead")
                    return 0
                if action.startswith("SWITCH:"):
                    try:
                        idx = int(action[7:].strip()) - 1
                        if idx in alive and idx != 0:
                            mon = party[idx]
                            _log.log_think(f"=> New lead: {mon.nickname} Lv{mon.level}")
                            return idx
                    except ValueError:
                        pass
        return None
