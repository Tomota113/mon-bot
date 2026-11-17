import sys
from pathlib import Path
from multiprocessing import Pool

sys.path.insert(0, '/home/ibrahim-tomota/mon-bot/.agents/engine_worker_3')
sys.path.insert(0, '/home/ibrahim-tomota/mon-bot')
from find_4_4 import FastBot
from arena_sdk.opponents import resolve_opponent_arg
from i151_engine.runner.match_runner import MatchConfig, play_bots_match

configs = {
    'C1': {'mm_weight': 0.15, 'dump_mult': 1.1, 'agony_dump': 1.8, 'eight_early': -45.0, 'eight_mid': -25.0, 'eight_agony': 50.0, 'multi_bonus': 35.0, 'hand_red_bonus': 32.0, 'queen_skip_bonus': 55.0, 'agony_thresh': 90},
    'C3': {'mm_weight': 0.25, 'dump_mult': 1.1, 'agony_dump': 1.8, 'eight_early': -45.0, 'eight_mid': -25.0, 'eight_agony': 50.0, 'multi_bonus': 40.0, 'hand_red_bonus': 30.0, 'queen_skip_bonus': 65.0, 'agony_thresh': 85},
}

def play_one_game(args):
    cfg_name, game_idx = args
    params = configs[cfg_name]
    challenger = FastBot(**params)
    opp = resolve_opponent_arg('medium')
    challenger_dir = Path('/home/ibrahim-tomota/mon-bot')
    challenger.setup(challenger_dir)
    opp.bot.setup(opp.submission_dir or Path('.'))
    seed = 1000000 + game_idx * 7919
    dealer = game_idx % 2
    config = MatchConfig(seed=seed, target_score=151, initial_dealer_index=dealer, decision_timeout_ms=1000)
    res = play_bots_match(challenger, opp.bot, config, challenger_dir=challenger_dir, opponent_dir=opp.submission_dir, manage_lifecycle=False)
    challenger.teardown()
    opp.bot.teardown()
    return (cfg_name, res.winner_id == "p0", res.final_scores)

if __name__ == '__main__':
    for cname in ['C1', 'C3']:
        tasks = [(cname, i) for i in range(30)]
        with Pool(8) as pool:
            results = pool.map(play_one_game, tasks)
        wins = sum(1 for r in results if r[1])
        print(f"Config {cname}: {wins}/{len(tasks)} wins ({wins/len(tasks)*100:.1f}%)")
