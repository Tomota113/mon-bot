import sys, os
from pathlib import Path
from multiprocessing import Pool, cpu_count
sys.path.insert(0, '/home/ibrahim-tomota/mon-bot')
from arena_sdk.opponents import resolve_opponent_arg
from i151_engine.runner.match_runner import MatchConfig, play_bots_match
import bot

def run_single(args):
    seed, opp_name = args
    opp = resolve_opponent_arg(opp_name)
    challenger_dir = Path('/home/ibrahim-tomota/mon-bot')
    bot.setup(challenger_dir)
    opp.bot.setup(opp.submission_dir or Path('.'))
    config = MatchConfig(seed=seed, target_score=151, initial_dealer_index=seed % 2, decision_timeout_ms=1000)
    res = play_bots_match(
        bot, opp.bot, config,
        challenger_dir=challenger_dir,
        opponent_dir=opp.submission_dir,
        manage_lifecycle=False
    )
    bot.teardown()
    opp.bot.teardown()
    return (seed, opp_name, res.winner_id == 'p0', res.final_scores)

def main():
    seeds = [848914317, 1477911113, 2063595735, 329389206]
    n_cpu = min(cpu_count(), 16)
    with Pool(n_cpu) as pool:
        seed_res = pool.map(run_single, [(s, 'medium') for s in seeds])
        basic_res = pool.map(run_single, [(2000 + i, 'basic') for i in range(30)])
        med_res = pool.map(run_single, [(1000 + i, 'medium') for i in range(30)])

    print('==========================================')
    print('SEEDS VS MEDIUM:')
    for s, _, w, sc in seed_res:
        print(f'  Seed {s}: {"PASS" if w else "FAIL"} (Scores: {sc})')
    print(f'Seeds: {sum(1 for _,_,w,_ in seed_res)}/4')
    print(f'30 vs Basic: {sum(1 for _,_,w,_ in basic_res)}/30 ({sum(1 for _,_,w,_ in basic_res)/30*100:.1f}%)')
    print(f'30 vs Medium: {sum(1 for _,_,w,_ in med_res)}/30 ({sum(1 for _,_,w,_ in med_res)/30*100:.1f}%)')
    print('==========================================')

if __name__ == "__main__":
    main()
