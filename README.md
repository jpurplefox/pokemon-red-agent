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

## How it works

The agent reads Pokemon Red's WRAM (working RAM) to extract game state: map position, nearby points of interest, party HP, battle stats, inventory. This state is rendered into text prompts via Jinja2 templates and sent to an LLM — either a cloud model via the OpenRouter API or a local model running on Apple Silicon via MLX. The LLM responds with a structured action (`GO:3`, `MOVE:TACKLE`, `BUY: 1 x3`), which is parsed and translated into button presses on the emulator.

```
Game Boy (PyBoy)  -->  State Readers  -->  Domain Objects  -->  LLM Agent  -->  Menu Driver  -->  Game Boy
     WRAM               (adapters)        (dataclasses)      (reasoning)      (adapters)       button presses
```

## Architecture

Hexagonal architecture with clear port/adapter boundaries:

```
pokemon-red/
├── domain/              # Models + Protocol definitions (ports)
│   └── models.py        #   PartyMember, BattleMon, Move, LLMPort, GameStatePort, etc.
│
├── agents/              # AI decision-makers (use LLMPort)
│   ├── battle_ai.py     #   Combat strategy via LLM
│   ├── overworld_ai.py  #   Exploration decisions + sub-goal tracking
│   ├── shop_ai.py       #   Purchase optimization
│   ├── scout_ai.py      #   Catch-or-defeat evaluation
│   ├── naming_ai.py     #   Pokemon nickname generation
│   └── templates/       #   Jinja2 prompt templates
│
├── adapters/
│   ├── state/           # Read game state from WRAM (driven adapters)
│   │   ├── battle_state_reader.py
│   │   ├── bag_reader.py
│   │   ├── overworld.py
│   │   ├── screen.py
│   │   └── menu.py
│   ├── input/           # Execute actions via button presses (driven adapters)
│   │   ├── battle_menu_driver.py
│   │   ├── navigator.py     # A* pathfinding + walking
│   │   ├── pathfinder.py
│   │   └── naming.py
│   └── display/         # Output to user (driven adapters)
│       ├── ai_logger.py     # Unified colored console output
│       ├── ai_log_window.py # Pygame window showing AI thoughts
│       └── console.py       # ASCII map rendering, prompts
│
├── orchestration/       # Game flow control
│   ├── game.py              # Main game loop + state dispatch
│   ├── battle.py            # Battle turn sequencing
│   ├── overworld_controller.py  # Overworld AI coordinator
│   └── event_processor.py   # Dialogue, menus, mart interaction
│
├── data/                # Static data + constants
│   ├── constants.py         # WRAM addresses, map names, items
│   └── pokemon_data.py      # Types, moves, species data
│
├── tools/                  # Dev utilities (memory inspector)
├── main.py                 # Entry point + dependency wiring
└── pyproject.toml
```

## Ports (interfaces)

Defined as Python Protocols in `domain/models.py`:

| Port | Purpose | Adapter |
|------|---------|---------|
| `LLMPort` | Send prompts, get responses | `OpenAILLM` (cloud via OpenRouter) or `MLXLLM` (local on Apple Silicon) |
| `GameStatePort` | Read battle/party state | `BattleStateReader` |
| `GameInputPort` | Press buttons in menus | `BattleMenuDriver` |
| `BagPort` | Read inventory and money | `BagReader` |
| `DisplayPort` | Show AI reasoning | `AILogger` + pygame window |
| `BattleStrategy` | Choose battle actions | `BattleAI` or `ManualStrategy` |

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

# Shop AI only (you explore, AI buys at marts)
python main.py --shop

# Naming AI only (you play, AI names caught Pokemon)
python main.py --naming
```

Available cloud model presets: `qwen3.5-27b`, `qwen3-30b`, `qwen3-235b`, `gemini-flash`, `deepseek-v3`, `llama4-maverick`. Pass any other OpenRouter model ID directly. See `main.py` for the full list of local MLX presets.

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

## AI Features

### Overworld Agent
- ASCII map with spatial awareness (`@` = player, `#` = wall, numbers = POIs)
- Sub-goal system: detects side-quests from NPC dialogue, prioritizes them
- Visit tracking: avoids repeating actions
- Auto-heals at Pokemon Centers when HP is low
- Auto-buys Poke Balls when stock is low
- Goal detection: returns control to user when objective is reached

### Battle Agent
- Type advantage reasoning with STAB awareness
- Turn history tracking for context
- Retry with error feedback on parse failures
- LLM-based Pokemon switching after faints
- Post-battle reflection for learning

### Shop Agent
- Evaluates inventory needs vs budget
- Keeps money reserves (30% rule)
- Prioritizes Poke Balls

## Tech Stack

- **[PyBoy](https://github.com/Baekalfen/PyBoy)** — Game Boy emulator with Python API
- **[OpenRouter](https://openrouter.ai)** — Cloud LLM inference (any OpenAI-compatible model)
- **[MLX-LM](https://github.com/ml-explore/mlx-lm)** — Local LLM inference on Apple Silicon
- **[Jinja2](https://jinja.palletsprojects.com)** — Prompt templating
- **[Pygame](https://pygame.org)** — AI thoughts display window
