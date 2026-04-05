"""Generic OpenAI-compatible LLM adapter.

Works with any provider that exposes an OpenAI-compatible chat endpoint:
Together AI, Alibaba DashScope, OpenRouter, local vLLM, etc.

Uses httpx directly for reliable timeout control.
Satisfies the LLMPort Protocol: invoke(messages) → response with .content
"""

import os
import re
import time
from dataclasses import dataclass

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_THINKING_BUDGET = 4096


@dataclass
class _Response:
    """Minimal response object matching LangChain's interface."""
    content: str


class OpenAILLM:
    """LLM inference via any OpenAI-compatible endpoint."""

    def __init__(self, *, model: str, base_url: str, api_key_env: str,
                 max_tokens: int = 512, temperature: float = 0.3,
                 strip_thinking: bool = False,
                 enable_thinking: bool = False,
                 timeout: float = 120.0):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} environment variable is required")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._model_name = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._strip_thinking = strip_thinking
        self._enable_thinking = enable_thinking
        self._timeout = timeout

    def invoke(self, messages: list) -> _Response:  # type: ignore[type-arg]
        """Send messages to the API and return a response.

        Retries indefinitely on API errors with exponential backoff.
        Each individual request is bounded by the timeout.
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

        if self._enable_thinking:
            payload = {
                "model": self._model,
                "messages": chat_messages,
                "max_tokens": self._max_tokens + _THINKING_BUDGET,
                "temperature": self._temperature,
                "enable_thinking": True,
                "thinking": {"budget_tokens": _THINKING_BUDGET},
            }
        else:
            payload = {
                "model": self._model,
                "messages": chat_messages,
                "max_tokens": self._max_tokens,
                "temperature": self._temperature,
            }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        attempt = 0
        while True:
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                resp.raise_for_status()
                data = resp.json()

                choices = data.get("choices", [])
                if not choices:
                    attempt += 1
                    wait = min(2 ** attempt, 30)
                    print(f"\n  ⚠️  Empty choices (attempt {attempt}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                msg = choices[0].get("message", {})
                text = msg.get("content") or ""

                # Check for reasoning (field name varies by provider)
                reasoning = (msg.get("reasoning") or
                             msg.get("reasoning_content") or "")
                if reasoning:
                    print(f"  🧠 Thinking: {len(reasoning)} chars")
                if not text and reasoning:
                    print(f"  ⚠️  content empty, using reasoning")
                    text = reasoning

                # Always strip <think> tags from content (some models
                # embed them inline even with structured reasoning)
                text = _THINK_RE.sub("", text).strip()

                if not text.strip():
                    attempt += 1
                    wait = min(2 ** attempt, 30)
                    print(f"\n  ⚠️  Empty response (attempt {attempt}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                break
            except httpx.TimeoutException as e:
                attempt += 1
                wait = min(2 ** attempt, 30)
                print(f"\n  ⏱️  Timeout after {self._timeout}s (attempt {attempt}), retrying in {wait}s...")
                time.sleep(wait)
            except Exception as e:
                attempt += 1
                wait = min(2 ** attempt, 30)
                print(f"\n  ⚠️  Cloud LLM error (attempt {attempt}), retrying in {wait}s: {e}")
                time.sleep(wait)

        return _Response(content=text)
