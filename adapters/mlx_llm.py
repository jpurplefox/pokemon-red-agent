"""MLX LLM adapter — runs Qwen locally on Apple Silicon GPU via mlx-lm.

Satisfies the LLMPort Protocol: invoke(messages) → response with .content
"""

import re
from dataclasses import dataclass

_THINK_CLOSED_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_THINK_UNCLOSED_RE = re.compile(r"<think>.*", re.DOTALL)
_THINKING_BUDGET = 8192


@dataclass
class _Response:
    """Minimal response object matching LangChain's interface."""
    content: str


class MLXLLM:
    """Local LLM inference using MLX on Apple Silicon."""

    def __init__(self, model_name: str = "mlx-community/Qwen3.5-9B-4bit",
                 max_tokens: int = 512, temperature: float = 0.3):
        from mlx_lm import load
        self._model, self._tokenizer = load(model_name)  # type: ignore[misc]
        # Qwen models always produce <think> blocks regardless of config,
        # so always allocate extra tokens for the thinking budget.
        self._max_tokens = max_tokens + _THINKING_BUDGET

    def invoke(self, messages: list) -> _Response:  # type: ignore[type-arg]
        """Send messages to the local MLX model and return a response."""
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler, make_logits_processors
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
            enable_thinking=False,
        )
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

        sampler = make_sampler(
            temp=0.6, top_p=0.9, top_k=40, min_p=0.05,
        )
        logits_processors = make_logits_processors(
            repetition_penalty=1.15, presence_penalty=0.0,
        )
        while True:
            text = generate(self._model, self._tokenizer,
                            prompt=prompt, max_tokens=self._max_tokens,
                            sampler=sampler,
                            logits_processors=logits_processors,
                            verbose=False)
            print(f"  [MLX raw] {text}")

            # Log and strip <think> blocks
            think_match = _THINK_CLOSED_RE.search(text)
            if think_match:
                print(f"  🧠 Thinking: {len(think_match.group())} chars")
            text = _THINK_CLOSED_RE.sub("", text).strip()
            # Strip unclosed <think> blocks (model ran out of tokens mid-thought)
            unclosed_match = _THINK_UNCLOSED_RE.search(text)
            if unclosed_match:
                print(f"  🧠 Thinking (truncated): {len(unclosed_match.group())} chars")
            text = _THINK_UNCLOSED_RE.sub("", text).strip()

            if text:
                return _Response(content=text)
            print("  ⚠️  MLX: empty response, retrying...")
