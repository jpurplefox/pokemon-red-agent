"""Battle AI — uses a local LLM via LangChain to decide battle actions.

Sends battle state (both pokemon stats, moves, PP) to a local Qwen model
running on Ollama. The model reasons about the best action: fight with a
specific move, throw a ball, switch pokemon, or run.

Prompts are managed as Jinja2 templates in the templates/ directory.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import SystemMessage, HumanMessage
from data.pokemon_data import POKEMON_TYPES, MOVE_TYPES, MOVE_DATA
from adapters.display.ai_logger import AILogger

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), trim_blocks=True,
                   lstrip_blocks=True)

_log = AILogger("BATTLE")


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


class BattleAI:
    def __init__(self, llm, scout=None, battle_reflect=None):
        self._llm = llm
        self._goal = None  # "defeat" or "catch"
        self._scout = scout
        self._battle_reflect = battle_reflect
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

    def get_history(self):
        """Return the battle turn history."""
        return self._history

    def on_battle_start(self, player, enemy, is_wild, balls=None):
        """Called at the start of a new battle to set the goal."""
        self._history = []
        self._goal = "defeat"
        if is_wild:
            has_balls = balls and any(c > 0 for _, c, _ in balls)
            _log.log_think(f"A wild {enemy.name} (Lv{enemy.level}) appeared!")
            if has_balls and self._scout:
                should_catch = self._scout.should_catch(
                    enemy.name, enemy.level, self._team
                )
                if should_catch:
                    self._goal = "catch"
                    _log.log_think(f"Goal: CATCH {enemy.name}!")
                else:
                    _log.log_think(f"Goal: DEFEAT {enemy.name}!")
            elif has_balls:
                choice = input(f"\033[35m  AI: Fight or catch? [f/c]: \033[0m").strip().lower()
                if choice.startswith("c"):
                    self._goal = "catch"
                    _log.log_think(f"Goal: CATCH {enemy.name}!")
                else:
                    _log.log_think(f"Goal: DEFEAT {enemy.name}!")
            else:
                _log.log_think("No Poke Balls — going for the win!")

    def on_battle_end(self, is_wild, result="unknown"):
        """Called when a battle ends. Delegates to BattleReflectAI."""
        if result == "you won":
            _log.log_stat("W")
        elif result == "you lost":
            _log.log_stat("L")
        elif result == "caught":
            _log.log_stat("C")
        if not self._history:
            return
        if self._battle_reflect:
            battle_type = "Wild" if is_wild else "Trainer"
            self._battle_reflect.reflect(
                self._history, battle_type, result,
                enemy_name="",
            )

    def choose_switch_in(self, party, alive_indices, is_wild, enemy=None):
        """Choose which pokemon to send after one fainted.

        Uses the LLM to pick the best pokemon considering type advantages
        against the enemy.  Falls back to highest-level if LLM fails or
        no enemy data is available. Returns -1 to run (wild only).
        """
        _log.log_think("--- Pokemon fainted! Who to send? ---")

        if not enemy or len(alive_indices) == 1:
            # Only one option or no enemy data — skip LLM
            idx = alive_indices[0]
            label = party[idx].nickname
            if party[idx].nickname != party[idx].name:
                label = f"{party[idx].name} ({party[idx].nickname})"
            _log.log_think(f"=> Sending out {label} Lv{party[idx].level}!")
            return idx

        # Build candidate list
        candidates = []
        for i in alive_indices:
            mon = party[i]
            nick = mon.nickname
            label = (f"{mon.name} ({nick})"
                     if nick != mon.name else nick)
            m_types = POKEMON_TYPES.get(mon.name.upper(), "")
            candidates.append({
                "label": label, "types": m_types,
                "level": mon.level,
                "hp": mon.hp, "max_hp": mon.max_hp,
            })

        # Enemy data
        e_types = POKEMON_TYPES.get(enemy.name.upper(), "")
        hp_pct = round(enemy.hp / enemy.max_hp * 100) if enemy.max_hp else 0
        enemy_data = {
            "name": enemy.name, "types": e_types,
            "level": enemy.level,
            "hp": enemy.hp, "max_hp": enemy.max_hp,
            "hp_pct": hp_pct,
            "status": enemy.status,
        }

        # Find fainted pokemon name
        fainted_name = "your pokemon"
        active = self._active_idx
        if active is not None and active < len(party):
            fainted_name = party[active].name

        battle_type = "Wild" if is_wild else "Trainer"

        system_prompt = _render("switch_in.j2", is_wild=is_wild)
        user_prompt = _render("switch_in_state.j2",
                              fainted_name=fainted_name,
                              battle_type=battle_type,
                              enemy=enemy_data,
                              candidates=candidates)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        for attempt in range(3):
            _log.start_thinking()
            response = self._llm.invoke(messages)
            _log.stop_thinking()
            choice_idx = self._parse_switch_response(
                response.content or "", party, alive_indices, is_wild
            )
            if choice_idx is not None:
                return choice_idx
            _log.log_retry()
            messages.append(response)
            names = [f"{party[i].nickname}" for i in alive_indices]
            messages.append(HumanMessage(
                content=f"ERROR: Invalid choice. Use SWITCH:<name>. "
                        f"Available: {', '.join(names)}"
            ))
        return None

    def _parse_switch_response(self, text, party, alive_indices, is_wild):
        """Parse LLM response for switch-in decision."""
        # Print reasoning
        for line in text.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                reasoning = line.strip()[6:].strip()
                _log.log_think(reasoning)

        # Find ACTION line
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line[7:].strip()

                if action == "RUN" and is_wild:
                    _log.log_think("chose: RUN!")
                    return -1

                if action.startswith("SWITCH:"):
                    target = action[7:].strip()
                    for i in alive_indices:
                        mon = party[i]
                        if (target.upper() in mon.nickname.upper()
                                or target.upper() in mon.name.upper()):
                            label = mon.nickname
                            if mon.nickname != mon.name:
                                label = f"{mon.name} ({mon.nickname})"
                            _log.log_think(f"=> Sending out {label} Lv{mon.level}!")
                            return i

        # Retry — return None to signal manual control needed
        _log.log_think("(couldn't parse switch response)")
        return None

    def choose_switch_offer(self, party, active_idx, alive_indices):
        """Decide whether to switch when given the chance between trainer mons.

        Uses the LLM to decide. Returns a party index to switch to,
        or None to stay.
        """
        _log.log_think("--- Switch before next opponent? ---")

        current = party[active_idx]
        hp_pct = round(current.hp / current.max_hp * 100) if current.max_hp else 100
        p_types = POKEMON_TYPES.get(current.name.upper(), "")
        active_data = {
            "name": current.name, "types": p_types,
            "level": current.level,
            "hp": current.hp, "max_hp": current.max_hp,
            "hp_pct": hp_pct,
        }

        candidates = []
        for i in alive_indices:
            mon = party[i]
            nick = mon.nickname
            label = (f"{mon.name} ({nick})"
                     if nick != mon.name else nick)
            m_types = POKEMON_TYPES.get(mon.name.upper(), "")
            candidates.append({
                "label": label, "types": m_types,
                "level": mon.level,
                "hp": mon.hp, "max_hp": mon.max_hp,
            })

        system_prompt = _render("switch_offer.j2")
        user_prompt = _render("switch_offer_state.j2",
                              active=active_data, candidates=candidates)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        _log.start_thinking()
        response = self._llm.invoke(messages)
        _log.stop_thinking()
        text = response.content or ""

        for line in text.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                _log.log_think(line.strip()[6:].strip())

        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line[7:].strip()
                if action == "STAY":
                    _log.log_think("=> STAY")
                    return -1
                if action.startswith("SWITCH:"):
                    target = action[7:].strip()
                    for i in alive_indices:
                        mon = party[i]
                        if (target.upper() in mon.nickname.upper()
                                or target.upper() in mon.name.upper()):
                            label = mon.nickname
                            if mon.nickname != mon.name:
                                label = f"{mon.name} ({mon.nickname})"
                            _log.log_think(f"=> SWITCH to {label} Lv{mon.level}!")
                            return i

        # Couldn't parse — stay
        _log.log_think("=> STAY")
        return None

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def decide(self, player, enemy, is_wild, balls=None):
        """Decide a battle action given both pokemon's stats.

        Returns:
            tuple: ("move", move_name), ("run", None),
                   ("ball", bag_index), or ("switch", party_idx)
        """
        _log.log_think(f"--- Turn: {player.name} vs {enemy.name} ---")

        # If catching and no balls left, switch to defeat
        if self._goal == "catch" and (not balls or all(c == 0 for _, c, _ in balls)):
            _log.log_think("No Poke Balls left! Switching to defeat.")
            self._goal = "defeat"

        system_prompt = self._render_system()
        user_prompt = self._render_state(player, enemy, is_wild, balls)

        _log.log_prompt("BATTLE", system_prompt, user_prompt)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        max_retries = 2
        last_text = ""
        for attempt in range(max_retries + 1):
            response = self._llm.invoke(messages)
            _log.stop_thinking()
            last_text = response.content or ""
            # Print reasoning to console for every attempt
            for line in last_text.strip().split("\n"):
                if line.strip().startswith("THINK:"):
                    _log.log_think(line.strip()[6:].strip())
            action, error = self._parse_response(
                last_text, player, balls,
            )
            if action is not None:
                break
            _log.log_retry()
            _log.log_think(f"(retry {attempt + 1}/{max_retries}: {error})")
            if attempt < max_retries:
                messages.append(response)
                messages.append(HumanMessage(
                    content=f"ERROR: {error}\nTry again."
                ))

        # All retries failed — return None for manual control
        if action is None:
            _log.log_think("(all retries failed — returning control to user)")
            return None

        # Retry loop if LLM tries to RUN in a trainer battle
        while not is_wild and action[0] == "run":
            error_msg = "ERROR: You CANNOT run from trainer battles. Pick a MOVE instead."
            _log.log_retry()
            _log.log_think("(retry: tried to run from trainer)")
            messages.append(HumanMessage(content=error_msg))
            _log.start_thinking()
            response = self._llm.invoke(messages)
            _log.stop_thinking()
            text = response.content or ""
            action, _ = self._parse_response(text, player, balls)

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
        e_types = POKEMON_TYPES.get(enemy.name.upper(), "")
        hp_pct = round(enemy.hp / enemy.max_hp * 100) if enemy.max_hp else 0
        enemy_data = {
            "name": enemy.name, "types": e_types,
            "level": enemy.level,
            "hp": enemy.hp, "max_hp": enemy.max_hp,
            "hp_pct": hp_pct,
            "status": enemy.status,
        }

        # Player data with typed moves + power/description + STAB
        p_types = POKEMON_TYPES.get(player.name.upper(), "")
        p_type_list = [t.strip() for t in p_types.split("/")] if p_types else []
        moves = []
        for m in player.moves:
            m_type = MOVE_TYPES.get(m.name.upper(), "")
            data = MOVE_DATA.get(m.name.upper())
            power = data[0] if data else 0
            accuracy = data[1] if data else 0
            category = data[2] if data else ""
            desc = data[3] if data else ""
            stab = m_type != "" and m_type in p_type_list
            moves.append({
                "name": m.name, "type": m_type,
                "pp": m.pp, "max_pp": m.max_pp,
                "power": power, "accuracy": accuracy,
                "category": category, "desc": desc,
                "stab": stab,
            })
        player_data = {
            "name": player.name, "types": p_types,
            "level": player.level,
            "hp": player.hp, "max_hp": player.max_hp,
            "status": player.status,
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
            if mon.hp <= 0:
                continue
            nick = mon.nickname
            label = (f"{mon.name} ({nick})"
                     if nick != mon.name else nick)
            m_types = POKEMON_TYPES.get(mon.name.upper(), "")
            switchable.append({
                "label": label, "types": m_types,
                "level": mon.level,
                "hp": mon.hp, "max_hp": mon.max_hp,
            })

        battle_type = "Wild" if is_wild else "Trainer (CANNOT RUN)"
        goal = self._goal.upper() if self._goal else None

        # Get known type matchups from battle memory
        known_matchups = []
        if self._battle_reflect:
            known_matchups = self._battle_reflect.get_memory_text()

        return _render("battle_state.j2",
                       battle_type=battle_type, goal=goal,
                       enemy=enemy_data, player=player_data,
                       balls=ball_strs, switchable=switchable,
                       history=self._history,
                       known_matchups=known_matchups)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, text, player, balls=None):
        """Parse the LLM response into an action tuple.

        Returns (action_tuple, error_str | None).
        error_str is set when the action couldn't be resolved so the
        caller can retry with the error added to the prompt.
        """
        # Find the ACTION line
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action = line[7:].strip()
                if action == "RUN":
                    return ("run", None), None
                if action == "BALL":
                    if balls:
                        for name, count, bag_idx in balls:
                            if count > 0:
                                return ("ball", bag_idx), None
                    return None, "No Poke Balls available. Choose a different action."
                if action.startswith("SWITCH:"):
                    target = action[7:].strip()
                    for i, mon in enumerate(self._team):
                        if i == self._active_idx:
                            continue
                        if mon.hp <= 0:
                            continue
                        if (target.upper() in mon.nickname.upper()
                                or target.upper() in mon.name.upper()):
                            return ("switch", i), None
                    return None, (
                        f"'{target}' doesn't match any switchable party member. "
                        f"Available: {[m.nickname for m in self._team if m.hp > 0 and self._team.index(m) != self._active_idx]}"
                    )
                if action.startswith("MOVE:"):
                    move_name = action[5:].strip().replace("_", " ")
                    available = [m.name for m in player.moves if m.pp > 0]
                    for m in available:
                        if m.upper() == move_name.upper():
                            return ("move", m), None
                    for m in available:
                        if move_name.upper() in m.upper():
                            return ("move", m), None
                    return None, (
                        f"'{move_name}' doesn't match any available move. "
                        f"Available moves: {available}"
                    )

        return None, f"Could not find ACTION: in your response. Use the exact format."

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_action(self, action):
        if action[0] == "run":
            _log.log_think("=> RUN")
            _log.log_stat("run")
        elif action[0] == "ball":
            _log.log_think("=> throw Poke Ball!")
            _log.log_stat("ball")
        elif action[0] == "switch":
            mon = self._team[action[1]]
            label = (mon.nickname if mon.nickname == mon.name
                     else f"{mon.name} ({mon.nickname})")
            _log.log_think(f"=> SWITCH to {label}!")
            _log.log_stat("sw")
        else:
            _log.log_think(f"=> {action[1]}")
            _log.log_stat("atk")
