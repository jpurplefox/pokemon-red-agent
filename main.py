import sys
from game import Game

if __name__ == "__main__":
    strategy = None
    naming_ai = None
    overworld_ai = None
    flags = set(sys.argv[1:])

    if flags & {"--ai", "--naming", "--shop"}:
        from naming_ai import NamingAI
        naming_ai = NamingAI()
        print("Naming AI enabled")

    if "--ai" in flags:
        from battle_ai import BattleAI
        from scout_ai import ScoutAI
        from overworld_ai import OverworldAI
        scout = ScoutAI()
        strategy = BattleAI(scout=scout)
        overworld_ai = OverworldAI()
        print("Battle AI + Scout AI + Overworld AI enabled")
    elif "--shop" in flags:
        from overworld_ai import OverworldAI
        # Shop-only: creates the AI for purchase decisions but no overworld control
        overworld_ai = OverworldAI()
        overworld_ai._shop_only = True
        print("Shop AI enabled (manual overworld control)")

    Game("rom.gb", battle_strategy=strategy, naming_ai=naming_ai,
         overworld_ai=overworld_ai).run()
