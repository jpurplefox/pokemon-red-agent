# Qwen 3.5 27B (Run 3) - Run Results

## Overview
- **Model:** Qwen 3.5 27B
- **Inference:** Cloud via OpenRouter (thinking/reasoning enabled)
- **Total runtime:** 33 hours 37 minutes
- **Outcome:** Defeated Misty (Badge 2) at 26h 58m, did not complete Bill quest

## Metrics
- **NAME:** 8x (2 retries), 3186s total, 398.2s avg
- **MOVE:** 2x, 69s total, 34.5s avg — 2 learned
- **BATTLE:** 1209x (22 retries), 34149s total, 28.2s avg — 956 attacks, 405 wins, 6 losses, 10 ball throws, 6 catches, 176 switches
- **BATTLE-REFLECT:** 418x, 18793s total, 45.0s avg — 24 facts learned (6 incorrect)
- **SCOUT:** 363x, 8122s total, 22.4s avg — 11 catches
- **OW (Overworld):** 800x (3 retries), 6459s total, 8.1s avg — 322 warps, 207 interactions, 268 grass encounters
- **LEAD:** 407x, 10491s total, 25.8s avg — 27 swaps
- **SHOP:** 8x, 1405s total, 175.6s avg — 7 buys

**Unparseable responses:** Battle 22, Name 2, Overworld 3

## Final Team
| Pokemon     | Nickname   | Level |
|-------------|------------|-------|
| IVYSAUR     | NICKNAME   | 29    |
| GEODUDE     | FLINT      | 22    |
| BUTTERFREE  | METAMORPH  | 16    |
| PIDGEY      | SKYHAWK    | 12    |
| RATTATA     | RATZILLA   | 12    |
| MAGIKARP    | LEVIATHAN  | 6     |

## Checkpoint Times

| # | Checkpoint | Wall-clock | Party |
|---|-----------|------------|-------|
| 1 | Obtain starter | 0h 45m | Lv5 NICKNAME (Bulbasaur) |
| 2 | Deliver Oak's Parcel | 1h 13m | Lv8 NICKNAME (Bulbasaur) |
| 3 | Reach Viridian Forest | 2h 22m | Lv9 NICKNAME (Bulbasaur), Lv3 SKYHAWK (Pidgey), Lv4 RATZILLA (Rattata) |
| 4 | Defeat Brock (Badge 1) | 5h 33m | Lv14 NICKNAME (Bulbasaur), Lv7 SKYHAWK (Pidgey), Lv5 RATZILLA (Rattata) |
| 5 | Reach Mt. Moon | 7h 07m | Lv18 NICKNAME (Ivysaur), Lv9 SKYHAWK (Pidgey), Lv5 RATZILLA (Rattata) |
| 6 | Reach Cerulean City | 26h 32m | Lv24 NICKNAME (Ivysaur), Lv19 FLINT (Geodude), Lv15 METAMORPH (Butterfree), Lv11 RATZILLA (Rattata), Lv11 SKYHAWK (Pidgey), Lv5 LEVIATHAN (Magikarp) |
| 7 | Defeat Misty (Badge 2) | 26h 58m | Lv25 NICKNAME (Ivysaur), Lv20 FLINT (Geodude), Lv15 METAMORPH (Butterfree), Lv11 RATZILLA (Rattata), Lv11 SKYHAWK (Pidgey), Lv5 LEVIATHAN (Magikarp) |

Run terminated at 33h 37m without completing Bill's quest.

## Notable Observations
- **Strategic use of starter type advantage:** The agent chose Bulbasaur and deliberately trained until it learned Vine Whip before challenging Brock, showing awareness of the move's importance.
- **Smoother Misty battle:** Unlike the Charmander runs, the Misty fight was straightforward with no difficulty, thanks to the Grass-type Ivysaur's advantage against Water-type.
- **More balanced team training:** The level spread was much narrower than Run 2 — at the time of defeating Misty, the top-bottom gap was 20 levels (Lv25 Ivysaur to Lv5 Magikarp), but excluding the newly-caught Magikarp the gap drops to 14, compared to Run 2's 28-level gap.
- **Mt. Moon took longer than Run 1:** ~19 hours (7h 07m to 26h 32m) vs Run 1's 15 hours, but the maze was completed successfully.
