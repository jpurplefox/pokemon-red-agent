"""PyBoy wrapper — adds speed/sound mode toggle and idle ticking.

Thin proxy that intercepts tick() to control sound per-frame.
During blocking calls (user input, LLM inference), the main thread
keeps ticking the emulator while the blocking work runs in a worker thread.
This satisfies macOS SDL requirement: rendering must happen on main thread.
"""

import os
import signal
from concurrent.futures import ThreadPoolExecutor


def _sigint_handler(signum, frame):
    """Handle Ctrl+C by hard-exiting (PyBoy's C extension eats KeyboardInterrupt)."""
    print("\n\nExiting...")
    os._exit(0)


# Register immediately so Ctrl+C always works, even during PyBoy tick()
signal.signal(signal.SIGINT, _sigint_handler)


class PyBoyWrapper:
    """Wraps a PyBoy instance with speed/sound mode control."""

    def __init__(self, pyboy):
        self._pyboy = pyboy
        self._sound = False
        self._pool = ThreadPoolExecutor(max_workers=1)

    @property
    def is_fast(self) -> bool:
        return not self._sound

    def set_speed(self, fast: bool):
        """Toggle speed mode: fast (unlimited, muted) or normal (60fps, sound)."""
        self._pyboy.set_emulation_speed(0 if fast else 1)
        self._sound = not fast

    def tick(self, count=1, render=True):
        """Tick with sound controlled by current speed mode."""
        if self._sound:
            result = True
            for _ in range(count):
                result = self._pyboy.tick(1, render=render, sound=True)
            return result
        return self._pyboy.tick(count, render=render, sound=False)

    def run_with_ticking(self, fn, *args, **kwargs):
        """Run fn in a worker thread while the main thread keeps ticking."""
        future = self._pool.submit(fn, *args, **kwargs)
        while not future.done():
            self._pyboy.tick(1, render=True, sound=self._sound)
        return future.result()

    def __getattr__(self, name):
        """Proxy all other attributes to the real PyBoy."""
        return getattr(self._pyboy, name)
