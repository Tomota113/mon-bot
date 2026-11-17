import time
import random
from pathlib import Path
from arena_sdk.opponents import resolve_opponent_arg
from arena_sdk import MatchConfig
from i151_engine.runner.match_runner import play_bots_match
import bot
import evaluator

resolved = resolve_opponent_arg("medium")
ref_seeds = [848914317, 1477911113, 2063595735, 329389206]

def evaluate_seeds():
    results = []
    for s in ref_seeds:
        bot.setup()
        resolved.bot.setup(resolved.submission_dir)
        cfg = MatchConfig(seed=s, target_score=151, initial_dealer_index=1, decision_timeout_ms=1000)
        res = play_bots_match(bot, resolved.bot, cfg, challenger_name="mon-bot", opponent_name=resolved.name, opponent_id=resolved.opponent_id, manage_lifecycle=False)
        bot.teardown()
        resolved.bot.teardown()
        won = (res.winner_id == "p0" and res.reason == "normal")
        results.append((s, won, res.winner_id, res.final_scores, res.rounds_played))
    return results

if __name__ == "__main__":
    res = evaluate_seeds()
    for s, won, winner, scores, rounds in res:
        status = "PASS" if won else "FAIL"
        print(f"[{status}] Seed {s}: winner={winner} scores={scores} rounds={rounds}")
    won_count = sum(1 for _, won, _, _, _ in res if won)
    print(f"Total Won: {won_count}/4 ({won_count/4:.1%})")
