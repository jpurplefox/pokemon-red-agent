# Pokemon Red AI Agent

An autonomous AI agent that plays Pokemon Red on a Game Boy emulator, making real-time decisions using an LLM (cloud or local).

The agent reads the game's memory to understand the world, reasons about what to do next, and presses buttons to execute its decisions — no scripting, no hardcoded paths.

## What it does

- **Explores the overworld** — navigates maps, talks to NPCs, enters buildings, reads signs
- **Fights battles** — chooses moves based on type advantages, STAB, and enemy HP
- **Manages inventory** — buys Poke Balls at marts, heals at Pokemon Centers
- **Tracks quests** — detects side-quests from dialogue and prioritizes them
- **Names Pokemon** — generates creative nicknames for caught Pokemon
- **Decides what to catch** — evaluates wild Pokemon against current team composition
- **Learns new moves** — decides whether to teach a new move on level-up and which old one to replace

## How it works

The agent reads Pokemon Red's WRAM (working RAM) to extract game state: map position, nearby points of interest, party HP, battle stats, inventory. This state is rendered into text prompts via Jinja2 templates and sent to an LLM — either a cloud model via the OpenRouter API or a local model running on Apple Silicon via MLX. The LLM responds with a structured action (`GO:3`, `MOVE:TACKLE`, `BUY: 1 x3`), which is parsed and translated into button presses on the emulator.

```
Game Boy (PyBoy)  -->  State Readers  -->  Domain Objects  -->  LLM Agent  -->  Menu Driver  -->  Game Boy
     WRAM               (adapters)        (dataclasses)      (reasoning)      (adapters)       button presses
```

## Setup

### Requirements

- Python 3.11+
- A Pokemon Red ROM file named `rom.gb` in the repo root. ROMs are copyrighted; obtain one by dumping the cartridge you own. None is provided here.
- For cloud inference: an [OpenRouter](https://openrouter.ai) API key
- For local inference (optional): an Apple Silicon Mac (MLX requirement)

### Install

```bash
# Cloud-only setup (works on any platform)
pip install .

# With local inference support (Apple Silicon only)
pip install '.[local]'
```

### Configure

Copy `.env.example` to `.env` and set your key:

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY
```

### Run

```bash
# Manual mode (you control everything)
python main.py

# Full AI mode with a cloud model via OpenRouter
python main.py --ai --model qwen3.5-27b

# Full AI mode with a local MLX model (Apple Silicon)
python main.py --ai --local qwen2.5-14b

# Closed decisions (overworld, battle, catch, move, lead, sub-goals) on TypeSafe
# Jev via OpenRouter, random nicknames, no post-battle reflection; shop stays on --model
python main.py --ai --model qwen3.5-27b --jev
```

Cloud model presets (the six Qwen models evaluated in the paper): `qwen3.5-9b`, `qwen3.5-27b`, `qwen3.5-35b-a3b`, `qwen3.5-122b-a10b`, `qwen3.5-397b-a17b`, `qwen3.6-plus`. You can also pass any other OpenRouter model ID directly, but only these have been tested. See `main.py` for the full list of local MLX presets.

### Controls (manual mode)

| Command | Action |
|---------|--------|
| `up/down/left/right` | Move |
| `a/b/start/select` | Game Boy buttons |
| `go` | Navigate to a point of interest |
| `look` | Show nearby POIs and map |
| `lead` | Change lead Pokemon |
| `ai` | Resume AI control (after pausing) |
| `quit` | Exit |

During AI mode, press **Enter** to pause the AI and take manual control.

## Tech Stack

- **[PyBoy](https://github.com/Baekalfen/PyBoy)** — Game Boy emulator with Python API
- **[OpenRouter](https://openrouter.ai)** — Cloud LLM inference (any OpenAI-compatible model)
- **[MLX-LM](https://github.com/ml-explore/mlx-lm)** — Local LLM inference on Apple Silicon
- **[Jinja2](https://jinja.palletsprojects.com)** — Prompt templating
- **[Pygame](https://pygame.org)** — AI thoughts display window

## Reproducing the paper

Each model in the paper was evaluated with the same invocation, varying only the `--model` preset:

```bash
python main.py --ai --model qwen3.5-27b --thinking --mute
```

A run terminates when one of three conditions is met:

1. **Completion** — the agent reaches the S.S. Anne.
2. **Retry exhaustion** — an agent cannot produce a valid action after its maximum retries, requiring human intervention.
3. **Unrecoverable loop** — the agent fills its entire action history with repeated actions and no progress.

Per-model results, including checkpoint times and decision metrics, are in [paper/](paper/) (one `*_results.md` file per run).

## License

Released under the Apache 2.0 License — see [LICENSE](LICENSE).
