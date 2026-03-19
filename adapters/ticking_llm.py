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
        return self._pyboy.run_with_ticking(self._llm.invoke, messages)
