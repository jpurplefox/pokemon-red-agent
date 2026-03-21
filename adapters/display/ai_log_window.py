"""Separate pygame window that displays AI thoughts + persistent HUD.

Spawns a child PROCESS (not thread) because macOS requires SDL/pygame
to run on the main thread of its process.  The parent sends lines via
a multiprocessing Queue.

HUD shows: team (3+3 layout), goal, sub-goal — always visible.
Chat log shows AI thoughts with newest at bottom.
"""

from __future__ import annotations

import multiprocessing as mp
import textwrap
import time

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

    kind: "" for normal, "memory" for red/sub-goal lines.
    """
    if not _started:
        start()
    for line in text.split("\n"):
        _queue.put(("log", line, kind))


def ai_update_hud(team=None, goal="", subgoal="", think_time=0.0,
                   action_count=0, badges=0, map_name="", player_name="",
                   play_time="", retries=0):
    """Update the persistent HUD data."""
    if not _started:
        start()
    _queue.put(("hud", team or [], goal, subgoal, think_time,
                action_count, badges, map_name, player_name, play_time,
                retries))


def ai_set_thinking(is_thinking: bool):
    """Signal that AI is thinking (True) or done (False) for live timer."""
    if not _started:
        start()
    _queue.put(("thinking", is_thinking))


# ── Window config ─────────────────────────────────────────────────────

_WIDTH = 480
_HEIGHT = 432
_FONT_SIZE = 15
_FONT_SIZE_HUD = 14
_LINE_SPACING = 2
_PADDING = 10
_BG = (18, 18, 24)
_FG = (200, 180, 255)
_FG_DIM = (100, 90, 140)
_FG_ACTION = (130, 220, 160)
_FG_MEMORY = (255, 80, 80)
_FG_GOAL = (255, 200, 60)
_FG_HP_OK = (130, 220, 160)
_FG_HP_LOW = (255, 200, 60)
_FG_HP_CRIT = (255, 80, 80)
_FG_HP_DEAD = (100, 90, 140)
_HUD_BG = (28, 26, 36)
_TITLE_BG = (30, 28, 40)
_TITLE_FG = (160, 140, 220)
_SEPARATOR = (50, 46, 66)


# ── Main loop (runs in child process) ─────────────────────────────────

def _run(q: mp.Queue):
    import os
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ.setdefault("SDL_LOG_PRIORITY", "quiet")

    import contextlib, io
    with contextlib.redirect_stderr(io.StringIO()):
        import pygame
        pygame.init()
    screen = pygame.display.set_mode((_WIDTH, _HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("AI Thoughts")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("menlo,consolas,monospace", _FONT_SIZE)
    font_hud = pygame.font.SysFont("menlo,consolas,monospace", _FONT_SIZE_HUD)
    font_bold = pygame.font.SysFont("menlo,consolas,monospace", _FONT_SIZE_HUD, bold=True)

    # Each line: (text, color, prefix, prefix_color) — prefix is optional dim tag
    lines: list[tuple[str, tuple[int, int, int], str, tuple[int, int, int]]] = []
    scroll_offset = 0
    auto_scroll = True

    # HUD state
    hud_team = []
    hud_goal = ""
    hud_subgoal = ""
    hud_think_time = 0.0
    hud_action_count = 0
    hud_badges = 0
    hud_map_name = ""
    hud_player_name = ""
    hud_play_time = ""
    hud_retries = 0
    is_thinking = False
    think_start = 0.0

    running = True
    while running:
        # ── Events ────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEWHEEL:
                scroll_offset += event.y * 3
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

            if msg[0] == "hud":
                _, hud_team, hud_goal, hud_subgoal, hud_think_time, \
                    hud_action_count, hud_badges, hud_map_name, \
                    hud_player_name, hud_play_time, hud_retries = msg
                continue

            if msg[0] == "thinking":
                _, thinking_flag = msg
                is_thinking = thinking_flag
                if thinking_flag:
                    think_start = time.time()
                continue

            # Log message
            _, text, kind = msg

            char_w = font.size("M")[0]
            wrap_width = (screen.get_width() - _PADDING * 3) // char_w
            wrap_width = max(wrap_width, 20)

            # Extract (# N Xs) prefix tag if present
            prefix = ""
            if text.startswith("(#"):
                close = text.find(") ")
                if close > 0:
                    prefix = text[:close + 2]
                    text = text[close + 2:]
                    # Separator between different actions
                    if lines and lines[-1][2] and lines[-1][2] != prefix:
                        lines.append(("", _SEPARATOR, "", _SEPARATOR))

            if kind == "memory":
                color = _FG_MEMORY
            elif kind == "action":
                color = _FG_ACTION
            elif kind == "meta":
                color = _FG_DIM
            elif text.startswith("---"):
                lines.append(("", _FG, "", _FG))
                lines.append((text, _FG_DIM, "", _FG))
                continue
            elif text.startswith("=>"):
                color = _FG_ACTION
            elif text.strip() == "":
                lines.append(("", _FG, "", _FG))
                continue
            else:
                color = _FG

            effective_width = wrap_width - len(prefix) if prefix else wrap_width
            effective_width = max(effective_width, 15)
            wrapped = textwrap.wrap(text, width=effective_width) if text.strip() else [""]
            for i_w, wl in enumerate(wrapped):
                # Only first wrapped line gets the prefix
                p = prefix if i_w == 0 else ""
                lines.append((wl, color, p, _FG_DIM))

            if auto_scroll:
                scroll_offset = 0

        # ── Render ────────────────────────────────────────────────
        w, h = screen.get_size()
        screen.fill(_BG)

        # ── HUD (top section) ────────────────────────────────────
        # Live thinking timer
        thinking_elapsed = (time.time() - think_start) if is_thinking else 0.0

        hud_h = _render_hud(screen, font_hud, font_bold, w,
                            hud_team, hud_goal, hud_subgoal, hud_think_time,
                            hud_action_count, hud_badges, thinking_elapsed,
                            hud_map_name, hud_player_name, hud_play_time,
                            hud_retries)

        # Separator line
        pygame.draw.line(screen, _SEPARATOR, (0, hud_h), (w, hud_h), 1)
        chat_top = hud_h + 2

        # ── Chat log (bottom section, newest at bottom) ──────────
        line_h = _FONT_SIZE + _LINE_SPACING
        chat_h = h - chat_top
        max_visible = chat_h // line_h

        # Auto-scroll keeps view at bottom
        total = len(lines)
        if auto_scroll:
            scroll_offset = 0

        scroll_offset = max(0, min(scroll_offset, max(0, total - max_visible)))

        # Draw from bottom up: last lines visible at bottom
        start_idx = max(0, total - max_visible - scroll_offset)
        end_idx = min(total, start_idx + max_visible)

        y = chat_top
        for i in range(start_idx, end_idx):
            text, color, prefix, prefix_color = lines[i]
            # Separator line between actions
            if not text and color == _SEPARATOR:
                sep_y = y + line_h // 2
                pygame.draw.line(screen, _SEPARATOR,
                                 (_PADDING, sep_y), (w - _PADDING, sep_y), 1)
                y += line_h
                continue
            x_off = _PADDING
            if prefix:
                pre_surf = font.render(prefix, True, prefix_color)
                screen.blit(pre_surf, (x_off, y))
                x_off += pre_surf.get_width()
            if text:
                surf = font.render(text, True, color)
                screen.blit(surf, (x_off, y))
            y += line_h

        # Scroll indicator
        if total > max_visible:
            scrollable = max(total - max_visible, 1)
            bar_h = max(20, int(max_visible / total * chat_h))
            bar_pos = 1.0 - (scroll_offset / scrollable)
            bar_y = chat_top + int(bar_pos * (chat_h - bar_h))
            pygame.draw.rect(screen, _FG_DIM, (w - 6, bar_y, 4, bar_h),
                             border_radius=2)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


# Badge symbols + colors by gym type
_BADGE_LABELS = [
    ("\u25C9", (180, 140, 80)),    # ◉ Boulder — brown
    ("\u25C9", (80, 140, 220)),    # ◉ Cascade — blue
    ("\u25C9", (240, 200, 40)),    # ◉ Thunder — yellow
    ("\u25C9", (80, 190, 80)),     # ◉ Rainbow — green
    ("\u25C9", (200, 80, 200)),    # ◉ Soul — purple
    ("\u25C9", (160, 80, 160)),    # ◉ Marsh — pink
    ("\u25C9", (240, 100, 40)),    # ◉ Volcano — orange
    ("\u25C9", (160, 140, 100)),   # ◉ Earth — tan
]
_BADGE_MISSING = (40, 38, 50)      # very dim


def _render_hud(screen, font, font_bold, w, team, goal, subgoal, think_time,
                action_count=0, badges=0, thinking_elapsed=0.0, map_name="",
                player_name="", play_time="", retries=0):
    """Render the persistent HUD at the top. Returns the total HUD height."""
    import pygame

    y = 6
    pad = _PADDING
    line_h = _FONT_SIZE_HUD + 4

    # Background — header + team rows + goal + subgoal/badges
    team_rows = max(len(team), 1)
    rows = 1 + team_rows + 2  # header + team + goal + badges/subgoal
    hud_h_estimate = 12 + line_h * rows + 24
    pygame.draw.rect(screen, _HUD_BG, (0, 0, w, hud_h_estimate))

    # ── Row 1: Player + Map (left), Play time (right) ──────────
    top_left = ""
    if player_name:
        top_left = player_name
    if map_name:
        top_left += f" | {map_name}" if top_left else map_name
    if top_left:
        surf = font_bold.render(top_left, True, _FG)
        screen.blit(surf, (pad, y))
    if play_time:
        pt_surf = font.render(play_time, True, _FG_DIM)
        screen.blit(pt_surf, (w - pad - pt_surf.get_width(), y))

    y += line_h + 2
    pygame.draw.line(screen, _SEPARATOR, (pad, y), (w - pad, y), 1)
    y += 4

    # ── Row 2: Team (one per line) ──────────────────────────────
    char_w = font.size("M")[0]
    for mon in team[:6]:
        name = mon.get("nickname", "???")
        species = mon.get("name", "")
        hp = mon.get("hp", 0)
        max_hp = mon.get("max_hp", 1)
        level = mon.get("level", 0)

        if hp <= 0:
            hp_color = _FG_HP_DEAD
        elif hp < max_hp // 4:
            hp_color = _FG_HP_CRIT
        elif hp < max_hp // 2:
            hp_color = _FG_HP_LOW
        else:
            hp_color = _FG_HP_OK

        hp_text = f"HP:{hp}/{max_hp}"
        hp_surf = font.render(hp_text, True, hp_color)
        hp_w = hp_surf.get_width() + 8

        label = f"Lv{level} {name}"
        if species and species != name:
            label += f" ({species})"
        # Truncate if too long
        max_label_w = w - pad * 2 - hp_w
        while font.size(label)[0] > max_label_w and len(label) > 5:
            label = label[:-1]

        surf = font.render(label, True, _FG)
        screen.blit(surf, (pad, y))
        screen.blit(hp_surf, (w - pad - hp_surf.get_width(), y))
        y += line_h

    if not team:
        surf = font.render("No Pokemon yet!", True, _FG_DIM)
        screen.blit(surf, (pad, y))
        y += line_h

    y += 4

    pygame.draw.line(screen, _SEPARATOR, (pad, y), (w - pad, y), 1)
    y += 4

    # ── Row 3: Goal + stats ──────────────────────────────────
    goal_text = f"GOAL: {goal}" if goal else "GOAL: ---"
    # Truncate goal if needed
    max_goal_w = w - pad * 2 - 100  # leave room for stats
    while font_bold.size(goal_text)[0] > max_goal_w and len(goal_text) > 10:
        goal_text = goal_text[:-1]
    surf = font_bold.render(goal_text, True, _FG_GOAL)
    screen.blit(surf, (pad, y))

    # Timer + retries + count on the right
    right_x = w - pad
    if action_count > 0:
        count_surf = font.render(f"#{action_count}", True, _FG_DIM)
        right_x -= count_surf.get_width()
        screen.blit(count_surf, (right_x, y))
        right_x -= 10
    if retries > 0:
        retry_color = (255, 100, 100) if retries > 5 else (255, 180, 80)
        retry_surf = font.render(f"R:{retries}", True, retry_color)
        right_x -= retry_surf.get_width()
        screen.blit(retry_surf, (right_x, y))
        right_x -= 10

    if thinking_elapsed > 0:
        pulse = int(thinking_elapsed * 2) % 2
        timer_color = _FG_GOAL if pulse else (255, 160, 40)
        timer_text = f"{thinking_elapsed:.1f}s"
        timer_surf = font.render(timer_text, True, timer_color)
        right_x -= timer_surf.get_width()
        screen.blit(timer_surf, (right_x, y))
    elif think_time > 0:
        time_surf = font.render(f"{think_time:.1f}s", True, _FG)
        right_x -= time_surf.get_width()
        screen.blit(time_surf, (right_x, y))

    y += line_h

    # ── Row 4: Sub-goal (left) + Badges (right) ──────────────
    if subgoal:
        sg_text = f"> {subgoal}"
        max_sg_w = w - pad * 2 - 120
        while font.size(sg_text)[0] > max_sg_w and len(sg_text) > 5:
            sg_text = sg_text[:-1]
        surf = font.render(sg_text, True, _FG_MEMORY)
        screen.blit(surf, (pad, y))

    # Badges on the right (colored circles)
    badge_x = w - pad
    for i in range(7, -1, -1):
        obtained = bool(badges & (1 << i))
        symbol, badge_color = _BADGE_LABELS[i]
        color = badge_color if obtained else _BADGE_MISSING
        surf = font_bold.render(symbol, True, color)
        badge_x -= surf.get_width() + 2
        screen.blit(surf, (badge_x, y))

    y += line_h + 4
    return y
