"""TypeSafe demo — catch/defeat decision without free-text parsing.

Reuses ScoutAI's prompt builder as the TypeSafe `state`, and asks
structured questions instead of parsing "DECISION: CATCH" from LLM text.

Setup:
    venv/bin/pip install typesafe-sdk
    export TYPESAFE_API_KEY=...        # or put it in .env

Run:
    venv/bin/python -m tools.typesafe_scout_demo
"""

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from agents.scout_ai import ScoutAI

load_dotenv()

SCENARIOS = [
    ("PIDGEY", 3, []),
    ("PIDGEY", 4, [{"name": "CHARMANDER", "level": 8}, {"name": "PIDGEOTTO", "level": 18}]),
    ("MAGIKARP", 5, [{"name": "CHARMANDER", "level": 12}, {"name": "PIKACHU", "level": 10}]),
    ("RATTATA", 3, [{"name": "SQUIRTLE", "level": 9}, {"name": "RATICATE", "level": 20}]),
]

QUESTIONS = {
    "decision": Choice(
        instructions="As a Pokemon Red team-building strategist, should the "
                     "trainer catch this wild Pokemon or defeat it?",
        criteria={
            "catch": "Adds new type coverage or strong evolution potential, "
                     "and is not already on the team",
            "defeat": "Redundant type or evolution line, or low value for the team",
        },
    ),
    "team_value": Score(
        instructions="How much this Pokemon would improve the current team",
        criteria=[
            "No value, redundant",
            "Minor value",
            "Useful addition",
            "Excellent addition",
        ],
    ),
    "duplicate_line": Noul(
        instructions="The team already has a Pokemon from the same evolution line",
    ),
}


def main():
    client = TypeSafeClient()
    scout = ScoutAI(llm=None)  # only used for its prompt builder

    for name, level, team in SCENARIOS:
        state = scout._build_prompt(name, level, team)
        response = client.system_one(state=state, questions=QUESTIONS)
        a = response.answers

        team_str = ", ".join(m["name"] for m in team) or "empty"
        print(f"\n=== Wild {name} Lv{level} | team: {team_str}")
        print(f"  decision:       {a['decision'].choice} "
              f"(confidence {a['decision'].confidence:.2f}, "
              f"probs {a['decision'].probabilities})")
        print(f"  team_value:     {a['team_value'].score:.2f} "
              f"(confidence {a['team_value'].confidence:.2f})")
        print(f"  duplicate_line: {a['duplicate_line'].noul}")
        print(f"  usage:          {response.usage}")


if __name__ == "__main__":
    main()
