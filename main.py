import sys
from orchestration.game import Game

if __name__ == "__main__":
    strategy = None
    naming_ai = None
    overworld_ai = None
    shop_ai = None
    flags = set(sys.argv[1:])

    if flags & {"--ai", "--naming", "--shop"}:
        from langchain_ollama import ChatOllama
        # Single shared LLM — the only place ChatOllama is created
        llm = ChatOllama(
            base_url="http://localhost:11434",
            model="qwen2.5:14b",
            temperature=0.3,
        )
        from agents.naming_ai import NamingAI
        naming_ai = NamingAI(llm=llm)
        print("Naming AI enabled")

    if "--ai" in flags:
        from agents.battle_ai import BattleAI
        from agents.scout_ai import ScoutAI
        from agents.overworld_ai import OverworldAI
        scout = ScoutAI(llm=llm)
        strategy = BattleAI(llm=llm, scout=scout)
        overworld_ai = OverworldAI(llm=llm)
        print("Battle AI + Scout AI + Overworld AI enabled")
    elif "--shop" in flags:
        from agents.shop_ai import ShopAI
        shop_ai = ShopAI(llm=llm)
        print("Shop AI enabled (manual overworld control)")

    Game("rom.gb", battle_strategy=strategy, naming_ai=naming_ai,
         overworld_ai=overworld_ai, shop_ai=shop_ai).run()
