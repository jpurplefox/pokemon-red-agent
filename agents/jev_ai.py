"""Jev (TypeSafe System One) variants of the closed-decision agents.

Each class keeps the public interface of the agent it replaces, so Game and
the controllers don't change. Instead of parsing "ACTION: ..." from LLM text,
the decision is a Choice over the valid options, built per call, and the
option is drawn at random weighted by Jev's probabilities (not the argmax).

Jev does not generate text, so there is no THINK line. The only free-text
step (describing a NEW sub-goal) is delegated to the chat LLM.

Enabled with `--jev` in main.py.
"""

import json
import random

from langchain_core.messages import SystemMessage, HumanMessage
from typesafe_sdk import Choice

from adapters.display.ai_logger import AILogger
from agents.battle_ai import BattleAI
from data.pokemon_data import POKEMON_TYPES
from agents.overworld_ai import OverworldAI, _build_badge_list
from agents.reflect_ai import ReflectAI
from agents.scout_ai import ScoutAI

_MAX_HISTORY_IN_STATE = 25  # same window the chat OverworldAI sees


def _ask(log, label, client, state, questions):
    """Single System One call with prompt/latency logging. None on API error."""
    log.log_prompt(label, json.dumps(
        {k: q.instructions for k, q in questions.items()}, ensure_ascii=False),
        json.dumps(state, ensure_ascii=False, indent=1)
        if not isinstance(state, str) else state)
    log.start_thinking()
    try:
        response = client.system_one(state=state, questions=questions)
    except Exception as e:
        log.stop_thinking()
        log.log_think(f"(Jev error: {e})")
        return None
    log.stop_thinking()
    return response


def _sample_choice(log, answer):
    """Pick an option at random, weighted by Jev's probabilities.

    Draws r in [0, 1) and returns the option whose cumulative probability
    band contains it, so a 70/30 split picks the second option ~30% of the time.
    """
    options = sorted(answer.probabilities.items(), key=lambda kv: -kv[1])
    total = sum(p for _, p in options) or 1.0
    r = random.random()
    cumulative = 0.0
    picked = options[-1][0]
    for option, p in options:
        cumulative += p / total
        if r < cumulative:
            picked = option
            break
    probs = ", ".join(f"{k} {p:.0%}" for k, p in options[:3])
    note = "" if picked == answer.choice else f" — top was {answer.choice}"
    log.log_think(f"{picked} (rolled {r:.2f}; conf {answer.confidence:.2f}; "
                  f"{probs}){note}")
    return picked


# ----------------------------------------------------------------------
# Overworld
# ----------------------------------------------------------------------

_ow_log = AILogger("JEV-OW")


class JevOverworldAI(OverworldAI):
    """OverworldAI whose decide() is a Choice over INTERACT:n / GO:n."""

    def __init__(self, jev, **kwargs):
        super().__init__(**kwargs)
        self._jev = jev

    def decide(self, map_name, pois, grid=None, player_y=0, player_x=0,
               party=None, pokeballs=0, has_pokedex=False,
               money=0, badges=0, player_name="", key_items=None):
        self._iteration += 1
        _ow_log._action_count = self._iteration
        if map_name not in self._visited_maps:
            self._visited_maps.append(map_name)

        recent = self._history[-_MAX_HISTORY_IN_STATE:]
        options = {}   # option id -> (orig poi index, action label, poi)
        criteria = {}
        n_interact = n_warp = 0
        for i, poi in enumerate(pois):
            dist = abs(poi["ty"] - player_y) + abs(poi["tx"] - player_x)
            if poi["kind"] in ("exit", "warp", "connection"):
                n_warp += 1
                oid = f"go_{n_warp}"
                options[oid] = (i, f"GO:{n_warp}", poi)
                criteria[oid] = {
                    "action": "Walk to and enter this warp/exit, leaving the current map",
                    "target": poi["label"], "distance_steps": dist,
                }
                if poi.get("visited") is not None:
                    criteria[oid]["already_visited"] = poi["visited"]
                if poi.get("leads_to"):
                    criteria[oid]["leads_to"] = poi["leads_to"]
            else:
                n_interact += 1
                oid = f"interact_{n_interact}"
                times = sum(1 for e in recent
                            if e.get("map") == map_name
                            and e.get("poi") == poi["label"])
                options[oid] = (i, f"INTERACT:{n_interact}", poi)
                criteria[oid] = {
                    "action": "Walk to and interact with (talk / read / battle / walk in grass)",
                    "target": poi["label"], "distance_steps": dist,
                    "times_interacted_recently": times,
                }
                if poi.get("last_interaction"):
                    criteria[oid]["last_said"] = poi["last_interaction"]
        if not options:
            _ow_log.log_think("(nothing to choose from — returning control to user)")
            return None

        active = self.active_subgoal()
        completed = (self._reflect_ai.completed_subgoals()
                     if self._reflect_ai else [])
        state = {
            "player": player_name or "RED",
            "main_goal": self.goal,
            "active_subgoal": active["description"] if active else "none",
            "completed_subgoals": [sg["description"] for sg in completed],
            "current_map": map_name,
            "team": [f"{m.nickname} ({m.name}) Lv{m.level} {m.hp}/{m.max_hp} HP"
                     for m in (party or [])],
            "money": money,
            "poke_balls": pokeballs,
            "has_pokedex": has_pokedex,
            "key_items": key_items or [],
            "badges": [b["name"] for b in _build_badge_list(badges) if b["obtained"]],
            "recent_history": [
                {k: e[k] for k in ("map", "action_label", "poi", "action", "result") if e.get(k)}
                for e in recent
            ],
        }
        questions = {"next_action": Choice(
            instructions=(
                "You are playing Pokemon Red. Which single action should the "
                "player take next to make progress on the active sub-goal (or "
                "the main goal if there is none)? Heal at a Pokemon Center when "
                "the team is badly hurt; avoid repeating interactions that were "
                "already done several times. For exits, `leads_to` is what "
                "the player found beyond that exit the last time it was used "
                "(only what is reachable from where it lands; nested `exits` "
                "are further away). `already_visited: false` means it was "
                "never used and leads somewhere unknown; `interacted: false` "
                "means that person or object was never talked to or checked; "
                "`blocks_way_to` lists what it keeps out of reach."),
            criteria=criteria,
        )}

        response = _ask(_ow_log, "DECIDE", self._jev, state, questions)
        if response is None:
            return None
        answer = response.answers["next_action"]
        choice = _sample_choice(_ow_log, answer)
        orig_idx, action_label, poi = options[choice]
        _ow_log.log_think(f"=> {action_label} {poi['label']}")
        self._last_think = ""
        if action_label.startswith("GO:"):
            _ow_log.log_stat("warp")
        elif poi["kind"] == "grass":
            _ow_log.log_stat("grass")
        else:
            _ow_log.log_stat("interact")
        return ("go", orig_idx, action_label)


# ----------------------------------------------------------------------
# Scout (catch / defeat)
# ----------------------------------------------------------------------

_scout_log = AILogger("JEV-SCOUT")


class JevScoutAI(ScoutAI):
    def __init__(self, jev):
        super().__init__(llm=None)
        self._jev = jev

    def should_catch(self, enemy_name, enemy_level, team):
        state = self._build_prompt(enemy_name, enemy_level, team)
        questions = {"decision": Choice(
            instructions="As a Pokemon Red team-building strategist, should the "
                         "trainer catch this wild Pokemon or defeat it?",
            criteria={
                "catch": "Adds new type coverage or strong evolution potential, "
                         "and is not already on the team (same species or evolution line)",
                "defeat": "Redundant type or evolution line, or low value for the team",
            },
        )}
        response = _ask(_scout_log, "SCOUT", self._jev, state, questions)
        if response is None:
            return False  # same conservative default as ScoutAI
        answer = response.answers["decision"]
        choice = _sample_choice(_scout_log, answer)
        if choice == "catch":
            _scout_log.log_think("Decision: CATCH! 🔴")
            _scout_log.log_stat("catch")
            return True
        _scout_log.log_think("Decision: DEFEAT ⚔️")
        return False


# ----------------------------------------------------------------------
# Move learning
# ----------------------------------------------------------------------

_move_log = AILogger("JEV-MOVE")


class JevMoveAI:
    def __init__(self, jev):
        self._jev = jev

    def decide(self, species, new_move, current_moves):
        """Same contract as MoveAI.decide: name to forget, "" to keep, None on failure."""
        fields = ("name", "type", "power", "pp", "category", "desc")
        state = {
            "pokemon": species,
            "new_move": {k: new_move[k] for k in fields if k in new_move},
            "current_moves": [{k: m[k] for k in fields if k in m}
                              for m in current_moves],
        }
        criteria = {"keep": f"Skip learning {new_move['name']} and keep the current four moves"}
        for m in current_moves:
            criteria[f"forget_{m['name'].upper()}"] = (
                f"Forget {m['name']} and learn {new_move['name']}")
        questions = {"decision": Choice(
            instructions="A Pokemon is trying to learn a new move but already knows "
                         "4. Which option gives the best moveset, considering power, "
                         "type coverage, PP and not keeping redundant moves?",
            criteria=criteria,
        )}
        response = _ask(_move_log, "MOVE", self._jev, state, questions)
        if response is None:
            return None
        answer = response.answers["decision"]
        choice = _sample_choice(_move_log, answer)
        if choice == "keep":
            _move_log.log_think(f"Keep current moves, skip {new_move['name']}")
            _move_log.log_stat("skipped")
            return ""
        forget = choice[len("forget_"):]
        _move_log.log_think(f"Forget {forget} → learn {new_move['name']}")
        _move_log.log_stat("learned")
        return forget


# ----------------------------------------------------------------------
# Lead selection
# ----------------------------------------------------------------------

_lead_log = AILogger("JEV-LEAD")


class JevLeadAI:
    def __init__(self, jev):
        self._jev = jev

    def choose_lead(self, party):
        """Same contract as LeadAI.choose_lead: party index, 0 to keep, None if n/a."""
        if len(party) <= 1:
            return None
        alive = [i for i, m in enumerate(party) if m.hp > 0]
        if len(alive) <= 1:
            return None

        state = {"team": [
            {"slot": i + 1, "nickname": m.nickname, "species": m.name,
             "level": m.level, "hp": f"{m.hp}/{m.max_hp}",
             "current_lead": i == 0}
            for i, m in enumerate(party)
        ]}
        lead = party[0]
        criteria = {"keep": f"Keep {lead.nickname} as lead"}
        for i in alive:
            if i != 0:
                m = party[i]
                criteria[f"switch_{i + 1}"] = (
                    f"Make {m.nickname} ({m.name} Lv{m.level}) the new lead")
        questions = {"decision": Choice(
            instructions="After a battle, which Pokemon should lead the party? A "
                         "lead with very low HP should not stay in front; a healthy "
                         "lead is usually fine; a lower-level teammate may benefit "
                         "from experience.",
            criteria=criteria,
        )}
        response = _ask(_lead_log, "LEAD", self._jev, state, questions)
        if response is None:
            return None
        answer = response.answers["decision"]
        choice = _sample_choice(_lead_log, answer)
        if choice == "keep":
            _lead_log.log_think(f"Keeping {lead.nickname} as lead")
            return 0
        idx = int(choice[len("switch_"):]) - 1
        mon = party[idx]
        _lead_log.log_stat("swap")
        _lead_log.log_think(f"=> New lead: {mon.nickname} Lv{mon.level}")
        return idx


# ----------------------------------------------------------------------
# Sub-goal reflection
# ----------------------------------------------------------------------

_reflect_log = AILogger("JEV-REFLECT")

_DESCRIBE_PROMPT = """\
An NPC in Pokemon Red just gave the player a mission. Write it as one short \
imperative sentence (e.g. "Deliver Oak's Parcel to Professor Oak in Pallet Town").
Respond with EXACTLY one line:
GOAL: <mission>"""


class JevReflectAI(ReflectAI):
    """Jev decides NEW / DONE / NONE; the chat LLM only writes NEW descriptions."""

    def __init__(self, jev, llm, **kwargs):
        super().__init__(llm=llm, **kwargs)
        self._jev = jev

    def reflect(self, map_name, action, result="", dialogue="",
                player_name=""):
        active = self.active_subgoal()
        state = {
            "location": map_name,
            "action": action,
            "result": result,
            "dialogue": dialogue,
            "main_goal": self.goal,
            "active_subgoal": active["description"] if active else "none",
            "completed_subgoals": [sg["description"] for sg in self.completed_subgoals()],
        }
        criteria = {
            "new": "An NPC personally gave the player a concrete mission in this "
                   "dialogue (not a sign, tip, item pickup, or general advice), "
                   "different from the main goal and the active sub-goal",
            "none": "Nothing noteworthy: no new NPC mission and no confirmation "
                    "that the active sub-goal was completed",
        }
        if active:
            criteria["done"] = ("The active sub-goal was just completed, confirmed "
                                "by a thank-you or reward from the NPC")
        questions = {"decision": Choice(
            instructions="What happened to the player's sub-goals after this action?",
            criteria=criteria,
        )}
        response = _ask(_reflect_log, "REFLECT", self._jev, state, questions)
        if response is None:
            return
        answer = response.answers["decision"]
        choice = _sample_choice(_reflect_log, answer)

        if choice == "new":
            self._apply("new", self._describe(map_name, dialogue))
        else:
            self._apply(choice)

    def _describe(self, map_name, dialogue):
        text = self._llm.invoke([
            SystemMessage(content=_DESCRIBE_PROMPT),
            HumanMessage(content=f"Location: {map_name}\nDialogue: \"{dialogue}\""),
        ]).content or ""
        for line in text.strip().split("\n"):
            if line.strip().startswith("GOAL:"):
                return line.strip()[5:].strip()
        return ""


# ----------------------------------------------------------------------
# Battle
# ----------------------------------------------------------------------

_battle_log = AILogger("JEV-BATTLE")


def _mon_label(mon):
    return mon.nickname if mon.nickname == mon.name else f"{mon.name} ({mon.nickname})"


def _mon_state(mon):
    return {"pokemon": _mon_label(mon),
            "types": POKEMON_TYPES.get(mon.name.upper(), ""),
            "level": mon.level, "hp": f"{mon.hp}/{mon.max_hp}"}


class JevBattleAI(BattleAI):
    """BattleAI whose turn / switch decisions are Choices over the legal actions.

    The state is the same rendered battle prompt the chat model sees. RUN is
    only offered in wild battles, so no "can't run from trainer" retries.
    """

    def __init__(self, jev, **kwargs):
        super().__init__(**kwargs)
        self._jev = jev

    def decide(self, player, enemy, is_wild, balls=None):
        _battle_log.log_think(f"--- Turn: {player.name} vs {enemy.name} ---")
        has_balls = bool(balls) and any(c > 0 for _, c, _ in balls)
        if self._goal == "catch" and not has_balls:
            _battle_log.log_think("No Poke Balls left! Switching to defeat.")
            self._goal = "defeat"

        options, criteria = {}, {}
        for m in player.moves:
            if m.pp > 0 and not m.disabled:
                oid = f"move_{m.name.upper()}"
                options[oid] = ("move", m.name)
                criteria[oid] = f"Attack with {m.name}"
        if self._goal == "catch":
            for _, count, bag_idx in balls:
                if count > 0:
                    options["ball"] = ("ball", bag_idx)
                    criteria["ball"] = "Throw a Poke Ball to catch the enemy"
                    break
        elif is_wild:
            options["run"] = ("run", None)
            criteria["run"] = "Run away from this wild battle"
        for i, mon in enumerate(self._team):
            if i != self._active_idx and mon.hp > 0:
                oid = f"switch_{i + 1}"
                options[oid] = ("switch", i)
                criteria[oid] = (f"Switch to {_mon_label(mon)} "
                                 f"(costs a turn: the enemy attacks for free)")
        if not options:
            _battle_log.log_think("(no legal action — returning control to user)")
            return None

        if self._goal == "catch":
            instructions = (
                "Pokemon Red battle, goal: CATCH the wild Pokemon. Which action is "
                "best now? Weaken it with low-power moves without knocking it out "
                "(STAB moves hit 50% harder); throw a ball once its HP is low, or "
                "right away if any attack risks a KO.")
        else:
            instructions = (
                "Pokemon Red battle, goal: DEFEAT the enemy. Which action is best "
                "now? Prefer high-power, super-effective and STAB moves; moves with "
                "Pow 0 deal no damage; switch only if the active Pokemon is about "
                "to faint and a healthier teammate is available.")

        state = self._render_state(player, enemy, is_wild, balls)
        questions = {"action": Choice(instructions=instructions, criteria=criteria)}
        response = _ask(_battle_log, "BATTLE", self._jev, state, questions)
        if response is None:
            return None
        answer = response.answers["action"]
        choice = _sample_choice(_battle_log, answer)
        action = options[choice]
        self._log_action(action)
        return action

    def choose_switch_in(self, party, alive_indices, is_wild, enemy=None):
        _battle_log.log_think("--- Pokemon fainted! Who to send? ---")
        if not enemy or len(alive_indices) == 1:
            idx = alive_indices[0]
            _battle_log.log_think(f"=> Sending out {_mon_label(party[idx])} Lv{party[idx].level}!")
            return idx

        options, criteria = {}, {}
        for i in alive_indices:
            oid = f"send_{i + 1}"
            options[oid] = i
            criteria[oid] = f"Send out {_mon_label(party[i])}"
        if is_wild:
            options["run"] = -1
            criteria["run"] = "Run away from this wild battle"

        state = {
            "battle_type": "Wild" if is_wild else "Trainer (cannot run)",
            "enemy": {"pokemon": enemy.name,
                      "types": POKEMON_TYPES.get(enemy.name.upper(), ""),
                      "level": enemy.level, "hp": f"{enemy.hp}/{enemy.max_hp}",
                      "status": enemy.status},
            "available_team": [_mon_state(party[i]) for i in alive_indices],
        }
        questions = {"send": Choice(
            instructions="Your Pokemon fainted in a Pokemon Red battle. Which "
                         "Pokemon should go out next to beat this enemy, "
                         "considering type advantage, level and HP?",
            criteria=criteria,
        )}
        response = _ask(_battle_log, "SWITCH-IN", self._jev, state, questions)
        if response is None:
            return None
        answer = response.answers["send"]
        choice = _sample_choice(_battle_log, answer)
        idx = options[choice]
        if idx == -1:
            _battle_log.log_think("chose: RUN!")
        else:
            _battle_log.log_think(f"=> Sending out {_mon_label(party[idx])} Lv{party[idx].level}!")
        return idx

    def choose_switch_offer(self, party, active_idx, alive_indices):
        _battle_log.log_think("--- Switch before next opponent? ---")
        current = party[active_idx]
        options = {"stay": -1}
        criteria = {"stay": f"Keep {_mon_label(current)} in battle"}
        for i in alive_indices:
            if i != active_idx:
                oid = f"switch_{i + 1}"
                options[oid] = i
                criteria[oid] = f"Switch to {_mon_label(party[i])}"

        state = {
            "active": _mon_state(current),
            "available_team": [_mon_state(party[i]) for i in alive_indices
                               if i != active_idx],
        }
        questions = {"decision": Choice(
            instructions="In a Pokemon Red trainer battle the opponent is about to "
                         "send its next Pokemon (still unknown). Should the active "
                         "Pokemon stay, or switch to a teammate? Switch mainly if "
                         "the active one is badly hurt.",
            criteria=criteria,
        )}
        response = _ask(_battle_log, "SWITCH-OFFER", self._jev, state, questions)
        if response is None:
            _battle_log.log_think("=> STAY (Jev error)")
            return -1
        answer = response.answers["decision"]
        choice = _sample_choice(_battle_log, answer)
        idx = options[choice]
        if idx == -1:
            _battle_log.log_think("=> STAY")
        else:
            _battle_log.log_think(f"=> SWITCH to {_mon_label(party[idx])} Lv{party[idx].level}!")
        return idx
