import sys
from pyboy import PyBoy
from adapters.pyboy_wrapper import PyBoyWrapper
from adapters.display.ai_log_window import start as start_ai_window
from adapters.ticking_llm import TickingLLM
from langchain_ollama import ChatOllama
from agents.naming_ai import NamingAI
from agents.battle_ai import BattleAI
from agents.scout_ai import ScoutAI
from agents.overworld_ai import OverworldAI
from agents.shop_ai import ShopAI
from orchestration.game import Game

ROM = "rom.gb"

if __name__ == "__main__":
    strategy = None
    naming_ai = None
    overworld_ai = None
    shop_ai = None
    flags = set(sys.argv[1:])

    raw_pyboy = PyBoy(ROM, sound_emulated=True)
    pyboy = PyBoyWrapper(raw_pyboy)
    pyboy.set_speed(fast="--fast" in flags)

    start_ai_window()

    if flags & {"--ai", "--naming", "--shop"}:
        raw_llm = ChatOllama(
            base_url="http://localhost:11434",
            model="qwen2.5:14b",
            temperature=0.3,
        )
        llm = TickingLLM(raw_llm, pyboy)
        naming_ai = NamingAI(llm=llm)
        print("Naming AI enabled")

    if "--ai" in flags:
        scout = ScoutAI(llm=llm)
        strategy = BattleAI(llm=llm, scout=scout)
        overworld_ai = OverworldAI(llm=llm)
        print("Battle AI + Scout AI + Overworld AI enabled")
    elif "--shop" in flags:
        shop_ai = ShopAI(llm=llm)
        print("Shop AI enabled (manual overworld control)")

    Game(pyboy, rom_path=ROM, battle_strategy=strategy, naming_ai=naming_ai,
         overworld_ai=overworld_ai, shop_ai=shop_ai).run()
