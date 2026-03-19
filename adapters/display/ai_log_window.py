"""Separate pygame window that displays AI thoughts in a terminal style.

Spawns a child PROCESS (not thread) because macOS requires SDL/pygame
to run on the main thread of its process.  The parent sends lines via
a multiprocessing Queue.

Other modules just call `ai_log(text)` — the process starts on first call.
"""

from __future__ import annotations

import multiprocessing as mp
import textwrap

# ── Public API ────────────────────────────────────────────────────────

_queue: mp.Queue | None = None
_process: mp.Process | None = None
_started = False


def start():
    """Start the AI log window immediately."""
    global _started, _queue, _process
    if not _started:
        _queue = mp.Queue()
        _process = mp.Process(target=_run, args=(_queue,), daemon=True)
        _process.start()
        _started = True


def ai_log(text: str, kind: str = ""):
    """Append a line (or multi-line) to the AI log window.

    kind: "" for normal, "memory" for red memory lines.
    """
    if not _started:
        start()
    for line in text.split("\n"):
        _queue.put((line, kind))


# ── Window config ─────────────────────────────────────────────────────

_WIDTH = 520
_HEIGHT = 400
_FONT_SIZE = 14
_LINE_SPACING = 2
_PADDING = 10
_BG = (18, 18, 24)
_FG = (200, 180, 255)
_FG_DIM = (100, 90, 140)
_FG_ACTION = (130, 220, 160)   # green for chosen actions
_FG_MEMORY = (255, 80, 80)    # red for memory saves
_TITLE_BG = (30, 28, 40)
_TITLE_FG = (160, 140, 220)


# ── Main loop (runs in child process) ─────────────────────────────────

def _run(q: mp.Queue):
    import os
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    # Suppress macOS SDL/IMK warnings
    os.environ.setdefault("SDL_LOG_PRIORITY", "quiet")

    import contextlib, io
    with contextlib.redirect_stderr(io.StringIO()):
        import pygame
        pygame.init()
    screen = pygame.display.set_mode((_WIDTH, _HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("AI Thoughts")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("menlo,consolas,monospace", _FONT_SIZE)

    lines: list[tuple[str, tuple[int, int, int]]] = []
    scroll_offset = 0
    max_visible = 0
    auto_scroll = True

    running = True
    while running:
        # ── Events ────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEWHEEL:
                scroll_offset -= event.y * 3
                auto_scroll = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_END:
                    auto_scroll = True

        # ── Drain message queue ───────────────────────────────────
        while True:
            try:
                msg = q.get_nowait()
            except Exception:
                break

            # Support both old str and new (str, kind) format
            if isinstance(msg, tuple):
                text, kind = msg
            else:
                text, kind = msg, ""

            wrap_width = (screen.get_width() - _PADDING * 2) // (font.size("M")[0])
            wrap_width = max(wrap_width, 20)

            if kind == "memory":
                color = _FG_MEMORY
            elif text.startswith("---"):
                new_block = [("", _FG), (text, _FG_DIM)]
                lines[0:0] = new_block
                continue
            elif text.startswith("=>"):
                color = _FG_ACTION
            elif text.strip() == "":
                lines.insert(0, ("", _FG))
                continue
            else:
                color = _FG

            wrapped = textwrap.wrap(text, width=wrap_width) if text.strip() else [""]
            # Insert at top in correct order
            for idx, wl in enumerate(wrapped):
                lines.insert(idx, (wl, color))

            if auto_scroll:
                scroll_offset = 0

        # ── Render ────────────────────────────────────────────────
        w, h = screen.get_size()
        screen.fill(_BG)

        # Title bar
        pygame.draw.rect(screen, _TITLE_BG, (0, 0, w, 26))
        title_surf = font.render("AI Thoughts", True, _TITLE_FG)
        screen.blit(title_surf, (8, 5))

        # Lines
        line_h = _FONT_SIZE + _LINE_SPACING
        max_visible = (h - 30) // line_h
        scroll_offset = max(0, min(scroll_offset, max(0, len(lines) - max_visible)))

        y = 30
        start = scroll_offset
        end = min(start + max_visible, len(lines))
        for i in range(start, end):
            text, color = lines[i]
            if text:
                surf = font.render(text, True, color)
                screen.blit(surf, (_PADDING, y))
            y += line_h

        # Scroll indicator
        if len(lines) > max_visible:
            total = max(len(lines), 1)
            scrollable = max(len(lines) - max_visible, 1)
            bar_h = max(20, int(max_visible / total * (h - 30)))
            bar_y = 30 + int(scroll_offset / scrollable * (h - 30 - bar_h))
            pygame.draw.rect(screen, _FG_DIM, (w - 6, bar_y, 4, bar_h),
                             border_radius=2)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
