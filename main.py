import sys
from game import Game

if __name__ == "__main__":
    strategy = None
    naming_ai = None
    if "--ai" in sys.argv:
        from battle_ai import BattleAI
        from naming_ai import NamingAI
        strategy = BattleAI()
        naming_ai = NamingAI()
        print("Battle AI + Naming AI enabled (qwen2.5 via Ollama)")
    Game("rom.gb", battle_strategy=strategy, naming_ai=naming_ai).run()
