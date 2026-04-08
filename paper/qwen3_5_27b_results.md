# Qwen 3.5 27B - Run Results

## Overview
- **Model:** Qwen 3.5 27B
- **Inference:** Cloud via OpenRouter (thinking/reasoning enabled)
- **Total runtime:** 30 hours
- **Outcome:** Defeated Misty (Cerulean Gym), did not complete Bill quest

## Metrics
- **NAME:** 6x, 1987s total, 331.1s avg
- **MOVE:** 2x, 80s total, 39.9s avg — 2 learned
- **BATTLE:** 1167x (28 retries), 28660s total, 24.6s avg — 976 attacks, 413 wins, 2 losses, 10 ball throws, 5 catches, 124 switches
- **BATTLE-REFLECT:** 420x, 13556s total, 32.3s avg — 23 facts learned (3 incorrect)
- **SCOUT:** 370x, 8455s total, 22.9s avg — 16 catches
- **OW (Overworld):** 790x (1 retry), 6585s total, 8.3s avg — 331 warps, 202 interactions, 256 grass encounters
- **LEAD:** 410x (3 retries), 8504s total, 20.7s avg — 30 swaps
- **SHOP:** 3x, 92s total, 30.6s avg — 3 buys

**Unparseable responses:** Battle 28, Lead 3, Overworld 1

## Final Team
| Pokemon     | Nickname    | Level |
|-------------|-------------|-------|
| IVYSAUR     | CHLOROPHYL  | 30    |
| PIKACHU     | VOLTAGE     | 5     |
| RATTATA     | NIBBLER     | 19    |
| GEODUDE     | STONEHENGE  | 14    |
| BUTTERFREE  | METAMORPH   | 12    |
| SPEAROW     | SPEARHEAD   | 18    |

## Checkpoint Times

| # | Checkpoint | Wall-clock | Party |
|---|-----------|------------|-------|
| 1 | Obtain starter | 0h 14m | Lv5 CHLOROPHYL (Bulbasaur) |
| 2 | Deliver Oak's Parcel | 1h 03m | Lv7 CHLOROPHYL (Bulbasaur) |
| 3 | Reach Viridian Forest | 2h 26m | Lv4 NIBBLER (Rattata), Lv3 SPEARHEAD (Spearow), Lv9 CHLOROPHYL (Bulbasaur) |
| 4 | Defeat Brock (Badge 1) | 5h 02m | Lv5 SPEARHEAD (Spearow), Lv13 CHLOROPHYL (Bulbasaur), Lv9 NIBBLER (Rattata), Lv3 METAMORPH (Caterpie) |
| 5 | Reach Mt. Moon | 6h 51m | Lv6 METAMORPH (Caterpie), Lv11 SPEARHEAD (Spearow), Lv10 NIBBLER (Rattata), Lv14 CHLOROPHYL (Bulbasaur) |
| 6 | Reach Cerulean City | 22h 26m | Lv16 SPEARHEAD (Spearow), Lv11 STONEHENGE (Geodude), Lv11 METAMORPH (Butterfree), Lv16 NIBBLER (Rattata), Lv4 VOLTAGE (Pikachu), Lv24 CHLOROPHYL (Ivysaur) |
| 7 | Defeat Misty (Badge 2) | 22h 46m | Lv17 NIBBLER (Rattata), Lv11 STONEHENGE (Geodude), Lv11 METAMORPH (Butterfree), Lv17 SPEARHEAD (Spearow), Lv4 VOLTAGE (Pikachu), Lv25 CHLOROPHYL (Ivysaur) |

Run terminated at 30h — did not complete Bill quest.

## Notable Observations
- **Mt. Moon bottleneck (15.5h):** From reaching Mt. Moon (6h51m) to exiting at Cerulean City (22h26m) took over 15 hours — the multi-floor cave navigation remains a major obstacle.
- **Bill quest not completed:** The agent never entered Bill's house. In general, the model rarely explores building interiors — very few warps into houses throughout the run.
- **Brock much faster than 3.6 Plus:** Defeated Brock in 5h vs 18h, likely because Bulbasaur reached Vine Whip level faster with less wasted time.
