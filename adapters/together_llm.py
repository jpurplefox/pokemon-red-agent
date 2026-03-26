"""Together AI adapter — uses the OpenAI-compatible API.

Satisfies the LLMPort Protocol: invoke(messages) → response with .content
Requires TOGETHER_API_KEY environment variable.
"""

import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class _Response:
    """Minimal response object matching LangChain's interface."""
    content: str


class TogetherLLM:
    """LLM inference via Together AI's OpenAI-compatible endpoint."""

    def __init__(self, model: str = "Qwen/Qwen3-Next-80B-A3B-Instruct",
                 max_tokens: int = 512, temperature: float = 0.3):
        api_key = os.environ.get("TOGETHER_API_KEY")
        if not api_key:
            raise RuntimeError("TOGETHER_API_KEY environment variable is required")
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.together.xyz/v1",
        )
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    def invoke(self, messages: list) -> _Response:  # type: ignore[type-arg]
        """Send messages to Together AI and return a response."""
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if hasattr(msg, 'type'):
                role = "system" if msg.type == "system" else "user"
            elif hasattr(msg, 'role'):
                role = msg.role
            else:
                role = "user"
            chat_messages.append({"role": role, "content": msg.content})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=chat_messages,  # type: ignore[arg-type]
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        return _Response(content=response.choices[0].message.content or "")
