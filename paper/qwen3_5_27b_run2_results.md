# Qwen 3.5 27B (Run 2) - Run Results

## Overview
- **Model:** Qwen 3.5 27B
- **Inference:** Cloud via OpenRouter (thinking/reasoning enabled)
- **Total runtime:** 40 hours 48 minutes
- **Outcome:** Defeated Misty (Badge 2) at 31h 21m, did not complete Bill quest

## Metrics
- **NAME:** 10x (2 retries), 3043s total, 304.3s avg
- **MOVE:** 2x, 41s total, 20.4s avg — 1 skipped, 1 learned
- **BATTLE:** 1053x (62 retries), 33999s total, 32.3s avg — 789 attacks, 500 wins, 5 losses, 17 ball throws, 9 catches, 175 switches, 1 run
- **BATTLE-REFLECT:** 515x, 21521s total, 41.8s avg — 15 facts learned (1 incorrect)
- **SCOUT:** 461x, 12854s total, 27.9s avg — 17 catches
- **OW (Overworld):** 1078x (4 retries), 10334s total, 9.6s avg — 437 warps, 270 interactions, 367 grass encounters
- **LEAD:** 507x (2 retries), 12330s total, 24.3s avg — 14 swaps
- **SHOP:** 13x, 763s total, 58.7s avg — 11 buys

**Unparseable responses:** Battle 62, Name 2, Overworld 4, Lead 2

## Final Team
| Pokemon    | Nickname | Level |
|------------|----------|-------|
| CHARIZARD  | EMBER    | 36    |
| GEODUDE    | BEDROCK  | 12    |
| PIDGEY     | HAWKEYE  | 12    |
| WEEDLE     | STINGER  | 5     |
| PIKACHU    | THUNDER  | 4     |
| RATTATA    | NICKNAME | 3     |

## Checkpoint Times

| # | Checkpoint | Wall-clock | Party |
|---|-----------|------------|-------|
| 1 | Obtain starter | 1h 34m | Lv5 EMBER (Charmander) |
| 2 | Deliver Oak's Parcel | 2h 08m | Lv8 EMBER (Charmander) |
| 3 | Reach Viridian Forest | 3h 31m | Lv10 EMBER (Charmander), Lv4 HAWKEYE (Pidgey), Lv3 NICKNAME (Rattata), Lv5 STINGER (Weedle) |
| 4 | Defeat Brock (Badge 1) | 7h 51m | Lv17 EMBER (Charmeleon), Lv9 HAWKEYE (Pidgey), Lv5 STINGER (Weedle), Lv3 NICKNAME (Rattata) |
| 5 | Reach Mt. Moon | 10h 04m | Lv21 EMBER (Charmeleon), Lv10 HAWKEYE (Pidgey), Lv5 STINGER (Weedle), Lv3 NICKNAME (Rattata), Lv3 THUNDER (Pikachu) |
| 6 | Reach Cerulean City | 31h 06m | Lv30 EMBER (Charmeleon), Lv10 BEDROCK (Geodude), Lv10 HAWKEYE (Pidgey), Lv5 STINGER (Weedle), Lv4 THUNDER (Pikachu), Lv3 NICKNAME (Rattata) |
| 7 | Defeat Misty (Badge 2) | 31h 21m | Lv31 EMBER (Charmeleon), Lv10 BEDROCK (Geodude), Lv10 HAWKEYE (Pidgey), Lv5 STINGER (Weedle), Lv4 THUNDER (Pikachu), Lv3 NICKNAME (Rattata) |

Run terminated at 40h 48m without completing Bill's quest.

## Notable Observations
- **Extreme starter over-leveling:** At the time of defeating Misty, Charmeleon was Lv31 while the next highest team member was only Lv10 — a 21-level gap, by far the most extreme of any run. The final Charizard reached Lv36 while most of the party remained at Lv3-12.
- **PP exhaustion trap:** The over-leveled starter was so strong it could battle indefinitely without taking damage, so the model never switched or healed. This caused Ember and Scratch PP to be fully depleted, leaving the starter with no usable moves. When this happened the model did not know how to recover, producing two pathological battles:
  - Wild Zubat: 2.5 hours, ended by running away
  - Wild Geodude: 2 hours, ended in loss
- Brock at 7h 51m — slower than Run 1 (5h 02m), likely due to choosing Charmander (type disadvantage) instead of Bulbasaur
- Mt. Moon bottleneck: 21 hours (10h 04m to 31h 06m) — the longest Mt. Moon time of any run
