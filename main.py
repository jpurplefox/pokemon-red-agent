import sys
from dotenv import load_dotenv
load_dotenv()
from pyboy import PyBoy
from adapters.pyboy_wrapper import PyBoyWrapper
from adapters.display.ai_log_window import start as start_ai_window
from adapters.ticking_llm import TickingLLM
from adapters.mlx_llm import MLXLLM
from adapters.openai_llm import OpenAILLM
from agents.naming_ai import NamingAI, RandomNamingAI
from agents.move_ai import MoveAI
from agents.battle_ai import BattleAI
from agents.scout_ai import ScoutAI
from agents.overworld_ai import OverworldAI
from agents.reflect_ai import ReflectAI
from agents.lead_ai import LeadAI
from agents.shop_ai import ShopAI
from agents.jev_ai import (JevOverworldAI, JevScoutAI, JevMoveAI, JevLeadAI,
                           JevReflectAI, JevBattleAI)
from adapters.jev_client import make_jev_client, JEV_MODEL
from adapters.persistence.json_store import FileJSONStore
from domain.world import World
from orchestration.game import Game

ROM = "rom.gb"

# OpenRouter model presets (--model <name>) — models evaluated in the paper
CLOUD_MODELS = {
    "qwen3.5-9b":        "qwen/qwen3.5-9b",
    "qwen3.5-27b":       "qwen/qwen3.5-27b",
    "qwen3.5-35b-a3b":   "qwen/qwen3.5-35b-a3b",
    "qwen3.5-122b-a10b": "qwen/qwen3.5-122b-a10b",
    "qwen3.5-397b-a17b": "qwen/qwen3.5-397b-a17b",
    "qwen3.6-plus":      "qwen/qwen3.6-plus",
}


LOCAL_MODELS = {
    "qwen2.5-7b":  "mlx-community/Qwen2.5-7B-Instruct-4bit",
    "qwen2.5-14b": "mlx-community/Qwen2.5-14B-Instruct-4bit",
    "qwen3-14b":   "mlx-community/Qwen3-14B-4bit",
    "qwen3.5-9b":  "mlx-community/Qwen3.5-9B-4bit",
    "llama3.1-8b":  "mlx-community/Llama-3.1-8B-Instruct-4bit",
}

DEFAULT_LOCAL_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"


def _parse_flags(args):
    """Extract --model <name> and --local <name> from args."""
    flags = set()
    cloud_model = None
    local_model = None
    args_list = list(args)
    i = 0
    while i < len(args_list):
        if args_list[i] == "--model" and i + 1 < len(args_list):
            cloud_model = args_list[i + 1]
            i += 2
        elif args_list[i] == "--local" and i + 1 < len(args_list):
            local_model = args_list[i + 1]
            i += 2
        else:
            flags.add(args_list[i])
            i += 1
    return cloud_model, local_model, flags


if __name__ == "__main__":
    strategy = None
    naming_ai = None
    move_ai = None
    overworld_ai = None
    lead_ai = None
    shop_ai = None
    world = None
    cloud_model, local_model, flags = _parse_flags(sys.argv[1:])

    raw_pyboy = PyBoy(ROM, sound_emulated="--mute" not in flags)
    pyboy = PyBoyWrapper(raw_pyboy)
    pyboy.set_speed(fast="--fast" in flags)

    start_ai_window()
    enable_thinking = "--thinking" in flags

    if flags & {"--ai", "--naming", "--shop"} and not cloud_model:
        local_id = LOCAL_MODELS.get(local_model, local_model) if local_model else DEFAULT_LOCAL_MODEL
        print(f"Loading local model: {local_id}")
        raw_llm = MLXLLM(
            model_name=local_id,
            temperature=0.3,
        )
        llm = TickingLLM(raw_llm, pyboy)
        naming_ai = NamingAI(llm=llm)
        move_ai = MoveAI(llm=llm)
        print("Naming AI + Move AI enabled (MLX)")

    if "--ai" in flags:
        # If cloud model specified, use it for ALL agents
        if cloud_model:
            model_id = CLOUD_MODELS.get(cloud_model, cloud_model)
            cloud_llm = OpenAILLM(
                model=model_id,
                base_url="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
                enable_thinking=enable_thinking,
            )
            llm = TickingLLM(cloud_llm, pyboy)
            naming_ai = NamingAI(llm=llm)
            move_ai = MoveAI(llm=llm)
            print(f"All agents: {model_id} (OpenRouter)")
        # --jev: closed decisions (overworld, scout, move, lead, sub-goals)
        # + battle turns go to TypeSafe Jev; nicknames are random; no
        # post-battle reflection; only the shop stays on the chat LLM.
        jev = make_jev_client() if "--jev" in flags else None
        scout = JevScoutAI(jev) if jev else ScoutAI(llm=llm)
        # Post-battle reflection (BattleReflectAI) is off in every mode
        if jev:
            strategy = JevBattleAI(jev, llm=llm, scout=scout)
        else:
            strategy = BattleAI(llm=llm, scout=scout)
        reflect_ai = None
        if "--subgoals" in flags:
            subgoal_store = FileJSONStore("overworld_subgoals.json")
            if jev:
                reflect_ai = JevReflectAI(jev, llm=llm, store=subgoal_store)
            else:
                reflect_ai = ReflectAI(llm=llm, store=subgoal_store)
        shop_ai = ShopAI(llm=llm)
        if jev:
            overworld_ai = JevOverworldAI(jev, llm=llm, reflect_ai=reflect_ai,
                                          shop_ai=shop_ai)
            move_ai = JevMoveAI(jev)
            naming_ai = RandomNamingAI()
            lead_ai = JevLeadAI(jev)
            print(f"Overworld + Battle + Scout + Move + Lead + Sub-goals: {JEV_MODEL} (OpenRouter)")
            print("Naming: random from predefined list")
        else:
            overworld_ai = OverworldAI(llm=llm, reflect_ai=reflect_ai,
                                       shop_ai=shop_ai)
            lead_ai = LeadAI(llm=llm)
        world = World(store=FileJSONStore("world_memory.json"))
        print("Battle AI + Scout AI + Overworld AI + Lead AI enabled")
    elif "--shop" in flags:
        shop_ai = ShopAI(llm=llm)
        print("Shop AI enabled (manual overworld control)")

    Game(pyboy, rom_path=ROM, battle_strategy=strategy, naming_ai=naming_ai,
         move_ai=move_ai, overworld_ai=overworld_ai, lead_ai=lead_ai,
         shop_ai=shop_ai, world=world).run()
