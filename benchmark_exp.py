"""Experimentation harness to test bot variations vs medium_bot."""

from arena_sdk.opponents import resolve_opponent_arg
from i151_engine.runner.match_runner import play_bots_match
from arena_sdk import MatchConfig
import bot

resolved = resolve_opponent_arg("medium")

wins = 0
total = 20
scores = []

for seed in range(100, 100 + total):
    cfg = MatchConfig(seed=seed, target_score=151)
    res = play_bots_match(bot, resolved.bot, cfg, challenger_name="bot", opponent_name="medium")
    is_win = (res.winner_id == "p0")
    if is_win:
        wins += 1
    scores.append((res.final_scores.get("p0", 0), res.final_scores.get("p1", 0)))
    print(f"Seed {seed}: Winner={res.winner_id} Scores={res.final_scores} (Current {wins}/{len(scores)} = {wins/len(scores):.1%})")

print(f"\nFinal Win Rate: {wins}/{total} = {wins/total:.1%}")
