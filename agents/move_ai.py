"""Move Learning AI — decides whether to learn a new move or keep existing ones.

When a Pokemon tries to learn a 5th move, this agent evaluates the new move
against the current moveset and decides which move to forget (if any).
"""

from langchain_core.messages import SystemMessage, HumanMessage
from data.pokemon_data import enrich_move
from adapters.display.console import format_move
from adapters.display.ai_logger import AILogger

_log = AILogger("MOVE")

SYSTEM_PROMPT = """\
You are a Pokemon move advisor. A Pokemon is trying to learn a new move but \
already knows 4 moves. Decide whether to forget an existing move or skip learning.

Key concepts:
- Power (Pow): Higher = more damage. Pow 0 means the move deals no direct damage.
- PP: How many times the move can be used before needing to restore it.
- Category: "physical" uses Attack stat, "special" uses Special stat, "status" has effects only.
- Status moves (Pow 0) can still be valuable (stat boosts, status effects, healing).

Consider:
- A move with higher Power is generally better for dealing damage.
- Type coverage: having moves of different types lets you hit more enemies effectively.
- Don't keep two moves of the same type unless one is clearly superior.
- PP matters: a strong move with very low PP may not be practical.
- Status moves are situational — keep at most one unless they're very strong.

Respond with EXACTLY one of these formats:
THINK: <brief reasoning>
ACTION: FORGET <move name to delete>

THINK: <brief reasoning>
ACTION: KEEP"""


HM_LEARNER_PROMPT = """\
You are a Pokemon Red team manager. The team can learn an HM move, which is \
needed to get through the world (CUT clears small trees, SURF crosses water...). \
Choose which Pokemon should learn it.

In Pokemon Red an HM move can NEVER be forgotten once learned: it permanently \
takes one of the four move slots. Consider:
- A Pokemon with a free move slot loses nothing.
- Otherwise prefer one whose weakest move matters least, or one that is not \
your main battler.
- Only one Pokemon needs to know it.

Respond with EXACTLY this format:
THINK: <brief reasoning>
ACTION: TEACH <number> or ACTION: NONE"""


class MoveAI:
    def __init__(self, llm):
        self._llm = llm

    def decide(self, species, new_move, current_moves):
        """Decide whether to learn a new move.

        Args:
            species: Pokemon species name (e.g. "CHARMELEON")
            new_move: dict with keys: name, power, pp, category, desc
            current_moves: list of dicts with keys: name, power, pp, category, desc

        Returns:
            str: move name to forget, or "" to keep current moveset
        """
        lines = [f"Pokemon: {species}", ""]
        lines.append(f"New move: {format_move(new_move)}")
        lines.append("")
        lines.append("Current moves:")
        for i, move in enumerate(current_moves, 1):
            lines.append(f"  {i}. {format_move(move)}")

        prompt = "\n".join(lines)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        _log.log_prompt("MOVE", SYSTEM_PROMPT, prompt)

        for attempt in range(3):
            _log.start_thinking()
            response = self._llm.invoke(messages)
            content = response.content or ""
            _log.stop_thinking()
            _log.log_response("MOVE", content)
            result = self._parse_response(content, current_moves)
            if result is not None:
                if result:
                    _log.log_think(f"Forget {result} → learn {new_move['name']}")
                    _log.log_stat("learned")
                else:
                    _log.log_think(f"Keep current moves, skip {new_move['name']}")
                    _log.log_stat("skipped")
                return result
            _log.log_retry()
            messages.append(response)
            messages.append(HumanMessage(
                content="ERROR: Invalid response. Use: ACTION: FORGET <move name> or ACTION: KEEP"
            ))

        _log.log_think("(couldn't decide — asking user)")
        return None

    def choose_hm_learner(self, move, candidates):
        """Pick who learns an HM move.

        Args:
            move: HM move name (e.g. "CUT")
            candidates: list of (party_index, PartyMember) able to learn it

        Returns:
            int party index, or None to not teach it
        """
        hm = enrich_move(move)
        lines = [f"HM move: {format_move(hm)}", "", "Pokemon that can learn it:"]
        for n, (_, mon) in enumerate(candidates, 1):
            moves = ", ".join(mon.moves) or "none"
            lines.append(f"  {n}. {mon.nickname} ({mon.name}) Lv{mon.level} — "
                         f"moves ({len(mon.moves)}/4): {moves}")
        prompt = "\n".join(lines)
        messages = [SystemMessage(content=HM_LEARNER_PROMPT),
                    HumanMessage(content=prompt)]
        _log.log_prompt("HM", HM_LEARNER_PROMPT, prompt)
        for _ in range(3):
            _log.start_thinking()
            response = self._llm.invoke(messages)
            content = response.content or ""
            _log.stop_thinking()
            _log.log_response("HM", content)
            for line in content.strip().split("\n"):
                line = line.strip()
                if line.startswith("THINK:"):
                    _log.log_think(line[6:].strip())
                if not line.startswith("ACTION:"):
                    continue
                action = line[7:].strip().upper()
                if action == "NONE":
                    _log.log_think(f"Don't teach {move}")
                    return None
                if action.startswith("TEACH"):
                    try:
                        n = int(action[5:].strip())
                    except ValueError:
                        continue
                    if 1 <= n <= len(candidates):
                        slot, mon = candidates[n - 1]
                        _log.log_think(f"Teach {move} to {mon.nickname}")
                        return slot
            _log.log_retry()
            messages.append(response)
            messages.append(HumanMessage(
                content=f"ERROR: Use ACTION: TEACH <1-{len(candidates)}> or ACTION: NONE"))
        return None

    def _parse_response(self, text, current_moves):
        """Parse LLM response. Returns move name to forget, "" to keep, None on failure."""
        move_names = {m["name"].upper() for m in current_moves}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line.startswith("ACTION:"):
                continue
            action = line[7:].strip()
            if action.upper() == "KEEP":
                return ""
            if action.upper().startswith("FORGET"):
                name = action[6:].strip().upper()
                if name in move_names:
                    return name
                # Fuzzy match: find the closest move name
                for mn in move_names:
                    if mn in name or name in mn:
                        return mn
        return None
