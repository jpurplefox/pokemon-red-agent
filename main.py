import sys
from pyboy import PyBoy
from adapters.pyboy_wrapper import PyBoyWrapper
from adapters.display.ai_log_window import start as start_ai_window
from adapters.ticking_llm import TickingLLM
from adapters.mlx_llm import MLXLLM
from agents.naming_ai import NamingAI
from agents.battle_ai import BattleAI
from agents.scout_ai import ScoutAI
from agents.overworld_ai import OverworldAI
from agents.lead_ai import LeadAI
from agents.shop_ai import ShopAI
from orchestration.game import Game

ROM = "rom.gb"

if __name__ == "__main__":
    strategy = None
    naming_ai = None
    overworld_ai = None
    lead_ai = None
    shop_ai = None
    flags = set(sys.argv[1:])

    raw_pyboy = PyBoy(ROM, sound_emulated="--mute" not in flags)
    pyboy = PyBoyWrapper(raw_pyboy)
    pyboy.set_speed(fast="--fast" in flags)

    start_ai_window()

    if flags & {"--ai", "--naming", "--shop"}:
        print("Loading MLX model...")
        raw_llm = MLXLLM(
            model_name="mlx-community/Qwen3.5-9B-4bit",
            temperature=0.3,
        )
        llm = TickingLLM(raw_llm, pyboy)
        naming_ai = NamingAI(llm=llm)
        print("Naming AI enabled (MLX)")

    if "--ai" in flags:
        scout = ScoutAI(llm=llm)
        strategy = BattleAI(llm=llm, scout=scout)
        overworld_ai = OverworldAI(llm=llm)
        lead_ai = LeadAI(llm=llm)
        print("Battle AI + Scout AI + Overworld AI + Lead AI enabled")
    elif "--shop" in flags:
        shop_ai = ShopAI(llm=llm)
        print("Shop AI enabled (manual overworld control)")

    Game(pyboy, rom_path=ROM, battle_strategy=strategy, naming_ai=naming_ai,
         overworld_ai=overworld_ai, lead_ai=lead_ai, shop_ai=shop_ai).run()
