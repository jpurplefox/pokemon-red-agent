"""Reflect AI — detects and manages sub-goals from gameplay events.

Runs on a separate (typically local) LLM to analyze dialogue and
battle results, creating or completing sub-goals that guide the
overworld exploration agent.
"""

import json
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

    def __init__(self, llm, goal="Become Pokemon Champion"):
        self._llm = llm
        self.goal = goal
        self._subgoals_file = Path("overworld_subgoals.json")
        self._subgoals = self._load_subgoals()
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

    def _load_subgoals(self):
        """Load sub-goals from disk."""
        if self._subgoals_file.exists():
            try:
                data = json.loads(self._subgoals_file.read_text())
                print(f"  Loaded {len(data)} sub-goals from {self._subgoals_file}")
                return data
            except (json.JSONDecodeError, KeyError):
                pass
        return []

    def _save_subgoals(self):
        """Persist sub-goals to disk."""
        self._subgoals_file.write_text(json.dumps(self._subgoals, indent=2))

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
                              completed_subgoals=self.completed_subgoals(),
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
