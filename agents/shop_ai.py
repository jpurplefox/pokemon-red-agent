"""Shop AI — uses a local LLM to decide what to buy at Poké Marts (ISP).

Extracted from OverworldAI to satisfy Interface Segregation:
shop-only mode no longer needs the full overworld exploration system.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import HumanMessage
from adapters.display.ai_logger import AILogger

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), trim_blocks=True,
                   lstrip_blocks=True)
_log = AILogger("SHOP")
_DEBUG_PROMPTS = True


def _render(template_name, **kwargs):
    return _env.get_template(template_name).render(**kwargs)


class ShopAI:
    """LLM-based purchasing decisions for Poké Marts."""

    def __init__(self, llm):
        self._llm = llm

    def decide_purchases(self, items, money, pokeballs, party=None):
        """Ask the LLM what to buy at a Poké Mart.

        Returns list of (item_index, quantity) tuples.
        """
        user_prompt = _render("shop_state.j2",
                              items=items, money=money,
                              pokeballs=pokeballs,
                              party=party or [])

        if _DEBUG_PROMPTS:
            _log.log_prompt("SHOP", "(inline)", user_prompt)

        messages = [HumanMessage(content=user_prompt)]
        for _empty_retry in range(3):
            response = self._llm.invoke(messages)
            text = response.content or ""
            if text.strip():
                break
            print(f"  ⚠️  Shop: empty response (attempt {_empty_retry + 1}/3)")

        if _DEBUG_PROMPTS:
            _log.log_response("SHOP", text)

        # Parse BUY lines
        purchases = []
        think = ""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("THINK:"):
                think = line[6:].strip()
            elif line.startswith("BUY:"):
                try:
                    parts = line[4:].strip().split("x")
                    idx = int(parts[0].strip()) - 1  # 1-based → 0-based
                    qty = int(parts[1].strip())
                    if 0 <= idx < len(items) and qty > 0:
                        purchases.append((idx, qty))
                except (ValueError, IndexError):
                    pass

        if think:
            _log.log_think(f"🛒 {think}")

        if purchases:
            _log.log_stat("buys")
            for idx, qty in purchases:
                _log.log_think(f"=> BUY {qty}x {items[idx]['name']}")
        else:
            _log.log_think("=> Nothing to buy")

        return purchases
