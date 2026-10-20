"""TypeSafe Jev client routed through OpenRouter.

Jev is a System One model: it answers typed questions (Choice / Noul / Score)
about a state instead of generating text, so it does not fit the chat-based
LLMPort. Agents that use it call `system_one(state, questions)` directly.
"""

import os

from typesafe_sdk import TypeSafeClient

# Pinned (not jev-latest) so runs are comparable across time.
JEV_MODEL = "jev-1.13"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api"


def make_jev_client(model: str = JEV_MODEL) -> TypeSafeClient:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is required")
    return TypeSafeClient(api_key=api_key, base_url=_OPENROUTER_BASE_URL,
                          model=model)
