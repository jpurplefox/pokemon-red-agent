# Qwen 3.5 397B-A17B - Run Results

## Overview
- **Model:** Qwen 3.5 397B-A17B (MoE, 17B active parameters)
- **Inference:** Cloud via OpenRouter (thinking/reasoning enabled)
- **Total runtime:** 33 hours 40 minutes
- **Outcome:** Defeated Misty (Cerulean Gym), completed Bill quest (S.S. Ticket obtained)
- **Blocker:** Unable to exit Cerulean City toward Route 5 (same building interior pattern)

## Metrics
- **NAME:** 7x, 1061s total, 151.5s avg
- **MOVE:** 1x, 16s total, 15.9s avg — 1 skipped
- **BATTLE:** 767x (38 retries), 29621s total, 38.6s avg — 564 attacks, 180 wins, 7 losses, 9 ball throws, 6 catches, 110 switches
- **BATTLE-REFLECT:** 193x, 8379s total, 43.4s avg — 25 facts learned (1 incorrect, 4 duplicates)
- **SCOUT:** 138x, 2806s total, 20.3s avg — 12 catches
- **OW (Overworld):** 597x (41 retries), 39557s total, 66.3s avg — 220 warps, 260 interactions, 76 grass encounters
- **LEAD:** 189x (6 retries), 7366s total, 39.0s avg — 31 swaps
- **SHOP:** 7x, 427s total, 61.0s avg — 6 buys

**Unparseable responses:** Battle 38, Overworld 41, Lead 6

## Final Team
| Pokemon     | Nickname  | Level |
|-------------|-----------|-------|
| CHARMELEON  | IGNIS     | 29    |
| PIDGEY      | VENTUS    | 16    |
| ODDISH      | FLOREUS   | 15    |
| GEODUDE     | SAXUM     | 13    |
| BEEDRILL    | CULEUS    | 13    |
| RATTATA     | WILLARD   | 12    |

## Checkpoint Times

| # | Checkpoint | Wall-clock | Party |
|---|-----------|------------|-------|
| 1 | Obtain starter | 0h 41m | Lv5 IGNIS (Charmander) |
| 2 | Deliver Oak's Parcel | 1h 19m | Lv7 IGNIS (Charmander) |
| 3 | Reach Viridian Forest | 1h 42m | Lv7 IGNIS (Charmander), Lv3 CULEUS (Weedle) |
| 4 | Defeat Brock (Badge 1) | 7h 33m | Lv14 IGNIS (Charmander), Lv9 VENTUS (Pidgey), Lv5 CULEUS (Weedle), Lv4 WILLARD (Rattata) |
| 5 | Reach Mt. Moon | 8h 54m | Lv17 IGNIS (Charmeleon), Lv11 VENTUS (Pidgey), Lv7 CULEUS (Kakuna), Lv6 WILLARD (Rattata) |
| 6 | Reach Cerulean City | 18h 43m | Lv24 IGNIS (Charmeleon), Lv13 VENTUS (Pidgey), Lv11 SAXUM (Geodude), Lv9 CULEUS (Kakuna), Lv9 WILLARD (Rattata) |
| 7 | Defeat Misty (Badge 2) | 28h 33m | Lv29 IGNIS (Charmeleon), Lv16 VENTUS (Pidgey), Lv15 FLOREUS (Oddish), Lv13 CULEUS (Beedrill), Lv13 SAXUM (Geodude), Lv12 WILLARD (Rattata) |
| 8 | Help Bill | 30h 23m | Lv29 IGNIS (Charmeleon), Lv16 VENTUS (Pidgey), Lv15 FLOREUS (Oddish), Lv13 CULEUS (Beedrill), Lv13 SAXUM (Geodude), Lv12 WILLARD (Rattata) |

Run terminated at 33h 40m without further progress.

## Notable Observations
- Same outcome as Qwen 3.6 Plus (Badge 2 + Bill), same blocker (Cerulean exit)
- Slowest OW decisions of all models (66.3s avg) and highest OW unparseable rate (41 retries)
- Also chose Charmander like 122B-A10B, with same starter over-leveling pattern (Lv29 vs next highest Lv16)
- Explored building interiors more than other models and entered the house containing the Route 5 exit, but did not walk through to the other side
- First model to produce duplicate facts in battle reflect (4 duplicates out of 25)
