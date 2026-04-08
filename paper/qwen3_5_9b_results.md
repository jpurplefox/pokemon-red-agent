# Qwen 3.5 9B - Run Results

## Overview
- **Model:** Qwen 3.5 9B (thinking/reasoning enabled)
- **Inference:** Cloud via OpenRouter
- **Outcome:** Failed — agent could not progress past the very start of the game
- **Termination reason:** 3 consecutive unparseable responses after 6 overworld decisions

## Metrics
- **OW (Overworld):** 6x, 196s total, 32.7s avg — 3 warps, 3 interactions
- **Unparseable responses:** 3 (terminal)

## Notable Observations
- Model too small for the task — unable to produce consistently parseable output even in early game
- Thinking/reasoning mode did not compensate for the lack of capacity
