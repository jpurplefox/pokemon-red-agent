"""LLM wrapper that keeps the emulator ticking during inference.

Delegates to PyBoyWrapper.run_with_ticking() so the LLM call runs
in a worker thread while the main thread keeps rendering + sound.
"""


class TickingLLM:
    """Wraps an LLMPort to keep the emulator alive during inference.

    Satisfies LLMPort Protocol — drop-in replacement for ChatOllama.
    """

    def __init__(self, llm, pyboy):
        self._llm = llm
        self._pyboy = pyboy

    def invoke(self, messages):
        """Call the LLM while the emulator keeps ticking on main thread."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                return self._pyboy.run_with_ticking(self._llm.invoke, messages)
            except TimeoutError:
                print(f"  ⚠️  LLM timeout (attempt {attempt + 1}/{max_attempts})")
                print(f"  ⚠️  Model: {getattr(self._llm, '_model_name', '?')}")
                print(f"  ⚠️  Messages ({len(messages)}):")
                for i, msg in enumerate(messages):
                    role = msg.__class__.__name__
                    content = msg.content or ""
                    preview = content[:200].replace("\n", "\\n")
                    if len(content) > 200:
                        preview += f"... ({len(content)} chars)"
                    print(f"       [{i}] {role}: {preview}")
                if attempt == max_attempts - 1:
                    from adapters.openai_llm import CloudLLMError
                    raise CloudLLMError("LLM call timed out after retries")
