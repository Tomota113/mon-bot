import sys
from pathlib import Path
sys.path.insert(0, '/home/ibrahim-tomota/mon-bot')
from arena_sdk.opponents import resolve_opponent_arg
from i151_engine.runner.match_runner import MatchConfig, play_bots_match
import bot

opp = resolve_opponent_arg('medium')
challenger_dir = Path('/home/ibrahim-tomota/mon-bot')
bot.setup(challenger_dir)
opp.bot.setup(opp.submission_dir or Path('.'))

seed = 1000000
config = MatchConfig(seed=seed, target_score=151, initial_dealer_index=0, decision_timeout_ms=1000)
res = play_bots_match(bot, opp.bot, config, challenger_dir=challenger_dir, opponent_dir=opp.submission_dir, manage_lifecycle=False)
bot.teardown()
opp.bot.teardown()

print(f"Match seed={seed}: winner={res.winner_id}, scores={res.final_scores}, rounds={res.rounds_played}")
if res.replay:
    for i, r in enumerate(res.replay.rounds):
        last_step = r.steps[-1]
        print(f"  Round {i+1}: winner={r.winner_id}, steps={len(r.steps)}, scores={last_step.snapshot['scores']}, hand_pts={last_step.snapshot['hand_points']}")
