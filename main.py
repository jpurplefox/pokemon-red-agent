import sys
from game import Game

if __name__ == "__main__":
    strategy = None
    if "--ai" in sys.argv:
        from battle_ai import BattleAI
        strategy = BattleAI()
        print("Battle AI enabled (qwen2.5 via Ollama)")
    Game("rom.gb", battle_strategy=strategy).run()
