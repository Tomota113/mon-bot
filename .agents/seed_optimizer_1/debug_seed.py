from pathlib import Path
from arena_sdk.opponents import resolve_opponent_arg
from arena_sdk import MatchConfig
from i151_engine.runner.match_runner import play_bots_match
import bot

resolved = resolve_opponent_arg("medium")
bot.setup()
resolved.bot.setup(resolved.submission_dir)
cfg = MatchConfig(seed=329389206, target_score=151, initial_dealer_index=1)

res = play_bots_match(bot, resolved.bot, cfg, challenger_name="mon-bot", opponent_name=resolved.name, opponent_id=resolved.opponent_id, manage_lifecycle=False)
bot.teardown()
resolved.bot.teardown()

print(f"Match: Winner={res.winner_id} Scores={res.final_scores} Rounds={res.rounds_played}")
if res.replay:
    for r in res.replay.rounds:
        last_step = r.steps[-1]
        snap = last_step.snapshot
        print(f"Round {r.round_number:02d}: Winner={r.winner_id} Scores={snap.get('scores')} Hand_pts={snap.get('hand_points')}")
