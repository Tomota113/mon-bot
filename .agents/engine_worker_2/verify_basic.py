import sys
from pathlib import Path

sys.path.insert(0, '/home/ibrahim-tomota/mon-bot')
from arena_sdk.opponents import resolve_opponent_arg
from arena_sdk import Action, ActionType, PlayerView
from i151_engine.runner.match_runner import MatchConfig, play_bots_match
from i151_engine.bots.protocol import Bot
import evaluator
import bot

# Let's update bot.py and evaluator.py with the exact winning parameters
# mm_weight = 0.35
# dump_mult = 1.2
# agony_dump = 1.8
# eight_early_pen = -45.0
# eight_mid_pen = -25.0
# eight_agony_bonus = 45.0
# agony_score_thresh = 95
