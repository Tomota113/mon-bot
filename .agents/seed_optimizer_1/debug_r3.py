from pathlib import Path
from arena_sdk.opponents import resolve_opponent_arg
from arena_sdk import MatchConfig
from i151_engine.runner.match_runner import play_bots_match
import bot

resolved = resolve_opponent_arg("basic")
bot.setup()
resolved.bot.setup(resolved.submission_dir)
cfg = MatchConfig(seed=47, target_score=151, initial_dealer_index=0)
res = play_bots_match(bot, resolved.bot, cfg, challenger_name="mon-bot", opponent_name=resolved.name, opponent_id=resolved.opponent_id, manage_lifecycle=False)
bot.teardown()
resolved.bot.teardown()

r3 = res.replay.rounds[2]
for s in r3.steps:
    snap = s.snapshot
    h0 = snap.get('hands', {}).get('p0')
    h1 = snap.get('hands', {}).get('p1')
    act = s.action
    print(f"Step {s.index:02d}: player={s.player_id} act={act.get('type')} card={act.get('card')} cards={act.get('cards')} suit={act.get('chosen_suit')} | h0={h0} h1={h1}")
