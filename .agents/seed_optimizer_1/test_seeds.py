from benchmark_suite import BenchmarkRunner
from pathlib import Path

runner = BenchmarkRunner(Path("bot.py"), profile_latency=True, target_score=151, verbose=True)
for s in [848914317, 1477911113, 2063595735, 329389206]:
    res = runner.run_seed("medium", s)
    w = res["winner"]
    sc = res["scores"]
    rd = res["rounds"]
    won = res["won"]
    print(f"Seed {s}: won={won} winner={w} scores={sc} rounds={rd}")
