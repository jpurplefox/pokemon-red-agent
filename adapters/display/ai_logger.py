"""Unified AI logging — coloured console output + AI thoughts window (DRY).


All AI modules inject this as a dependency for consistent output:
- Prompts (system/user) → grey
- AI responses/thoughts → purple
- Actions → green (in AI window)
- Sub-goal events → red (in AI window)
- HUD updates → team, goal, sub-goal, think time
"""

import time

from adapters.display.ai_log_window import ai_log, ai_set_thinking, ai_update_hud
from domain.models import HUDState

_PURPLE = "\033[35m"
_GRAY = "\033[90m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


class _MetricsRegistry:
    """Global registry that tracks metrics across all AILogger instances."""

    def __init__(self):
        self._loggers: dict[str, "AILogger"] = {}

    def register(self, logger: "AILogger"):
        self._loggers[logger._prefix] = logger

    def print_summary(self):
        """Print a compact metrics summary for all agents."""
        parts = []
        for name, log in self._loggers.items():
            if log._invoke_count == 0 and not log._stats:
                continue
            part = f"{name}:"
            if log._invoke_count > 0:
                avg = log._total_think_time / log._invoke_count
                part += f" {log._invoke_count}x"
                if log._retries > 0:
                    part += f" ({log._retries}r)"
                part += f" {log._total_think_time:.0f}s/{avg:.1f}s"
            if log._stats:
                stats_str = " ".join(f"{v}{k}" for k, v in log._stats.items())
                part += f" [{stats_str}]"
            parts.append(part)
        if parts:
            print(f"{_CYAN}  [metrics] {' | '.join(parts)}{_RESET}")


_metrics = _MetricsRegistry()


class AILogger:
    def __init__(self, prefix: str = "AI"):
        self._prefix = prefix
        self._think_start = 0.0
        self._last_think_time = 0.0
        self._action_count = 0
        self._retries = 0
        self._invoke_count = 0
        self._total_think_time = 0.0
        self._stats: dict[str, int] = {}  # custom counters per agent
        _metrics.register(self)

    def log_stat(self, name: str, increment: int = 1):
        """Increment a custom stat counter (e.g. 'wins', 'catches')."""
        self._stats[name] = self._stats.get(name, 0) + increment

    def start_thinking(self):
        """Mark the start of an LLM call to measure think time."""
        self._think_start = time.time()
        ai_set_thinking(True)

    def stop_thinking(self):
        """Mark the end of an LLM call and record elapsed time."""
        if self._think_start > 0:
            self._last_think_time = time.time() - self._think_start
            self._think_start = 0.0
            self._invoke_count += 1
            self._total_think_time += self._last_think_time
        ai_set_thinking(False)
        return self._last_think_time

    @property
    def last_think_time(self) -> float:
        return self._last_think_time

    def log_retry(self):
        """Increment the retry counter."""
        self._retries += 1

    @property
    def retries(self) -> int:
        return self._retries

    def log_prompt(self, label: str, system: str, user: str):
        """Print system+user prompts in grey and start timing."""
        self.start_thinking()
        print(f"{_GRAY}\n{'='*60}")
        print(f"[{label}] SYSTEM:\n{system}")
        print(f"\n[{label}] USER:\n{user}")
        print(f"{'='*60}{_RESET}\n")

    def log_response(self, label: str, text: str):
        """Print LLM response in purple."""
        elapsed = self.stop_thinking()
        print(f"{_PURPLE}[{label}] RESPONSE ({elapsed:.1f}s):\n{text}")
        print(f"{'='*60}{_RESET}\n")

    def log_console(self, msg: str):
        """Print to console only (no HUD window)."""
        parts = []
        if self._action_count > 0:
            parts.append(f"#{self._action_count}")
        if self._last_think_time > 0:
            parts.append(f"{self._last_think_time:.1f}s")
        tag = f"({' '.join(parts)}) " if parts else ""
        print(f"{_PURPLE}  {self._prefix}: {tag}{msg}{_RESET}")

    def log_think(self, msg: str):
        """Print AI reasoning in purple + send to AI window with time and action #."""
        parts = []
        if self._action_count > 0:
            parts.append(f"#{self._action_count}")
        if self._last_think_time > 0:
            parts.append(f"{self._last_think_time:.1f}s")
        tag = f"({' '.join(parts)}) " if parts else ""
        print(f"{_PURPLE}  {self._prefix}: {tag}{msg}{_RESET}")
        # Actions get green with no tag; thoughts get tag + purple
        if msg.startswith("=>"):
            self._to_window(msg, "action")
        else:
            self._to_window(f"{tag}{msg}")

    def log_action(self, msg: str):
        """Print chosen action in purple + send to AI window as action."""
        print(f"{_PURPLE}  {self._prefix}: {msg}{_RESET}")
        self._to_window(msg)

    def log_event(self, msg: str, kind: str = ""):
        """Print + send to AI window with optional kind (e.g. 'memory')."""
        print(f"{_PURPLE}  {self._prefix}: {msg}{_RESET}")
        self._to_window(msg, kind)

    def update_hud(self, state: HUDState):
        """Update the persistent HUD in the pygame window."""
        self._action_count = state.action_count
        team_data = [
            {"name": getattr(m, 'name', '???'),
             "nickname": getattr(m, 'nickname', '???'),
             "level": getattr(m, 'level', 0),
             "hp": getattr(m, 'hp', 0),
             "max_hp": getattr(m, 'max_hp', 1)}
            for m in state.team
        ]
        ai_update_hud(team_data, state.goal, state.subgoal,
                      self._last_think_time, state.action_count,
                      state.badges, state.map_name, state.player_name,
                      state.play_time, self._retries)

    def _to_window(self, msg: str, kind: str = ""):
        """Send to the AI thoughts pygame window (if running)."""
        ai_log(msg, kind)


def print_metrics():
    """Print a compact metrics summary for all agents."""
    _metrics.print_summary()
