"""Battle AI — uses a local LLM via LangChain to decide battle actions.

Sends battle state (both pokemon stats, moves, PP) to a local Qwen model
running on Ollama. The model reasons about the best action: fight with a
specific move, throw a ball, switch pokemon, or run.

Prompts are managed as Jinja2 templates in the templates/ directory.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from pokemon_data import POKEMON_TYPES, MOVE_TYPES

_PURPLE = "\033[35m"
_RESET = "\033[0m"

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), trim_blocks=True,
                   lstrip_blocks=True)


def _ai_print(msg):
    print(f"{_PURPLE}  AI: {msg}{_RESET}")


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


class BattleAI:
    def __init__(self, base_url="http://localhost:11434", model="qwen2.5:3b",
                 scout=None):
        self._llm = ChatOllama(
            base_url=base_url,
            model=model,
            temperature=0.3,
        )
        self._goal = None  # "defeat" or "catch"
        self._scout = scout
        self._team = []  # [{name, level, ...}] — updated from battle data
        self._history = []  # list of {"text": str, "player_hp": str, "enemy_hp": str}

    def set_team(self, team, active_idx=None):
        """Update the current team roster for scout decisions."""
        self._team = team
        self._active_idx = active_idx

    def add_turn(self, text, player_hp, player_max_hp, enemy_hp, enemy_max_hp):
        """Record what happened in a turn for context in the next decision."""
        if not text or not text.strip():
            return
        # Calculate damage dealt/received compared to previous turn
        if self._history:
            prev = self._history[-1]
            prev_player_hp = prev["_player_hp"]
            prev_enemy_hp = prev["_enemy_hp"]
        else:
            prev_player_hp = player_max_hp
            prev_enemy_hp = enemy_max_hp
        dmg_to_enemy = prev_enemy_hp - enemy_hp
        dmg_to_player = prev_player_hp - player_hp
        parts = []
        if dmg_to_enemy > 0:
            parts.append(f"You dealt {dmg_to_enemy} dmg")
        if dmg_to_player > 0:
            parts.append(f"You took {dmg_to_player} dmg")
        self._history.append({
            "text": text.strip(),
            "damage": ", ".join(parts) if parts else "No damage",
            "_player_hp": player_hp,
            "_enemy_hp": enemy_hp,
        })

    def on_battle_start(self, player, enemy, is_wild, balls=None):
        """Called at the start of a new battle to set the goal."""
        self._history = []
        self._goal = "defeat"
        if is_wild:
            has_balls = balls and any(c > 0 for _, c, _ in balls)
            _ai_print(f"A wild {enemy['name']} (Lv{enemy['level']}) appeared!")
            if has_balls and self._scout:
                should_catch = self._scout.should_catch(
                    enemy['name'], enemy['level'], self._team
                )
                if should_catch:
                    self._goal = "catch"
                    _ai_print(f"Goal: CATCH {enemy['name']}!")
                else:
                    _ai_print(f"Goal: DEFEAT {enemy['name']}!")
            elif has_balls:
                choice = input(f"{_PURPLE}  AI: Fight or catch? [f/c]: {_RESET}").strip().lower()
                if choice.startswith("c"):
                    self._goal = "catch"
                    _ai_print(f"Goal: CATCH {enemy['name']}!")
                else:
                    _ai_print(f"Goal: DEFEAT {enemy['name']}!")
            else:
                _ai_print("No Poke Balls — going for the win!")

    def choose_switch_in(self, party, alive_indices, is_wild):
        """Choose which pokemon to send after one fainted.

        Picks the highest-level alive pokemon. In wild battles, could
        return -1 to run, but AI always fights.
        """
        best_idx = alive_indices[0]
        best_level = 0
        for i in alive_indices:
            if party[i]['level'] > best_level:
                best_level = party[i]['level']
                best_idx = i
        label = party[best_idx]['nickname']
        if party[best_idx]['nickname'] != party[best_idx]['name']:
            label = f"{party[best_idx]['name']} ({party[best_idx]['nickname']})"
        _ai_print(f"Sending out {label} Lv{best_level}!")
        return best_idx

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def decide(self, player, enemy, is_wild, balls=None):
        """Decide a battle action given both pokemon's stats.

        Returns:
            tuple: ("move", move_name), ("run", None),
                   ("ball", bag_index), or ("switch", party_idx)
        """
        # If catching and no balls left, switch to defeat
        if self._goal == "catch" and (not balls or all(c == 0 for _, c, _ in balls)):
            _ai_print("No Poke Balls left! Switching to defeat.")
            self._goal = "defeat"

        system_prompt = self._render_system()
        user_prompt = self._render_state(player, enemy, is_wild, balls)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = self._llm.invoke(messages)
        action = self._parse_response(response.content, player, balls)

        # Hard override: never RUN in trainer battles
        if not is_wild and action[0] == "run":
            available = [m[0] for m in player['moves'] if m[1] > 0]
            if available:
                _ai_print("(can't run from trainer, forcing attack)")
                action = ("move", available[0])

        # Hard override: if catching and enemy HP <= 50%, force ball throw
        if self._goal == "catch" and action[0] != "ball" and balls:
            hp_pct = round(enemy['hp'] / enemy['max_hp'] * 100) if enemy['max_hp'] else 100
            if hp_pct <= 50:
                for name, count, bag_idx in balls:
                    if count > 0:
                        _ai_print("(enemy HP low, forcing Poke Ball!)")
                        action = ("ball", bag_idx)
                        break

        self._log_action(action)
        return action

    # ------------------------------------------------------------------
    # Template rendering
    # ------------------------------------------------------------------

    def _render_system(self):
        """Render the system prompt based on the current goal."""
        template = ("battle_system_catch.j2"
                    if self._goal == "catch"
                    else "battle_system_defeat.j2")
        actions = self._available_actions()
        return _render(template, actions=actions)

    def _available_actions(self):
        """List of action format strings for the response format template."""
        if self._goal == "catch":
            return ["BALL", "MOVE:name", "SWITCH:nickname"]
        return ["MOVE:name", "RUN", "SWITCH:nickname"]

    def _render_state(self, player, enemy, is_wild, balls=None):
        """Render the battle state user prompt."""
        # Enemy data
        e_types = POKEMON_TYPES.get(enemy['name'].upper(), "")
        hp_pct = round(enemy['hp'] / enemy['max_hp'] * 100) if enemy['max_hp'] else 0
        enemy_data = {
            "name": enemy['name'], "types": e_types,
            "level": enemy['level'],
            "hp": enemy['hp'], "max_hp": enemy['max_hp'],
            "hp_pct": hp_pct,
            "status": enemy.get('status', ''),
        }

        # Player data with typed moves
        p_types = POKEMON_TYPES.get(player['name'].upper(), "")
        moves = []
        for name, pp, max_pp in player['moves']:
            m_type = MOVE_TYPES.get(name.upper(), "")
            moves.append({"name": name, "type": m_type,
                          "pp": pp, "max_pp": max_pp})
        player_data = {
            "name": player['name'], "types": p_types,
            "level": player['level'],
            "hp": player['hp'], "max_hp": player['max_hp'],
            "status": player.get('status', ''),
            "moves": moves,
        }

        # Balls
        ball_strs = []
        if balls:
            ball_strs = [f"{n} x{c}" for n, c, _ in balls if c > 0]

        # Switchable party members (skip active by index, skip fainted)
        switchable = []
        for i, mon in enumerate(self._team):
            if i == self._active_idx:
                continue
            if mon['hp'] <= 0:
                continue
            nick = mon['nickname']
            label = (f"{mon['name']} ({nick})"
                     if nick != mon['name'] else nick)
            m_types = POKEMON_TYPES.get(mon['name'].upper(), "")
            switchable.append({
                "label": label, "types": m_types,
                "level": mon['level'],
                "hp": mon['hp'], "max_hp": mon['max_hp'],
            })

        battle_type = "Wild" if is_wild else "Trainer (CANNOT RUN)"
        goal = self._goal.upper() if self._goal else None

        return _render("battle_state.j2",
                       battle_type=battle_type, goal=goal,
                       enemy=enemy_data, player=player_data,
                       balls=ball_strs, switchable=switchable,
                       history=self._history)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

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
                        for name, count, bag_idx in balls:
                            if count > 0:
                                return ("ball", bag_idx)
                    _ai_print("(no balls available, attacking instead)")
                if action.startswith("SWITCH:"):
                    target = action[7:].strip()
                    for i, mon in enumerate(self._team):
                        if (mon['name'] == player['name']
                                and mon['hp'] == player['hp']):
                            continue
                        if mon['hp'] <= 0:
                            continue
                        if (target.upper() in mon['nickname'].upper()
                                or target.upper() in mon['name'].upper()):
                            return ("switch", i)
                    _ai_print(f"(couldn't match '{target}' in party, attacking)")
                if action.startswith("MOVE:"):
                    move_name = action[5:].strip()
                    available = [m[0] for m in player['moves'] if m[1] > 0]
                    for m in available:
                        if m.upper() == move_name.upper():
                            return ("move", m)
                    for m in available:
                        if move_name.upper() in m.upper():
                            return ("move", m)
                    if available:
                        _ai_print(f"(couldn't match '{move_name}', using {available[0]})")
                        return ("move", available[0])

        # Fallback: use first move with PP
        available = [m[0] for m in player['moves'] if m[1] > 0]
        if available:
            _ai_print("(couldn't parse response, using first move)")
            return ("move", available[0])
        return ("run", None)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_action(self, action):
        if action[0] == "run":
            _ai_print("chose: RUN")
        elif action[0] == "ball":
            _ai_print("chose: throw Poke Ball! \U0001f534")
        elif action[0] == "switch":
            mon = self._team[action[1]]
            label = (mon['nickname'] if mon['nickname'] == mon['name']
                     else f"{mon['name']} ({mon['nickname']})")
            _ai_print(f"chose: SWITCH to {label}! \U0001f504")
        else:
            _ai_print(f"chose: {action[1]}")
