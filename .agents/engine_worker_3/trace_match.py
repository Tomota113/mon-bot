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
config = MatchConfig(seed=2063595735, target_score=151, initial_dealer_index=1, decision_timeout_ms=1000)
res = play_bots_match(
    bot,
    opp.bot,
    config,
    challenger_name="mon-bot",
    opponent_name=opp.name,
    opponent_id=opp.opponent_id,
    challenger_dir=challenger_dir,
    opponent_dir=opp.submission_dir,
    manage_lifecycle=False,
)
bot.teardown()
opp.bot.teardown()

print(f"Match Result: winner_id={res.winner_id}, scores={res.final_scores}, rounds={res.rounds_played}")
for r_idx, r in enumerate(res.round_results):
    print(f"Round {r_idx+1}: winner={r.winner_id}, p0_hand_score={r.scores.get('p0',0)}, p1_hand_score={r.scores.get('p1',0)}, running_scores={r.accumulated_scores}")
