"""TypeSafe overworld experiment — can Jev pick the next overworld action?

Compares three ways of using System One for OverworldAI.decide() on
hand-built scenarios with a known "sensible" answer:

  direct    One Choice over every available action (INTERACT:n / GO:n).
  reversed  Same Choice with options in reverse order (Jev has a known
            first-option bias; if the answer flips, it is not robust).
  composite Per-action Nouls ("advances the goal?") combined in code with
            deterministic rules (novelty, low HP -> heal).

All questions go in ONE request per scenario (they run in parallel).

Setup:
    venv/bin/pip install typesafe-sdk
    export TYPESAFE_API_KEY=...        # or put it in .env

Run:
    venv/bin/python -m tools.typesafe_overworld_demo
"""

import time

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, TypeSafeClient

load_dotenv()

GOAL = "Become Pokemon Champion"

# Each scenario mirrors what OverworldAI.decide() receives.
# `expected` lists the action ids a reasonable player would pick.
SCENARIOS = [
    {
        "name": "Deliver Oak's Parcel (multi-hop: Pallet is south via Route 1)",
        "map": "VIRIDIAN CITY",
        "subgoal": "Deliver Oak's Parcel to Professor Oak in Pallet Town",
        "party": [{"name": "CHARMANDER", "level": 7, "hp": 22, "max_hp": 24}],
        "badges": 0,
        "history": [
            {"map": "VIRIDIAN POKEMART", "action": "INTERACT Clerk",
             "result": "\"Okay! Say hi to PROF. OAK for me!\" Received OAK's PARCEL"},
            {"map": "VIRIDIAN POKEMART", "action": "GO Exit", "result": "Entered VIRIDIAN CITY"},
        ],
        "interactables": [
            {"label": "Youngster", "dist": 4, "visited": 0},
            {"label": "Old Man (lying on road)", "dist": 9, "visited": 1},
        ],
        "warps": [
            {"label": "Viridian Pokemart", "dist": 2},
            {"label": "Pokemon Center", "dist": 6},
            {"label": "ROUTE 1 (south)", "dist": 12},
            {"label": "ROUTE 2 (north)", "dist": 14},
            {"label": "ROUTE 22 (west)", "dist": 10},
        ],
        "expected": {"go_3"},
    },
    {
        "name": "Team almost fainted on Route 1",
        "map": "ROUTE 1",
        "subgoal": None,
        "party": [{"name": "SQUIRTLE", "level": 6, "hp": 3, "max_hp": 22}],
        "badges": 0,
        "history": [
            {"map": "ROUTE 1", "action": "INTERACT Wild Pokémon (tall grass)",
             "result": "Defeated wild RATTATA, SQUIRTLE took heavy damage"},
        ],
        "interactables": [
            {"label": "Wild Pokémon (tall grass)", "dist": 1, "visited": 2},
            {"label": "Youngster", "dist": 5, "visited": 0},
        ],
        "warps": [
            {"label": "PALLET TOWN (south)", "dist": 8},
            {"label": "VIRIDIAN CITY (north, has Pokemon Center)", "dist": 15},
        ],
        "expected": {"go_2"},
    },
    {
        "name": "Pewter City, ready for the first gym",
        "map": "PEWTER CITY",
        "subgoal": None,
        "party": [
            {"name": "BULBASAUR", "level": 14, "hp": 40, "max_hp": 40},
            {"name": "PIDGEY", "level": 10, "hp": 29, "max_hp": 29},
        ],
        "badges": 0,
        "history": [
            {"map": "PEWTER CITY", "action": "INTERACT Pokemon Center Nurse", "result": "Team healed"},
            {"map": "PEWTER CITY", "action": "INTERACT Sign", "result": "\"PEWTER CITY GYM LEADER: BROCK\""},
        ],
        "interactables": [
            {"label": "Sign", "dist": 1, "visited": 1},
            {"label": "Lass", "dist": 7, "visited": 0},
        ],
        "warps": [
            {"label": "Pokemon Center", "dist": 3},
            {"label": "Pewter Museum", "dist": 11},
            {"label": "Pewter Gym", "dist": 6},
            {"label": "ROUTE 2 (south)", "dist": 16},
        ],
        "expected": {"go_3"},
    },
    {
        "name": "Stuck in a loop: only one unexplored thing left",
        "map": "PALLET TOWN",
        "subgoal": None,
        "party": [{"name": "CHARMANDER", "level": 5, "hp": 20, "max_hp": 20}],
        "badges": 0,
        "history": [
            {"map": "PALLET TOWN", "action": "INTERACT Girl", "result": "\"I'm raising POKéMON too!\""},
            {"map": "PALLET TOWN", "action": "INTERACT Girl", "result": "\"I'm raising POKéMON too!\""},
            {"map": "PALLET TOWN", "action": "INTERACT Girl", "result": "\"I'm raising POKéMON too!\""},
        ],
        "interactables": [
            {"label": "Girl", "dist": 2, "visited": 3},
            {"label": "Fat Man", "dist": 5, "visited": 1},
        ],
        "warps": [
            {"label": "Player's House", "dist": 4},
            {"label": "Oak's Lab", "dist": 7},
            {"label": "ROUTE 1 (north)", "dist": 9},
        ],
        "expected": {"go_3"},
    },
]


def _actions(sc):
    """Flatten POIs into (action_id, description dict), same numbering as the prompt."""
    acts = []
    for i, p in enumerate(sc["interactables"], 1):
        acts.append((f"interact_{i}", {
            "action": "Walk to and interact with (talk / read / battle)",
            "target": p["label"], "distance_steps": p["dist"],
            "times_interacted_recently": p["visited"],
        }))
    for i, w in enumerate(sc["warps"], 1):
        acts.append((f"go_{i}", {
            "action": "Walk to and enter this warp/exit, leaving the current map",
            "target": w["label"], "distance_steps": w["dist"],
        }))
    return acts


def _state(sc):
    return {
        "main_goal": GOAL,
        "active_subgoal": sc["subgoal"] or "none",
        "current_map": sc["map"],
        "badges": f"{sc['badges']}/8",
        "team": [f"{m['name']} Lv{m['level']} {m['hp']}/{m['max_hp']} HP" for m in sc["party"]],
        "recent_history": sc["history"],
    }


def _questions(acts):
    instr = ("You are playing Pokemon Red. Which single action should the "
             "player take next to make progress on the active sub-goal "
             "(or the main goal if there is none)?")
    qs = {
        "direct": Choice(instructions=instr, criteria=dict(acts)),
        "reversed": Choice(instructions=instr, criteria=dict(reversed(acts))),
    }
    for aid, desc in acts:
        qs[f"adv:{aid}"] = Noul(instructions=(
            f"Taking this action next moves the player closer to completing the "
            f"active sub-goal (or the main goal if there is none): {desc}"))
    return qs


def _composite(sc, acts, answers):
    """Code owns the rules; Jev only judges 'does this advance the goal'."""
    low_hp = any(m["hp"] / m["max_hp"] < 0.25 for m in sc["party"])
    scores = {}
    for aid, desc in acts:
        s = answers[f"adv:{aid}"].noul
        visited = desc.get("times_interacted_recently", 0)
        if visited >= 3:
            s -= 1.0                      # same rule as the 🚫 in the prompt
        elif visited > 0:
            s -= 0.3
        if low_hp and "pokemon center" in desc["target"].lower():
            s += 1.0                      # deterministic: heal when critical
        if low_hp and "grass" in desc["target"].lower():
            s -= 1.0
        scores[aid] = s
    return max(scores, key=scores.get), scores


def main():
    client = TypeSafeClient()
    hits = {"direct": 0, "reversed": 0, "composite": 0}

    for sc in SCENARIOS:
        acts = _actions(sc)
        labels = {aid: d["target"] for aid, d in acts}

        t0 = time.perf_counter()
        resp = client.system_one(state=_state(sc), questions=_questions(acts))
        ms = (time.perf_counter() - t0) * 1000
        a = resp.answers

        comp_pick, comp_scores = _composite(sc, acts, a)
        picks = {"direct": a["direct"].choice, "reversed": a["reversed"].choice,
                 "composite": comp_pick}

        print(f"\n=== {sc['name']}  ({ms:.0f} ms, {resp.usage})")
        print(f"  expected:  {', '.join(labels[e] for e in sc['expected'])}")
        for k, pick in picks.items():
            ok = pick in sc["expected"]
            hits[k] += ok
            extra = ""
            if k in ("direct", "reversed"):
                extra = f"  conf {a[k].confidence:.2f}"
            print(f"  {k:<9}  {'✅' if ok else '❌'} {labels[pick]}{extra}")
        if picks["direct"] != picks["reversed"]:
            print("  ⚠️  order bias: direct and reversed disagree")
        print("  adv nouls: " + ", ".join(
            f"{labels[aid]}={a[f'adv:{aid}'].noul:.2f}" for aid, _ in acts))

    n = len(SCENARIOS)
    print("\n=== Summary: " + " | ".join(f"{k} {v}/{n}" for k, v in hits.items()))


if __name__ == "__main__":
    main()
