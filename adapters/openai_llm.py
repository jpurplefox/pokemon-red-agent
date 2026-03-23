"""Generic OpenAI-compatible LLM adapter.

Works with any provider that exposes an OpenAI-compatible chat endpoint:
Together AI, Alibaba DashScope, OpenRouter, local vLLM, etc.

Satisfies the LLMPort Protocol: invoke(messages) → response with .content
"""

import os
import re
from dataclasses import dataclass

from openai import OpenAI

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


@dataclass
class _Response:
    """Minimal response object matching LangChain's interface."""
    content: str


class OpenAILLM:
    """LLM inference via any OpenAI-compatible endpoint."""

    def __init__(self, *, model: str, base_url: str, api_key_env: str,
                 max_tokens: int = 512, temperature: float = 0.3,
                 strip_thinking: bool = False,
                 enable_thinking: bool = True):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} environment variable is required")
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._strip_thinking = strip_thinking
        self._enable_thinking = enable_thinking

    def invoke(self, messages: list) -> _Response:
        """Send messages to the API and return a response."""
        chat_messages = []
        for msg in messages:
            if hasattr(msg, 'type'):
                role = "system" if msg.type == "system" else "user"
            elif hasattr(msg, 'role'):
                role = msg.role
            else:
                role = "user"
            chat_messages.append({"role": role, "content": msg.content})

        kwargs = dict(
            model=self._model,
            messages=chat_messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        if not self._enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": False}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"\n  ⚠️  Cloud LLM error: {e}")
            raise CloudLLMError(str(e)) from e

        text = response.choices[0].message.content

        if self._strip_thinking:
            text = _THINK_RE.sub("", text).strip()

        return _Response(content=text)


class CloudLLMError(Exception):
    """Raised when the cloud LLM API call fails."""
