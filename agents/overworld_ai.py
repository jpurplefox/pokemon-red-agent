"""Overworld exploration AI — uses a local LLM to decide where to go.

Sends map state (current location, POIs, history) to a local Qwen model
running on Ollama. The model reasons about what to explore next and
chooses actions: go to a POI, move, interact, or look around.

Prompts are managed as Jinja2 templates in the templates/ directory.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import SystemMessage, HumanMessage
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


def format_leads_to(node, indent="      "):
    """Render a World.leads_to() tree as nested lines under an exit."""
    lines = [f"{indent[:-2]}leads to {node['map']}:"]
    _format_node(node, indent, lines)
    return "\n".join(lines)


def _format_node(node, indent, lines):
    for it in node.get("interactables", []):
        said = f': "{it["said"]}"' if it.get("said") else ""
        new = " 🆕 NOT INTERACTED" if it.get("interacted") is False else ""
        blocks = (f" 🚧 BLOCKS THE WAY to: {', '.join(it['blocks_way_to'])}"
                  if it.get("blocks_way_to") else "")
        lines.append(f"{indent}- {it['name']}{said}{new}{blocks}")
    for ex in node.get("exits", []):
        line = f"{indent}> exit {ex['exit']}"
        if not ex["visited"]:
            line += " 🆕 NOT VISITED"
        elif "leads_to" in ex:
            line += f" → {ex['leads_to']['map']}:"
        else:
            line += " (visited)"
        lines.append(line)
        if "leads_to" in ex:
            _format_node(ex["leads_to"], indent + "    ", lines)


_CAN_MARKS = {"unchecked": "?", "trash": "✗", "switch": "⚡"}


def format_trash_grid(interact_data, puzzle):
    """The Vermilion Gym trash cans as a 3x5 grid of INTERACT numbers.

    The puzzle is spatial (the 2nd switch is next to the 1st), so the cans
    are shown where they are rather than as a list.
    """
    cans = {(e["can"]["row"], e["can"]["col"]): (n, e["can"]["status"])
            for n, e in enumerate(interact_data, 1) if e.get("can")}
    if not cans:
        return ""
    rows = sorted({r for r, _ in cans})
    cols = sorted({c for _, c in cans})
    lines = ["--- Trash cans: switch puzzle (use INTERACT:<number>) ---",
             "        " + "".join(f"col {c:<6}" for c in cols)]
    for r in rows:
        cells = []
        for c in cols:
            n, status = cans.get((r, c), (None, None))
            cells.append(f"[{n}] {_CAN_MARKS[status]}".ljust(10) if n else " " * 10)
        lines.append(f"row {r}   " + "".join(cells))
    lines.append("Marks: ✗ only trash · ⚡ 1st switch · ? not checked")
    switch = next((pos for pos, (_, s) in cans.items() if s == "switch"), None)
    if puzzle.get("solved"):
        lines.append("Both locks are open: the door to the GYM LEADER is open.")
    elif puzzle.get("first_lock_open") and switch:
        lines.append(f"1st lock: OPEN (switch in row {switch[0]}, col {switch[1]}). "
                     "2nd lock: closed.")
    elif puzzle.get("first_lock_open"):
        lines.append("1st lock: OPEN (since before you left the gym; the switches "
                     "have moved, so where the 2nd is is unknown). 2nd lock: closed.")
    else:
        lines.append("1st lock: closed. 2nd lock: closed.")
    lines.append("Rule: one can hides the 1st switch; the 2nd is in a can right "
                 "next to it (up, down, left or right in this grid). Before the "
                 "1st is found every other can only has trash, so those marks "
                 "are cleared when it's found. Checking a wrong can after that "
                 "resets both locks and moves the 1st switch. Leaving the gym "
                 "also moves the switches.")
    if puzzle.get("resets"):
        lines.append(f"The locks have been reset {puzzle['resets']} time(s) since "
                     "you entered.")
    return "\n".join(lines)


def _build_badge_list(badges_byte):
    """Convert badge bitmask to list of dicts with obtained status."""
    return [
        {**b, "obtained": bool(badges_byte & (1 << i))}
        for i, b in enumerate(_BADGES)
    ]


class OverworldAI:
    def __init__(self, llm, goal="Become Pokemon Champion",
                 reflect_ai=None, shop_ai=None):
        self._llm = llm
        self.goal = goal
        self.shop_ai = shop_ai
        self._reflect_ai = reflect_ai
        self._history = []
        self._last_think = ""
        self._visited_maps = []  # ordered by discovery time
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

    def reflect(self, map_name, action, result="", dialogue="",
                player_name=""):
        """Delegate reflection to the ReflectAI agent."""
        if self._reflect_ai:
            self._reflect_ai.iteration = self._iteration
            try:
                self._reflect_ai.reflect(map_name, action, result, dialogue,
                                         player_name=player_name)
            except Exception as e:
                print(f"  ⚠️  Reflect skipped: {e}")

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def record_action(self, action_desc, map_name, result_text="",
                      poi_label="", poi_kind="", action_label="", reason=""):
        """Record an action in the exploration history."""
        if map_name not in self._visited_maps:
            self._visited_maps.append(map_name)
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
        if action_label:
            entry["action_label"] = action_label
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
               money=0, badges=0, player_name="", key_items=None,
               hm_options=None, hm_notes=None, puzzle=None):
        """Ask the LLM what to do next in the overworld."""
        self._iteration += 1
        _log._action_count = self._iteration
        if map_name not in self._visited_maps:
            self._visited_maps.append(map_name)

        # Build POI data split into interactables and warps
        recent = self._history[-25:]
        interact_data = []
        warp_data = []
        blocked_trees = []  # trees CUT can't clear yet: shown, not choosable
        for i, poi in enumerate(pois):
            times = sum(1 for e in recent
                        if e.get("map") == map_name
                        and e.get("poi") == poi["label"])
            label = poi["label"]
            kind = poi["kind"]
            is_warp = kind in ("exit", "warp", "connection")
            dist = abs(poi["ty"] - player_y) + abs(poi["tx"] - player_x)
            cut = poi.get("cut")
            if cut and not cut["available"]:
                blocked_trees.append({"label": label, "dist": dist,
                                      "reason": cut["reason"], "hides": cut["hides"]})
                continue
            entry = {
                "icon": _poi_icon(poi),
                "label": label,
                "dist": dist,
                "times_recent": times,
                "is_warp": is_warp,
                "kind": kind,
                "last_said": poi.get("last_interaction"),
                "visited": poi.get("visited"),
                "leads_to_text": (format_leads_to(poi["leads_to"])
                                  if poi.get("leads_to") else ""),
                "can": poi.get("can"),
                "cut_text": ((f"✂️ uses CUT" + (f" — hides: {', '.join(cut['hides'])}"
                                                if cut["hides"] else ""))
                             if cut else ""),
                "_orig_idx": i,
            }
            if is_warp:
                warp_data.append(entry)
            else:
                interact_data.append(entry)
        poi_data = interact_data + warp_data

        active = self.active_subgoal()
        completed = (self._reflect_ai.completed_subgoals()
                     if self._reflect_ai else [])

        system_prompt = _render("overworld_system.j2",
                                goal=self.goal,
                                active_subgoal=active,
                                player_name=player_name)
        user_prompt = _render("overworld_state.j2",
                              map_name=map_name,
                              interactables=interact_data,
                              warps=warp_data,
                              visited_maps=self._visited_maps,
                              history=self._history[-25:],
                              active_subgoal=active,
                              completed_subgoals=completed,
                              party=party or [],
                              pokeballs=pokeballs,
                              has_pokedex=has_pokedex,
                              money=money,
                              key_items=key_items or [],
                              badge_list=_build_badge_list(badges),
                              badge_count=bin(badges).count("1"),
                              last_think=self._last_think,
                              blocked_trees=blocked_trees,
                              trash_grid=(format_trash_grid(interact_data, puzzle)
                                          if puzzle else ""),
                              hm_options=hm_options or [],
                              hm_notes=hm_notes or [],
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
        retry_user_prompt = None
        while attempt <= max_retries:
            _log.start_thinking()
            response = self._llm.invoke([
                messages[0],
                HumanMessage(content=retry_user_prompt or user_prompt),
            ])
            text = response.content or ""
            _log.stop_thinking()
            result = self._parse_response(text, interact_data, warp_data,
                                          hm_options or [])
            if result is not None:
                return result
            attempt += 1
            _log.log_retry()
            _log.log_think(f"(retry {attempt}: couldn't parse response)")
            _log.log_think(f"  raw: {text.strip()}")
            # Retry with a shorter prompt: drop history, add correction
            retry_user_prompt = _render("overworld_state.j2",
                              map_name=map_name,
                              interactables=interact_data,
                              warps=warp_data,
                              visited_maps=self._visited_maps,
                              history=[],
                              active_subgoal=active,
                              completed_subgoals=completed,
                              party=party or [],
                              pokeballs=pokeballs,
                              has_pokedex=has_pokedex,
                              money=money,
                              key_items=key_items or [],
                              badge_list=_build_badge_list(badges),
                              badge_count=bin(badges).count("1"),
                              last_think=self._last_think,
                              blocked_trees=blocked_trees,
                              trash_grid=(format_trash_grid(interact_data, puzzle)
                                          if puzzle else ""),
                              hm_options=hm_options or [],
                              hm_notes=hm_notes or [],
                              ascii_map=render_map(
                                  [pois[p["_orig_idx"]] for p in poi_data],
                                  player_y, player_x, grid,
                                  legend=False) if grid else "")
            retry_user_prompt += (
                f"\n\nERROR: Invalid action. "
                f"Use INTERACT:1-{len(interact_data)} for NPCs/signs/items, "
                f"or GO:1-{len(warp_data)} for warps"
                + (f", or TEACH:1-{len(hm_options)} for HMs" if hm_options else "")
                + ". Respond with exactly: ACTION: INTERACT:<number> or ACTION: GO:<number>"
                + (" or ACTION: TEACH:<number>" if hm_options else "")
            )

        # Max retries exhausted — return None to signal control back to user
        _log.log_think("(max retries — returning control to user)")
        return None

    def _parse_response(self, text, interact_data, warp_data, hm_options=()):
        """Parse LLM response into an action tuple.

        interact_data/warp_data contain _orig_idx for mapping
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

            # INTERACT:<n> — interactable POI (NPC, sign, item)
            if action.startswith("INTERACT:"):
                try:
                    num = int(action[9:].strip())
                    idx = num - 1
                    if 0 <= idx < len(interact_data):
                        orig_idx = interact_data[idx]["_orig_idx"]
                        if think:
                            _log.log_think(think)
                        _log.log_think(f"=> INTERACT with {interact_data[idx]['label']}")
                        self._last_think = think
                        if interact_data[idx].get("kind") == "grass":
                            _log.log_stat("grass")
                        else:
                            _log.log_stat("interact")
                        return ("go", orig_idx, f"INTERACT:{num}")
                except ValueError:
                    pass

            # GO:<n> — warp (exit, connection, stairs)
            if action.startswith("GO:"):
                try:
                    num = int(action[3:].strip())
                    idx = num - 1
                    if 0 <= idx < len(warp_data):
                        orig_idx = warp_data[idx]["_orig_idx"]
                        if think:
                            _log.log_think(think)
                        _log.log_think(f"=> GO to {warp_data[idx]['label']}")
                        self._last_think = think
                        _log.log_stat("warp")
                        return ("go", orig_idx, f"GO:{num}")
                except ValueError:
                    pass

            # TEACH:<n> — teach an HM from the bag
            if action.startswith("TEACH:"):
                try:
                    idx = int(action[6:].strip()) - 1
                except ValueError:
                    idx = -1
                if 0 <= idx < len(hm_options):
                    option = hm_options[idx]
                    if think:
                        _log.log_think(think)
                    _log.log_think(f"=> TEACH {option['hm']} {option['move']}")
                    self._last_think = think
                    _log.log_stat("teach")
                    return ("teach", idx, f"TEACH:{idx + 1}")

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
