"""Battle AI — uses a local LLM via LangChain to decide battle actions.

Sends battle state (both pokemon stats, moves, PP) to a local Qwen model
running on Ollama. The model reasons about the best action: fight with a
specific move, or run if the situation is hopeless.
"""

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from pokemon_data import POKEMON_TYPES, MOVE_TYPES

SYSTEM_PROMPT = """\
You are a Pokemon Red battle strategist. You receive the current battle state \
and must decide the best action.

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


class BattleAI:
    def __init__(self, base_url="http://localhost:11434", model="qwen2.5:3b"):
        self._llm = ChatOllama(
            base_url=base_url,
            model=model,
            temperature=0.3,
        )

    def decide(self, player, enemy, is_wild):
        """Decide a battle action given both pokemon's stats.

        Args:
            player: dict with name, level, hp, max_hp, status, moves
            enemy:  dict with name, level, hp, max_hp, status, moves
            is_wild: bool

        Returns:
            tuple: ("move", move_name) or ("run", None)
        """
        prompt = self._build_prompt(player, enemy, is_wild)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = self._llm.invoke(messages)
        action = self._parse_response(response.content, player)

        # Hard override: never RUN in trainer battles
        if not is_wild and action[0] == "run":
            available = [m[0] for m in player['moves'] if m[1] > 0]
            if available:
                print("  AI: (can't run from trainer, forcing attack)")
                return ("move", available[0])

        return action

    def _build_prompt(self, player, enemy, is_wild):
        battle_type = "Wild" if is_wild else "Trainer (CANNOT RUN)"
        lines = [f"Battle type: {battle_type}"]

        # Enemy info with types
        e_status = f" [{enemy['status']}]" if enemy['status'] else ""
        e_types = POKEMON_TYPES.get(enemy['name'].upper(), "")
        e_type_str = f" ({e_types})" if e_types else ""
        lines.append(
            f"Enemy: {enemy['name']}{e_type_str} Lv{enemy['level']} "
            f"HP: {enemy['hp']}/{enemy['max_hp']}{e_status}"
        )

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

        return "\n".join(lines)

    def _parse_response(self, text, player):
        """Parse the LLM response into an action tuple."""
        # Print the AI's reasoning
        for line in text.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                reasoning = line.strip()[6:].strip()
                print(f"  AI: {reasoning}")

        # Find the ACTION line
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line[7:].strip()
                if action == "RUN":
                    return ("run", None)
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
                        print(f"  AI: (couldn't match '{move_name}', using {available[0]})")
                        return ("move", available[0])

        # Fallback: use first move with PP
        available = [m[0] for m in player['moves'] if m[1] > 0]
        if available:
            print("  AI: (couldn't parse response, using first move)")
            return ("move", available[0])
        return ("run", None)
