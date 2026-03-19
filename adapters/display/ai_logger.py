"""Unified AI logging — coloured console output + AI thoughts window (DRY).

All AI modules inject this as a dependency for consistent output:
- Prompts (system/user) → grey
- AI responses/thoughts → purple
- Actions → green (in AI window)
- Sub-goal events → red (in AI window)
"""

_PURPLE = "\033[35m"
_GRAY = "\033[90m"
_RESET = "\033[0m"


class AILogger:
    def __init__(self, prefix: str = "AI"):
        self._prefix = prefix

    def log_prompt(self, label: str, system: str, user: str):
        """Print system+user prompts in grey."""
        print(f"{_GRAY}\n{'='*60}")
        print(f"[{label}] SYSTEM:\n{system}")
        print(f"\n[{label}] USER:\n{user}")
        print(f"{'='*60}{_RESET}\n")

    def log_response(self, label: str, text: str):
        """Print LLM response in purple."""
        print(f"{_PURPLE}[{label}] RESPONSE:\n{text}")
        print(f"{'='*60}{_RESET}\n")

    def log_think(self, msg: str):
        """Print AI reasoning in purple + send to AI window."""
        print(f"{_PURPLE}  {self._prefix}: {msg}{_RESET}")
        self._to_window(msg)

    def log_action(self, msg: str):
        """Print chosen action in purple + send to AI window as action."""
        print(f"{_PURPLE}  {self._prefix}: {msg}{_RESET}")
        self._to_window(msg)

    def log_event(self, msg: str, kind: str = ""):
        """Print + send to AI window with optional kind (e.g. 'memory')."""
        print(f"{_PURPLE}  {self._prefix}: {msg}{_RESET}")
        self._to_window(msg, kind)

    def _to_window(self, msg: str, kind: str = ""):
        """Send to the AI thoughts pygame window (if running)."""
        try:
            from adapters.display.ai_log_window import ai_log
            ai_log(msg, kind)
        except Exception:
            pass
