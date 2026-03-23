import sys
from dotenv import load_dotenv
load_dotenv()
from pyboy import PyBoy
from adapters.pyboy_wrapper import PyBoyWrapper
from adapters.display.ai_log_window import start as start_ai_window
from adapters.ticking_llm import TickingLLM
from adapters.mlx_llm import MLXLLM
from adapters.openai_llm import OpenAILLM
from agents.naming_ai import NamingAI
from agents.battle_ai import BattleAI
from agents.battle_reflect_ai import BattleReflectAI
from agents.scout_ai import ScoutAI
from agents.overworld_ai import OverworldAI
from agents.reflect_ai import ReflectAI
from agents.lead_ai import LeadAI
from agents.shop_ai import ShopAI
from orchestration.game import Game

ROM = "rom.gb"

# OpenRouter model presets (--model <name>)
CLOUD_MODELS = {
    "qwen3-30b":  "qwen/qwen3-30b-a3b",
    "qwen3-235b": "qwen/qwen3-235b-a22b",
    "gemini-flash": "google/gemini-2.5-flash",
    "deepseek-v3": "deepseek/deepseek-chat-v3-0324:free",
    "llama4-maverick": "meta-llama/llama-4-maverick:free",
}


def _parse_model_flag(args):
    """Extract --model <name> from args. Returns (model_id, remaining_flags)."""
    flags = set()
    model = None
    args_list = list(args)
    i = 0
    while i < len(args_list):
        if args_list[i] == "--model" and i + 1 < len(args_list):
            model = args_list[i + 1]
            i += 2
        else:
            flags.add(args_list[i])
            i += 1
    return model, flags


if __name__ == "__main__":
    strategy = None
    naming_ai = None
    overworld_ai = None
    lead_ai = None
    shop_ai = None
    model_name, flags = _parse_model_flag(sys.argv[1:])

    raw_pyboy = PyBoy(ROM, sound_emulated="--mute" not in flags)
    pyboy = PyBoyWrapper(raw_pyboy)
    pyboy.set_speed(fast="--fast" in flags)

    start_ai_window()

    if flags & {"--ai", "--naming", "--shop"}:
        print("Loading MLX model...")
        raw_llm = MLXLLM(
            model_name="mlx-community/Qwen3-14B-4bit",
            temperature=0.3,
        )
        llm = TickingLLM(raw_llm, pyboy)
        naming_ai = NamingAI(llm=llm)
        print("Naming AI enabled (MLX)")

    if "--ai" in flags:
        scout = ScoutAI(llm=llm)
        battle_reflect = BattleReflectAI(llm=llm)
        strategy = BattleAI(llm=llm, scout=scout, battle_reflect=battle_reflect)
        reflect_ai = ReflectAI(llm=llm)

        # Overworld LLM: cloud via --model, or local MLX by default
        if model_name:
            model_id = CLOUD_MODELS.get(model_name, model_name)
            cloud_llm = OpenAILLM(
                model=model_id,
                base_url="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
                enable_thinking=False,
            )
            overworld_llm = TickingLLM(cloud_llm, pyboy)
            print(f"Overworld AI: {model_id} (OpenRouter)")
        else:
            overworld_llm = llm
            print("Overworld AI: local MLX")

        overworld_ai = OverworldAI(llm=overworld_llm, reflect_ai=reflect_ai)
        lead_ai = LeadAI(llm=llm)
        print("Battle AI + Scout AI + Overworld AI + Lead AI enabled")
    elif "--shop" in flags:
        shop_ai = ShopAI(llm=llm)
        print("Shop AI enabled (manual overworld control)")

    Game(pyboy, rom_path=ROM, battle_strategy=strategy, naming_ai=naming_ai,
         overworld_ai=overworld_ai, lead_ai=lead_ai, shop_ai=shop_ai).run()
