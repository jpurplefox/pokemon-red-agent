# Qwen 3.5 35B-A3B - Run Results

## Overview
- **Model:** Qwen 3.5 35B-A3B (MoE, 3B active parameters)
- **Inference:** Cloud via OpenRouter (thinking/reasoning enabled)
- **Outcome:** Failed — unable to progress past early game

## Metrics
- **OW (Overworld):** 27x (15 retries), 1446s total, 53.5s avg — 5 warps, 10 interactions

**Unparseable responses:** Overworld 15

## Notable Observations
- Similar failure pattern to Qwen 3.5 9B — too few active parameters (3B) for the task despite 35B total
- High retry rate (15 out of 27 decisions) indicates the model cannot reliably produce parseable output
