"""Battle AI — uses a local LLM via LangChain to decide battle actions.

Sends battle state (both pokemon stats, moves, PP) to a local Qwen model
running on Ollama. The model reasons about the best action: fight with a
specific move, or run if the situation is hopeless.
"""

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from pokemon_data import POKEMON_TYPES, MOVE_TYPES

_PURPLE = "\033[35m"
_RESET = "\033[0m"


def _ai_print(msg):
    print(f"{_PURPLE}  AI: {msg}{_RESET}")

SYSTEM_PROMPT_DEFEAT = """\
You are a Pokemon Red battle strategist. Your goal is to DEFEAT the enemy pokemon.

Rules:
- Prioritize winning. Only suggest RUN as a last resort in wild battles \
when your pokemon is very likely to faint and cannot deal meaningful damage.
- Use type advantages! Water beats Fire/Ground/Rock, Fire beats Grass/Ice/Bug, \
Grass beats Water/Ground/Rock, Electric beats Water/Flying, etc.
- You can only use moves that have PP > 0.
- IMPORTANT: If the battle type is "Trainer", you CANNOT run. You must pick a move.

Respond with EXACTLY this format (no extra text):
THINK: <your brief reasoning in 1-2 sentences>
ACTION: <MOVE:name or RUN>

Examples:
THINK: Enemy Geodude is Rock/Ground type. My Squirtle's BUBBLE is Water type, super effective!
ACTION: MOVE:BUBBLE

THINK: My pokemon is at 3 HP against a much stronger wild opponent, better flee.
ACTION: RUN"""

SYSTEM_PROMPT_CATCH = """\
You are a Pokemon Red battle strategist. Your goal is to CATCH the wild pokemon.

Rules:
- DEFAULT ACTION: throw a Poké Ball (ACTION: BALL). Always prefer this.
- Only attack if you are CERTAIN the enemy can survive the hit. If in doubt, throw a ball.
- LEVEL DIFFERENCE MATTERS: if your pokemon is 3+ levels higher, even a normal move \
can one-shot a low-level enemy. In that case, just throw the ball directly.
- NEVER use super-effective moves — they will likely KO the enemy and ruin the catch.
- NEVER use status moves (TAIL WHIP, LEER, GROWL) — they waste turns and don't help catching.
- You can only use moves that have PP > 0.

Respond with EXACTLY this format (no extra text):
THINK: <your brief reasoning in 1-2 sentences>
ACTION: <BALL or MOVE:name>

Examples:
THINK: Enemy is at full HP but I have balls, better just try catching it directly.
ACTION: BALL

THINK: Enemy Pidgey Lv3 is at 100% HP and my Lv15 pokemon would one-shot it. Let me just throw a ball.
ACTION: BALL

THINK: Enemy Onix Lv12 has very high HP at 100%. One TACKLE won't KO it, safe to weaken.
ACTION: MOVE:TACKLE"""


class BattleAI:
    def __init__(self, base_url="http://localhost:11434", model="qwen2.5:3b"):
        self._llm = ChatOllama(
            base_url=base_url,
            model=model,
            temperature=0.3,
        )
        self._goal = None  # "defeat" or "catch"

    def on_battle_start(self, player, enemy, is_wild, balls=None):
        """Called at the start of a new battle to set the goal."""
        self._goal = "defeat"
        if is_wild:
            has_balls = balls and any(c > 0 for _, c, _ in balls)
            _ai_print(f"A wild {enemy['name']} (Lv{enemy['level']}) appeared!")
            if has_balls:
                choice = input(f"{_PURPLE}  AI: Fight or catch? [f/c]: {_RESET}").strip().lower()
                if choice.startswith("c"):
                    self._goal = "catch"
                    _ai_print(f"Goal: CATCH {enemy['name']}! Will weaken first, then throw ball.")
                else:
                    _ai_print(f"Goal: DEFEAT {enemy['name']}!")
            else:
                _ai_print("No Poké Balls — going for the win!")

    def decide(self, player, enemy, is_wild, balls=None):
        """Decide a battle action given both pokemon's stats.

        Args:
            player: dict with name, level, hp, max_hp, status, moves
            enemy:  dict with name, level, hp, max_hp, status, moves
            is_wild: bool
            balls: list of (name, count, bag_index) or None

        Returns:
            tuple: ("move", move_name), ("run", None), or ("ball", bag_index)
        """
        # If catching and no balls left, switch to defeat
        if self._goal == "catch" and (not balls or all(c == 0 for _, c, _ in balls)):
            _ai_print("No Poké Balls left! Switching to defeat.")
            self._goal = "defeat"

        system_prompt = SYSTEM_PROMPT_CATCH if self._goal == "catch" else SYSTEM_PROMPT_DEFEAT
        prompt = self._build_prompt(player, enemy, is_wild, balls)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]

        response = self._llm.invoke(messages)
        action = self._parse_response(response.content, player, balls)

        # Hard override: never RUN in trainer battles
        if not is_wild and action[0] == "run":
            available = [m[0] for m in player['moves'] if m[1] > 0]
            if available:
                _ai_print("(can't run from trainer, forcing attack)")
                action = ("move", available[0])

        # Hard override: if catching and enemy HP ≤ 50%, force ball throw
        if self._goal == "catch" and action[0] != "ball" and balls:
            hp_pct = round(enemy['hp'] / enemy['max_hp'] * 100) if enemy['max_hp'] else 100
            if hp_pct <= 50:
                for name, count, bag_idx in balls:
                    if count > 0:
                        _ai_print("(enemy HP low, forcing Poké Ball!)")
                        action = ("ball", bag_idx)
                        break

        if action[0] == "run":
            _ai_print("chose: RUN")
        elif action[0] == "ball":
            _ai_print("chose: throw Poké Ball! 🔴")
        else:
            _ai_print(f"chose: {action[1]}")

        return action

    def _build_prompt(self, player, enemy, is_wild, balls=None):
        battle_type = "Wild" if is_wild else "Trainer (CANNOT RUN)"
        lines = [f"Battle type: {battle_type}"]
        if self._goal:
            lines.append(f"Goal: {self._goal.upper()} the enemy")

        # Enemy info with types
        e_status = f" [{enemy['status']}]" if enemy['status'] else ""
        e_types = POKEMON_TYPES.get(enemy['name'].upper(), "")
        e_type_str = f" ({e_types})" if e_types else ""
        hp_pct = round(enemy['hp'] / enemy['max_hp'] * 100) if enemy['max_hp'] else 0
        lines.append(
            f"Enemy: {enemy['name']}{e_type_str} Lv{enemy['level']} "
            f"HP: {enemy['hp']}/{enemy['max_hp']} ({hp_pct}%){e_status}"
        )
        # Explicit hint for catch mode so the small model acts on HP%
        if self._goal == "catch":
            if hp_pct <= 50:
                lines.append(">>> Enemy HP is LOW — throw a Poké Ball NOW! <<<")
            elif hp_pct <= 75:
                lines.append(">>> Enemy is weakened, consider throwing a ball. <<<")
            else:
                lines.append(">>> Enemy HP is high, weaken it with a damage move. <<<")

        # Player info with types
        p_status = f" [{player['status']}]" if player['status'] else ""
        p_types = POKEMON_TYPES.get(player['name'].upper(), "")
        p_type_str = f" ({p_types})" if p_types else ""
        lines.append(
            f"Your: {player['name']}{p_type_str} Lv{player['level']} "
            f"HP: {player['hp']}/{player['max_hp']}{p_status}"
        )

        # Player moves with types
        lines.append("Your moves:")
        for name, pp, max_pp in player['moves']:
            m_type = MOVE_TYPES.get(name.upper(), "")
            type_str = f" [{m_type}]" if m_type else ""
            lines.append(f"  - {name}{type_str} ({pp}/{max_pp} PP)")

        # Poké Balls
        if balls:
            ball_str = ", ".join(f"{n} ×{c}" for n, c, _ in balls if c > 0)
            if ball_str:
                lines.append(f"Poké Balls: {ball_str}")

        return "\n".join(lines)

    def _parse_response(self, text, player, balls=None):
        """Parse the LLM response into an action tuple."""
        # Print the AI's reasoning
        for line in text.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                reasoning = line.strip()[6:].strip()
                _ai_print(reasoning)

        # Find the ACTION line
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line[7:].strip()
                if action == "RUN":
                    return ("run", None)
                if action == "BALL":
                    if balls:
                        # Use first available ball
                        for name, count, bag_idx in balls:
                            if count > 0:
                                return ("ball", bag_idx)
                    _ai_print("(no balls available, attacking instead)")
                if action.startswith("MOVE:"):
                    move_name = action[5:].strip()
                    # Match against available moves (fuzzy)
                    available = [m[0] for m in player['moves'] if m[1] > 0]
                    # Exact match
                    for m in available:
                        if m.upper() == move_name.upper():
                            return ("move", m)
                    # Partial match
                    for m in available:
                        if move_name.upper() in m.upper():
                            return ("move", m)
                    # Fallback: first available move
                    if available:
                        _ai_print(f"(couldn't match '{move_name}', using {available[0]})")
                        return ("move", available[0])

        # Fallback: use first move with PP
        available = [m[0] for m in player['moves'] if m[1] > 0]
        if available:
            _ai_print("(couldn't parse response, using first move)")
            return ("move", available[0])
        return ("run", None)
