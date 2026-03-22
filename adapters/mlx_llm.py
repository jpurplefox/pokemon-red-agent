"""MLX LLM adapter — runs Qwen locally on Apple Silicon GPU via mlx-lm.

Satisfies the LLMPort Protocol: invoke(messages) → response with .content
"""

from dataclasses import dataclass
from functools import partial
import mlx.core as mx
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler


@dataclass
class _Response:
    """Minimal response object matching LangChain's interface."""
    content: str


class MLXLLM:
    """Local LLM inference using MLX on Apple Silicon."""

    def __init__(self, model_name: str = "mlx-community/Qwen3.5-9B-4bit",
                 max_tokens: int = 256, temperature: float = 0.3,
                 enable_thinking: bool = False):
        self._model, self._tokenizer = load(model_name)
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._enable_thinking = enable_thinking

    def invoke(self, messages: list) -> _Response:
        """Send messages to the local MLX model and return a response."""
        # Convert LangChain-style messages to chat format
        chat_messages = []
        for msg in messages:
            if hasattr(msg, 'type'):
                role = "system" if msg.type == "system" else "user"
            elif hasattr(msg, 'role'):
                role = msg.role
            else:
                role = "user"
            chat_messages.append({"role": role, "content": msg.content})

        template_kwargs = dict(
            tokenize=False, add_generation_prompt=True,
        )
        if not self._enable_thinking:
            template_kwargs["enable_thinking"] = False
        prompt = self._tokenizer.apply_chat_template(
            chat_messages, **template_kwargs,
        )

        sampler = make_sampler(temp=self._temperature)
        text = generate(
            self._model, self._tokenizer, prompt=prompt,
            max_tokens=self._max_tokens, sampler=sampler,
            verbose=False,
        )

        return _Response(content=text)
