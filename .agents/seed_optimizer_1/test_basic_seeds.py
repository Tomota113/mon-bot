from pathlib import Path
from arena_sdk.opponents import resolve_opponent_arg
from arena_sdk import MatchConfig
from i151_engine.runner.match_runner import play_bots_match
import bot

resolved = resolve_opponent_arg("basic")
wins = 0
for seed in range(42, 52):
    p0_starts = ((seed - 42) % 2 == 0)
    dealer = 1 if p0_starts else 0
    bot.setup()
    resolved.bot.setup(resolved.submission_dir)
    cfg = MatchConfig(seed=seed, target_score=151, initial_dealer_index=dealer)
    res = play_bots_match(bot, resolved.bot, cfg, challenger_name="mon-bot", opponent_name=resolved.name, opponent_id=resolved.opponent_id, manage_lifecycle=False)
    bot.teardown()
    resolved.bot.teardown()
    won = (res.winner_id == "p0")
    if won:
        wins += 1
    print(f"Seed {seed}: won={won} scores={res.final_scores} rounds={res.rounds_played}")

print(f"Total Won: {wins}/10")
