# Qwen 3.6 Plus - Run Results

## Overview
- **Model:** Qwen 3.6 Plus
- **Total runtime:** 37 hours continuous
- **Outcome:** Defeated Misty (Cerulean Gym), completed Bill quest (S.S. Ticket obtained)
- **Blocker:** Agent unable to exit Cerulean City toward Route 5 (requires passing through a building interior — non-obvious navigation the model cannot infer)
- **Inference:** Cloud via OpenRouter (thinking/reasoning enabled)

## Final Team
| Pokemon    | Nickname   | Level |
|------------|------------|-------|
| PIDGEOTTO  | ZEPHYR     | 23    |
| PIKACHU    | RAIJIN     | 23    |
| GEODUDE    | TECTONIC   | 19    |
| BEEDRILL   | TWINSTING  | 17    |
| IVYSAUR    | CHLORIS    | 19    |

## Metrics
- **NAME:** 5x, 528s total, 105.7s avg
- **BATTLE:** 1553x (6 retries), 42412s total, 27.3s avg — 1130 attacks, 351 wins, 15 losses, 8 ball throws, 4 catches, 318 switches, 4 runs
- **BATTLE-REFLECT:** 374x, 11971s total, 32.0s avg — 30 facts learned (5 incorrect)
- **SCOUT:** 305x, 5383s total, 17.6s avg — 4 catches
- **OW (Overworld):** 894x (3 retries), 17204s total, 19.2s avg — 444 warps, 247 interactions, 200 grass encounters
- **LEAD:** 365x, 7808s total, 21.4s avg — 34 swaps
- **SHOP:** 10x, 366s total, 36.6s avg — 10 buys

**Unparseable responses:** Battle 6, Overworld 3

## Checkpoint Times

| # | Checkpoint | Wall-clock | Party |
|---|-----------|------------|-------|
| 1 | Obtain starter | 0h 15m | Lv5 CHLORIS (Bulbasaur) |
| 2 | Deliver Oak's Parcel | 0h 28m | Lv5 CHLORIS (Bulbasaur) |
| 3 | Reach Viridian Forest | 0h 50m | Lv6 CHLORIS (Bulbasaur), Lv4 ZEPHYR (Pidgey) |
| 4 | Defeat Brock (Badge 1) | 17h 57m | Lv13 ZEPHYR (Pidgey), Lv14 CHLORIS (Bulbasaur), Lv16 RAIJIN (Pikachu), Lv7 TWINSTING (Kakuna) |
| 5 | Reach Mt. Moon | 18h 56m | Lv8 TWINSTING (Kakuna), Lv15 ZEPHYR (Pidgey), Lv14 CHLORIS (Bulbasaur), Lv17 RAIJIN (Pikachu) |
| 6 | Reach Cerulean City | 28h 34m | Lv15 TWINSTING (Beedrill), Lv18 ZEPHYR (Pidgeotto), Lv17 CHLORIS (Ivysaur), Lv20 RAIJIN (Pikachu), Lv16 TECTONIC (Geodude) |
| 7 | Defeat Misty (Badge 2) | 28h 53m | Lv16 TWINSTING (Beedrill), Lv18 ZEPHYR (Pidgeotto), Lv17 CHLORIS (Ivysaur), Lv20 RAIJIN (Pikachu), Lv16 TECTONIC (Geodude) |
| 8 | Help Bill | 34h 22m | Lv22 ZEPHYR (Pidgeotto), Lv23 RAIJIN (Pikachu), Lv19 TECTONIC (Geodude), Lv17 TWINSTING (Beedrill), Lv19 CHLORIS (Ivysaur) |

Run terminated at 37h due to no further progress.

## Notable Observations
- **Brock bottleneck (17h):** Despite having Bulbasaur (type advantage vs Rock), it doesn't learn Vine Whip until Lv13. The agent's strategy was to grind and retry Brock repeatedly, but without an effective move the team couldn't damage him. This accounted for most of the first 18 hours.
- **Cerulean exit blocker:** Agent got stuck exiting Cerulean City — the path to Route 5 requires entering a building and exiting through the other side, a navigation pattern the model cannot deduce without explicit guidance.
- **Run termination:** Execution cut at 37h after 2h 38m without progress past Bill's quest.
