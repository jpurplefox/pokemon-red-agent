"""Overworld exploration AI — uses a local LLM to decide where to go.

Sends map state (current location, POIs, history) to a local Qwen model
running on Ollama. The model reasons about what to explore next and
chooses actions: go to a POI, move, interact, or look around.

Prompts are managed as Jinja2 templates in the templates/ directory.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import SystemMessage, HumanMessage
from agents.shop_ai import ShopAI
from adapters.display.ai_logger import AILogger
from adapters.display.console import _poi_icon

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES),
                   keep_trailing_newline=True)

_MAX_HISTORY = 30
_SUBGOAL_EXPIRE = 25  # expire after N iterations without completion
_DEBUG_PROMPTS = True

_log = AILogger("OW")


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


class OverworldAI:
    def __init__(self, llm, goal="Reach Viridian Forest"):
        self._llm = llm
        self.goal = goal
        self.shop_ai = ShopAI(llm=self._llm)
        self._history = []
        self._visited_maps = set()
        self._visited_pois = set()
        self._subgoals = []
        self._iteration = 0

    @property
    def iteration(self) -> int:
        """Number of decisions made so far."""
        return self._iteration

    def active_subgoal(self):
        """Return the current active sub-goal dict, or None."""
        for sg in self._subgoals:
            if sg["status"] == "active":
                return sg
        return None

    def _expire_subgoals(self):
        """Remove sub-goals that have been active too long."""
        expired = []
        for sg in self._subgoals:
            if sg["status"] == "active":
                age = self._iteration - sg["added_at"]
                if age >= _SUBGOAL_EXPIRE:
                    sg["status"] = "expired"
                    expired.append(sg)
        if expired:
            for sg in expired:
                msg = f"⏰ Sub-goal expired: {sg['description']}"
                print(f"  {_YELLOW}OW: {msg}{_RESET}")
                _log.log_event(msg, "memory")

    # ------------------------------------------------------------------
    # Reflect — detect and manage sub-goals
    # ------------------------------------------------------------------

    def reflect(self, map_name, action, result="", dialogue=""):
        """Ask the LLM to reflect and detect/complete sub-goals."""
        active = self.active_subgoal()

        system_prompt = _render("overworld_reflect.j2")
        user_prompt = _render("overworld_reflect_state.j2",
                              map_name=map_name,
                              action=action,
                              result=result,
                              dialogue=dialogue,
                              active_subgoal=active,
                              completed_subgoals=[
                                  sg for sg in self._subgoals
                                  if sg["status"] == "done"
                              ],
                              main_goal=self.goal)

        if _DEBUG_PROMPTS:
            _log.log_prompt("REFLECT", system_prompt, user_prompt)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self._llm.invoke(messages)
        text = response.content

        if _DEBUG_PROMPTS:
            _log.log_response("REFLECT", text)

        # Parse response
        subgoal_action = ""
        subgoal_desc = ""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("SUBGOAL:"):
                subgoal_action = line[8:].strip().lower()
            elif line.startswith("DESCRIPTION:"):
                subgoal_desc = line[12:].strip()

        if subgoal_action == "new" and subgoal_desc:
            # Check if we already have an identical active subgoal
            if active and active["description"].lower() == subgoal_desc.lower():
                return
            # If there's an active one, replace it
            if active:
                active["status"] = "replaced"
                msg = f"🔄 Replaced sub-goal: {active['description']}"
                print(f"  {_YELLOW}OW: {msg}{_RESET}")
                _log.log_event(msg, "memory")
            new_sg = {
                "description": subgoal_desc,
                "status": "active",
                "added_at": self._iteration,
            }
            self._subgoals.append(new_sg)
            msg = f"🎯 New sub-goal: {subgoal_desc}"
            print(f"  {_GREEN}OW: {msg}{_RESET}")
            _log.log_event(msg, "memory")

        elif subgoal_action == "done" and active:
            active["status"] = "done"
            active["done_at"] = self._iteration
            msg = f"✅ Sub-goal completed: {active['description']}"
            print(f"  {_GREEN}OW: {msg}{_RESET}")
            _log.log_event(msg, "memory")

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def record_action(self, action_desc, map_name, result_text="",
                      poi_label="", poi_kind="", poi_num=0):
        """Record an action in the exploration history."""
        self._visited_maps.add(map_name)
        entry = {
            "action": action_desc,
            "map": map_name,
            "result": result_text,
        }
        if poi_label:
            entry["poi"] = poi_label
        if poi_kind:
            entry["poi_kind"] = poi_kind
        if poi_num:
            entry["poi_num"] = poi_num
        self._history.append(entry)
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]

    def record_poi_visited(self, map_name, poi_label):
        """Mark a POI as already interacted with."""
        self._visited_pois.add(f"{map_name}:{poi_label}")

    def record_dialogue(self, map_name, text):
        """Attach dialogue text to the most recent history entry."""
        if self._history:
            prev = self._history[-1]
            if prev.get("result"):
                prev["result"] += f" — \"{text}\""
            else:
                prev["result"] = f"\"{text}\""

    # ------------------------------------------------------------------
    # Shopping
    # ------------------------------------------------------------------

    def decide_purchases(self, items, money, pokeballs, party=None):
        """Delegate to ShopAI for purchase decisions."""
        return self.shop_ai.decide_purchases(items, money, pokeballs, party)

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def decide(self, map_name, pois, grid=None, player_y=0, player_x=0,
               party=None, pokeballs=0, has_pokedex=False):
        """Ask the LLM what to do next in the overworld.

        Returns ("goal_reached", None) when the main goal is completed.
        """
        # Check if main goal is reached (goal name appears in map name)
        goal_keywords = self.goal.lower().replace("reach ", "").strip()
        if goal_keywords in map_name.lower():
            msg = f"🏆 GOAL REACHED: {self.goal} (arrived at {map_name})"
            print(f"\n  {_GREEN}{'='*50}")
            print(f"  {msg}")
            print(f"  {'='*50}{_RESET}\n")
            _log.log_event(msg, "memory")
            return ("goal_reached", None)

        self._iteration += 1
        _log._action_count = self._iteration
        self._visited_maps.add(map_name)
        self._expire_subgoals()

        # Build POI data with visit counts and directions
        recent = self._history[-15:]
        poi_data = []
        for poi in pois:
            times = sum(1 for e in recent
                        if e.get("map") == map_name
                        and e.get("poi") == poi["label"])
            label = poi["label"]
            kind = poi["kind"]
            if kind in ("exit", "warp", "connection"):
                label = f"[Warp] \u2192 {label}"
            poi_data.append({
                "icon": _poi_icon(poi),
                "label": label,
                "dir": poi["dir"],
                "times_recent": times,
            })

        active = self.active_subgoal()

        system_prompt = _render("overworld_system.j2",
                                goal=self.goal,
                                active_subgoal=active)
        user_prompt = _render("overworld_state.j2",
                              map_name=map_name,
                              pois=poi_data,
                              visited_maps=sorted(self._visited_maps),
                              history=self._history[-15:],
                              active_subgoal=active,
                              completed_subgoals=[
                                  sg for sg in self._subgoals
                                  if sg["status"] == "done"
                              ],
                              party=party or [],
                              pokeballs=pokeballs,
                              has_pokedex=has_pokedex)

        if _DEBUG_PROMPTS:
            _log.log_prompt("DECIDE", system_prompt, user_prompt)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        for attempt in range(3):
            _log.start_thinking()
            response = self._llm.invoke(messages)
            _log.stop_thinking()
            text = response.content
            result = self._parse_response(text, pois)
            if result is not None:
                return result
            _log.log_think(f"(retry {attempt + 1}: couldn't parse response)")
            _log.log_think(f"  raw: {text.strip()[:120]}")
            messages.append(response)
            messages.append(HumanMessage(
                content="ERROR: Invalid action. Use the exact format."
            ))

        # Fallback: pick first unvisited POI, or just look
        for i, poi in enumerate(pois):
            poi_id = f"{map_name}:{poi['label']}"
            if poi_id not in self._visited_pois:
                _log.log_think(f"(fallback) Going to {poi['label']}")
                return ("go", i)
        return ("look", None)

    def _parse_response(self, text, pois):
        """Parse LLM response into an action tuple."""
        think = ""
        for line in text.strip().split("\n"):
            if line.strip().startswith("THINK:"):
                think = line.strip()[6:].strip()

        for line in text.strip().split("\n"):
            line = line.strip()
            if not line.startswith("ACTION:"):
                continue
            action = line[7:].strip()

            if action.startswith("GO:"):
                try:
                    num = int(action[3:].strip())
                    idx = num - 1  # 1-indexed in prompt
                    if 0 <= idx < len(pois):
                        if think:
                            _log.log_think(think)
                        _log.log_think(f"=> GO to {pois[idx]['label']}")
                        return ("go", idx)
                except ValueError:
                    pass

            if action.startswith("MOVE:"):
                direction = action[5:].strip().lower()
                if direction in {"up", "down", "left", "right"}:
                    if think:
                        _log.log_think(think)
                    _log.log_think(f"=> MOVE {direction}")
                    return ("move", direction)

            if action == "START":
                if think:
                    _log.log_think(think)
                _log.log_think("=> START menu")
                return ("start", None)

        return None
