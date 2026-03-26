"""MLX LLM adapter — runs Qwen locally on Apple Silicon GPU via mlx-lm.

Satisfies the LLMPort Protocol: invoke(messages) → response with .content
"""

import re
from dataclasses import dataclass
import mlx.core as mx
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


@dataclass
class _Response:
    """Minimal response object matching LangChain's interface."""
    content: str


class _ThinkingBudgetProcessor:
    """Logits processor that forces </think> after a token budget.

    Once the model has generated `budget` tokens inside a <think> block,
    this processor forces a newline followed by </think> so the model
    switches to answer mode instead of thinking forever.
    """

    def __init__(self, tokenizer, budget: int):
        self._budget = budget
        self._think_end_id = tokenizer.encode("</think>", add_special_tokens=False)[0]
        self._nl_id = tokenizer.encode("\n", add_special_tokens=False)[0]
        self._thinking_tokens = 0
        self._inside_think = True  # Qwen starts in thinking mode
        self._forcing_end = False

    def __call__(self, tokens, logits):
        if not self._inside_think:
            return logits

        self._thinking_tokens += 1

        if self._thinking_tokens >= self._budget:
            # Force a newline first, then </think>
            if not self._forcing_end:
                self._forcing_end = True
                forced = mx.full(logits.shape, -1e9)
                forced[self._nl_id] = 0.0
                return forced
            else:
                self._inside_think = False
                forced = mx.full(logits.shape, -1e9)
                forced[self._think_end_id] = 0.0
                return forced

        # Check if model naturally ended thinking
        if tokens.size > 0:
            last = tokens[-1].item()
            if last == self._think_end_id:
                self._inside_think = False

        return logits


class MLXLLM:
    """Local LLM inference using MLX on Apple Silicon."""

    def __init__(self, model_name: str = "mlx-community/Qwen3.5-9B-4bit",
                 max_tokens: int = 512, temperature: float = 0.3,
                 enable_thinking: bool = False,
                 thinking_budget: int | None = None):
        self._model, self._tokenizer = load(model_name)  # type: ignore[misc]
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._enable_thinking = enable_thinking
        self._thinking_budget = thinking_budget

    def invoke(self, messages: list) -> _Response:  # type: ignore[type-arg]
        """Send messages to the local MLX model and return a response."""
        # Convert LangChain-style messages to chat format
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if hasattr(msg, 'type'):
                role = "system" if msg.type == "system" else "user"
            elif hasattr(msg, 'role'):
                role = msg.role
            else:
                role = "user"
            chat_messages.append({"role": role, "content": msg.content})

        # Ensure alternating roles — merge consecutive same-role messages
        # and fold system into first user for models that don't support it
        merged: list[dict[str, str]] = []
        for m in chat_messages:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n\n" + m["content"]
            elif merged and m["role"] == "system":
                # Fold system into next user or previous message
                merged[-1]["content"] += "\n\n" + m["content"]
            else:
                merged.append(dict(m))
        # If first message is system and model doesn't support it,
        # merge into first user message
        if len(merged) >= 2 and merged[0]["role"] == "system":
            # Try keeping system — if template fails, we'll merge below
            chat_messages = merged
        else:
            chat_messages = merged

        template_kwargs = dict(
            tokenize=False, add_generation_prompt=True,
        )
        if not self._enable_thinking:
            template_kwargs["enable_thinking"] = False
        try:
            prompt = self._tokenizer.apply_chat_template(
                chat_messages, **template_kwargs,
            )
        except Exception:
            # Model doesn't support system role — merge system into user
            if chat_messages and chat_messages[0]["role"] == "system":
                system_content = chat_messages[0]["content"]
                chat_messages = chat_messages[1:]
                if chat_messages:
                    chat_messages[0]["content"] = (
                        system_content + "\n\n" + chat_messages[0]["content"]
                    )
                else:
                    chat_messages = [{"role": "user", "content": system_content}]
            prompt = self._tokenizer.apply_chat_template(
                chat_messages, **template_kwargs,
            )

        sampler = make_sampler(temp=self._temperature)

        generate_kwargs = dict(
            prompt=prompt,
            max_tokens=self._max_tokens,
            sampler=sampler,
            verbose=False,
        )

        # Apply thinking budget via logits processor
        if self._enable_thinking and self._thinking_budget is not None:
            processor = _ThinkingBudgetProcessor(
                self._tokenizer, self._thinking_budget,
            )
            generate_kwargs["logits_processors"] = [processor]

        text = generate(self._model, self._tokenizer, **generate_kwargs)

        # Strip <think>…</think> blocks when thinking is enabled
        if self._enable_thinking:
            text = _THINK_RE.sub("", text).strip()

        return _Response(content=text)
