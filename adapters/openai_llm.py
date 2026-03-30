"""Generic OpenAI-compatible LLM adapter.

Works with any provider that exposes an OpenAI-compatible chat endpoint:
Together AI, Alibaba DashScope, OpenRouter, local vLLM, etc.

Satisfies the LLMPort Protocol: invoke(messages) → response with .content
"""

import os
import re
import time
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
                 timeout: float = 180.0):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} environment variable is required")
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self._model = model
        self._model_name = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._strip_thinking = strip_thinking

    def invoke(self, messages: list) -> _Response:  # type: ignore[type-arg]
        """Send messages to the API and return a response.

        Retries indefinitely on API errors with exponential backoff.
        Each individual request is bounded by the client timeout.
        """
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if hasattr(msg, 'type'):
                role = "system" if msg.type == "system" else "user"
            elif hasattr(msg, 'role'):
                role = msg.role
            else:
                role = "user"
            chat_messages.append({"role": role, "content": msg.content})

        attempt = 0
        while True:
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=chat_messages,  # type: ignore[arg-type]
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    extra_body={"enable_thinking": False},
                )
                if not response.choices:
                    attempt += 1
                    wait = min(2 ** attempt, 30)
                    print(f"\n  ⚠️  Empty choices (attempt {attempt}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                msg = response.choices[0].message
                text = msg.content or ""

                # Some models ignore enable_thinking and put output in reasoning_content
                if not text and getattr(msg, "reasoning_content", None):
                    print(f"  ⚠️  content empty but reasoning_content present ({len(msg.reasoning_content)} chars)")
                    text = msg.reasoning_content

                if self._strip_thinking:
                    text = _THINK_RE.sub("", text).strip()

                if not text.strip():
                    attempt += 1
                    wait = min(2 ** attempt, 30)
                    print(f"\n  ⚠️  Empty response (attempt {attempt}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                break
            except Exception as e:
                attempt += 1
                wait = min(2 ** attempt, 30)
                print(f"\n  ⚠️  Cloud LLM error (attempt {attempt}), retrying in {wait}s: {e}")
                time.sleep(wait)

        return _Response(content=text)
