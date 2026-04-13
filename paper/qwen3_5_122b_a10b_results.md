# Qwen 3.5 122B-A10B - Run Results

## Overview
- **Model:** Qwen 3.5 122B-A10B (MoE, 10B active parameters)
- **Inference:** Cloud via OpenRouter (thinking/reasoning enabled)
- **Total runtime:** 41 hours
- **Outcome:** Defeated Misty (Cerulean Gym), did not complete Bill quest

## Metrics
- **NAME:** 13x, 2220s total, 170.8s avg
- **MOVE:** 1x, 21s total, 20.6s avg — 1 skipped
- **BATTLE:** 927x (1 retry), 36469s total, 39.3s avg — 646 attacks, 186 wins, 11 losses, 23 ball throws, 12 catches, 140 switches
- **BATTLE-REFLECT:** 210x, 7351s total, 35.0s avg — 20 facts learned (4 incorrect)
- **SCOUT:** 145x, 2511s total, 17.3s avg — 18 catches
- **OW (Overworld):** 814x, 45915s total, 56.4s avg — 404 warps, 346 interactions, 64 grass encounters
- **LEAD:** 202x, 6958s total, 34.4s avg — 39 swaps
- **SHOP:** 17x, 1280s total, 75.3s avg — 14 buys

**Unparseable responses:** Battle 1

## Checkpoint Times

| # | Checkpoint | Wall-clock | Party |
|---|-----------|------------|-------|
| 1 | Obtain starter | 0h 31m | Lv5 REDTAIL (Charmander) |
| 2 | Deliver Oak's Parcel | 1h 30m | Lv8 REDTAIL (Charmander) |
| 3 | Reach Viridian Forest | 2h 54m | Lv3 RATITUDE (Rattata), Lv9 REDTAIL (Charmander), Lv3 KINGPIN (Nidoran♂), Lv3 WINGMAN (Pidgey) |
| 4 | Defeat Brock (Badge 1) | 6h 36m | Lv8 WINGMAN (Pidgey), Lv15 REDTAIL (Charmander), Lv5 KINGPIN (Nidoran♂), Lv3 RATITUDE (Rattata), Lv4 VOLTAGE (Pikachu), Lv5 BUZZSAW (Kakuna) |
| 5 | Reach Mt. Moon | 10h 05m | Lv3 RATITUDE (Rattata), Lv18 REDTAIL (Charmeleon), Lv5 KINGPIN (Nidoran♂), Lv9 BUZZSAW (Kakuna), Lv4 VOLTAGE (Pikachu), Lv8 WINGMAN (Pidgey) |
| 6 | Reach Cerulean City | 21h 52m | Lv9 VOLTAGE (Pikachu), Lv22 REDTAIL (Charmeleon), Lv10 KINGPIN (Nidoran♂), Lv12 BUZZSAW (Beedrill), Lv11 WINGMAN (Pidgey), Lv8 RATITUDE (Rattata) |
| 7 | Defeat Misty (Badge 2) | 31h 37m | Lv13 VOLTAGE (Pikachu), Lv27 REDTAIL (Charmeleon), Lv12 KINGPIN (Nidoran♂), Lv14 BUZZSAW (Beedrill), Lv16 WINGMAN (Pidgey), Lv12 RATITUDE (Rattata) |

Run terminated at 41h — did not complete Bill quest.

## Final Team
| Pokemon     | Nickname   | Level |
|-------------|------------|-------|
| CHARMELEON  | REDTAIL    | 28    |
| PIKACHU     | VOLTAGE    | 14    |
| RATTATA     | RATITUDE   | 12    |
| BEEDRILL    | BUZZSAW    | 14    |
| PIDGEY      | WINGMAN    | 16    |
| NIDORAN♂    | KINGPIN    | 14    |

## Notable Observations
- Very slow OW decisions (56.4s avg) — the slowest of all models tested, likely due to MoE overhead on reasoning
- Almost no unparseable responses (only 1 battle retry) — best parse reliability of all models
- High interaction count (346) vs low grass encounters (64) — this model explores interiors much more than Qwen 3.5 27B
- Did not complete Bill quest despite 41h runtime
