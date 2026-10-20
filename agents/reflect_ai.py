"""Reflect AI — detects and manages sub-goals from gameplay events.

Runs on a separate (typically local) LLM to analyze dialogue and
battle results, creating or completing sub-goals that guide the
overworld exploration agent.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import SystemMessage, HumanMessage

from adapters.display.ai_logger import AILogger

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES),
                   keep_trailing_newline=True)

_DEBUG_PROMPTS = True
_log = AILogger("REFLECT")


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


class ReflectAI:
    """Analyzes gameplay events and manages sub-goals."""

    def __init__(self, llm, goal="Become Pokemon Champion", store=None):
        self._llm = llm
        self.goal = goal
        self._store = store
        self._subgoals = self._store.load() if self._store else []
        if self._subgoals:
            print(f"  Loaded {len(self._subgoals)} sub-goals")
        self._iteration = 0

    @property
    def iteration(self) -> int:
        return self._iteration

    @iteration.setter
    def iteration(self, value: int):
        self._iteration = value

    def active_subgoal(self):
        """Return the current active sub-goal dict, or None."""
        for sg in self._subgoals:
            if sg["status"] == "active":
                return sg
        return None

    def completed_subgoals(self):
        """Return list of completed sub-goals."""
        return [sg for sg in self._subgoals if sg["status"] == "done"]

    def _save_subgoals(self):
        """Persist sub-goals via the injected store."""
        if self._store:
            self._store.save(self._subgoals)

    def reflect(self, map_name, action, result="", dialogue="",
                player_name=""):
        """Ask the LLM to reflect and detect/complete sub-goals."""
        active = self.active_subgoal()

        system_prompt = _render("overworld_reflect.j2",
                                player_name=player_name)
        user_prompt = _render("overworld_reflect_state.j2",
                              map_name=map_name,
                              action=action,
                              result=result,
                              dialogue=dialogue,
                              active_subgoal=active,
                              completed_subgoals=self.completed_subgoals(),
                              main_goal=self.goal)

        if _DEBUG_PROMPTS:
            _log.log_prompt("REFLECT", system_prompt, user_prompt)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self._llm.invoke(messages)
        text = response.content or ""

        if _DEBUG_PROMPTS:
            _log.log_response("REFLECT", text)

        # Parse response
        subgoal_action = ""
        subgoal_desc = ""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                subgoal_action = line[7:].strip().lower()
            elif line.startswith("GOAL:"):
                subgoal_desc = line[5:].strip()

        self._apply(subgoal_action, subgoal_desc)

    def _apply(self, subgoal_action, subgoal_desc=""):
        """Create, complete or ignore a sub-goal ("new" / "done" / other)."""
        active = self.active_subgoal()
        if subgoal_action == "new" and subgoal_desc:
            if active and active["description"].lower() == subgoal_desc.lower():
                return
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
            self._save_subgoals()
            _log.log_stat("goals")
            msg = f"🎯 New sub-goal: {subgoal_desc}"
            print(f"  {_GREEN}OW: {msg}{_RESET}")
            _log.log_event(msg, "memory")

        elif subgoal_action == "done" and active:
            active["status"] = "done"
            active["done_at"] = self._iteration
            self._save_subgoals()
            msg = f"✅ Sub-goal completed: {active['description']}"
            print(f"  {_GREEN}OW: {msg}{_RESET}")
            _log.log_event(msg, "memory")
