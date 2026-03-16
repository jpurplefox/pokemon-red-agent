class DialogueAdvancer:
    def __init__(self, pyboy, screen):
        self._pyboy = pyboy
        self._screen = screen

    def advance_until(self, stop_condition):
        """Press A through dialogue until stop_condition returns True.

        stop_condition(has_dialogue: bool, unchanged_count: int) -> bool

        Examples:
            # Stop when a name menu appears
            advance_until(lambda d, u: menu.is_name_menu())

            # Stop after prolonged silence (e.g. scene transition)
            advance_until(lambda d, u: d and u > 30)
        """
        dialogue = []
        last_captured = ""
        unchanged_count = 0

        while True:
            if stop_condition(len(dialogue) > 0, unchanged_count):
                break

            # Wait for text to stabilize (letter-by-letter animation)
            prev = ""
            current = self._screen.read_text_box()
            while current != prev:
                prev = current
                self._pyboy.tick(10)
                current = self._screen.read_text_box()
                if stop_condition(len(dialogue) > 0, unchanged_count):
                    break

            if stop_condition(len(dialogue) > 0, unchanged_count):
                break

            if current and current != last_captured:
                dialogue.append(current)
                last_captured = current
                unchanged_count = 0
            elif not current and dialogue:
                # Text box closed — keep waiting but don't press A
                # (pressing A could re-trigger nearby interactables)
                unchanged_count += 1
                self._pyboy.tick(10)
                continue
            else:
                unchanged_count += 1

            # Re-check stop condition BEFORE pressing A
            # (a menu cursor may have appeared with the new text)
            if stop_condition(len(dialogue) > 0, unchanged_count):
                break

            self._pyboy.button("a")
            self._pyboy.tick(10)

        return self.deduplicate(dialogue)

    @staticmethod
    def deduplicate(lines):
        """Remove overlapping text between consecutive captures.
        The text box shows 2 lines at a time, so when it scrolls,
        the next capture starts with text from the previous one."""
        if not lines:
            return ""
        result = [lines[0]]
        for line in lines[1:]:
            prev = result[-1]
            overlap = ""
            for length in range(min(len(prev), len(line)), 0, -1):
                if line.startswith(prev[-length:]):
                    overlap = prev[-length:]
                    break
            if overlap:
                new_text = line[len(overlap):]
                if new_text.strip():
                    result.append(new_text.strip())
            else:
                result.append(line)
        return " ".join(result)
