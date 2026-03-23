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
from agents.reflect_ai import ReflectAI
from adapters.display.ai_logger import AILogger
from adapters.display.console import _poi_icon, render_map

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES),
                   keep_trailing_newline=True)

_MAX_HISTORY = 30
_DEBUG_PROMPTS = True

_log = AILogger("OW")


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


_BADGES = [
    {"name": "Boulder Badge", "leader": "Brock", "city": "Pewter City"},
    {"name": "Cascade Badge", "leader": "Misty", "city": "Cerulean City"},
    {"name": "Thunder Badge", "leader": "Lt. Surge", "city": "Vermilion City"},
    {"name": "Rainbow Badge", "leader": "Erika", "city": "Celadon City"},
    {"name": "Soul Badge", "leader": "Koga", "city": "Fuchsia City"},
    {"name": "Marsh Badge", "leader": "Sabrina", "city": "Saffron City"},
    {"name": "Volcano Badge", "leader": "Blaine", "city": "Cinnabar Island"},
    {"name": "Earth Badge", "leader": "Giovanni", "city": "Viridian City"},
]


def _build_badge_list(badges_byte):
    """Convert badge bitmask to list of dicts with obtained status."""
    return [
        {**b, "obtained": bool(badges_byte & (1 << i))}
        for i, b in enumerate(_BADGES)
    ]


class OverworldAI:
    def __init__(self, llm, goal="Become Pokemon Champion",
                 reflect_ai: ReflectAI | None = None):
        self._llm = llm
        self.goal = goal
        self.shop_ai = ShopAI(llm=self._llm)
        self._reflect_ai = reflect_ai
        self._history = []
        self._last_think = ""
        self._visited_maps = set()
        self._visited_pois = set()
        self._iteration = 0

    @property
    def iteration(self) -> int:
        """Number of decisions made so far."""
        return self._iteration

    def active_subgoal(self):
        """Return the current active sub-goal dict, or None."""
        if self._reflect_ai:
            return self._reflect_ai.active_subgoal()
        return None

    # ------------------------------------------------------------------
    # Reflect — delegated to ReflectAI
    # ------------------------------------------------------------------

    def reflect(self, map_name, action, result="", dialogue=""):
        """Delegate reflection to the ReflectAI agent."""
        if self._reflect_ai:
            self._reflect_ai.iteration = self._iteration
            self._reflect_ai.reflect(map_name, action, result, dialogue)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def record_action(self, action_desc, map_name, result_text="",
                      poi_label="", poi_kind="", poi_num=0, reason=""):
        """Record an action in the exploration history."""
        self._visited_maps.add(map_name)
        entry = {
            "action": action_desc,
            "map": map_name,
            "result": result_text,
        }
        if reason:
            entry["reason"] = reason
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
               party=None, pokeballs=0, has_pokedex=False,
               money=0, badges=0):
        """Ask the LLM what to do next in the overworld."""
        self._iteration += 1
        _log._action_count = self._iteration
        self._visited_maps.add(map_name)

        # Build POI data with visit counts and directions
        recent = self._history[-25:]
        poi_data = []
        for i, poi in enumerate(pois):
            times = sum(1 for e in recent
                        if e.get("map") == map_name
                        and e.get("poi") == poi["label"])
            label = poi["label"]
            kind = poi["kind"]
            if kind in ("exit", "warp", "connection"):
                label = f"[Warp] \u2192 {label}"
            dist = abs(poi["ty"] - player_y) + abs(poi["tx"] - player_x)
            is_warp = kind in ("exit", "warp", "connection")
            poi_data.append({
                "icon": _poi_icon(poi),
                "label": label,
                "dist": dist,
                "times_recent": times,
                "is_warp": is_warp,
                "_orig_idx": i,
            })
        poi_data.sort(key=lambda p: p["dist"])

        active = self.active_subgoal()
        completed = (self._reflect_ai.completed_subgoals()
                     if self._reflect_ai else [])

        system_prompt = _render("overworld_system.j2",
                                goal=self.goal,
                                active_subgoal=active)
        user_prompt = _render("overworld_state.j2",
                              map_name=map_name,
                              pois=poi_data,
                              visited_maps=sorted(self._visited_maps),
                              history=self._history[-25:],
                              active_subgoal=active,
                              completed_subgoals=completed,
                              party=party or [],
                              pokeballs=pokeballs,
                              has_pokedex=has_pokedex,
                              money=money,
                              badge_list=_build_badge_list(badges),
                              badge_count=bin(badges).count("1"),
                              ascii_map=render_map(
                                  [pois[p["_orig_idx"]] for p in poi_data],
                                  player_y, player_x, grid,
                                  legend=False) if grid else "")

        if _DEBUG_PROMPTS:
            _log.log_prompt("DECIDE", system_prompt, user_prompt)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        max_retries = 3
        attempt = 0
        while attempt <= max_retries:
            _log.start_thinking()
            response = self._llm.invoke(messages)
            _log.stop_thinking()
            text = response.content
            result = self._parse_response(text, poi_data)
            if result is not None:
                return result
            attempt += 1
            _log.log_retry()
            _log.log_think(f"(retry {attempt}: couldn't parse response)")
            _log.log_think(f"  raw: {text.strip()}")
            messages.append(response)
            messages.append(HumanMessage(
                content=f"ERROR: Invalid action. Valid POI numbers are 1 to {len(pois)}. "
                        f"Respond with exactly: ACTION: GO:<number>"
            ))

        # Max retries exhausted — return None to signal control back to user
        _log.log_think("(max retries — returning control to user)")
        return None

    def _parse_response(self, text, poi_data):
        """Parse LLM response into an action tuple.

        poi_data is sorted by distance and contains _orig_idx for mapping
        back to the original pois array.
        """
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
                    if 0 <= idx < len(poi_data):
                        orig_idx = poi_data[idx]["_orig_idx"]
                        if think:
                            _log.log_think(think)
                        _log.log_think(f"=> GO to {poi_data[idx]['label']}")
                        self._last_think = think
                        return ("go", orig_idx)
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
