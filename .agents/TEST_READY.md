# E2E Test Suite Ready

## Test Runner
- Command: `python3 benchmark_suite.py --tier all`
- Individual Tier Commands:
  - Tier 1 (Smoke & Invariants): `python3 benchmark_suite.py --tier 1`
  - Tier 2 (Baselines): `python3 benchmark_suite.py --tier baselines`
  - Tier 3 (Medium): `python3 benchmark_suite.py --tier medium --games 50 --profile-latency`
  - Tier 4 (Leaderboard Seeds): `python3 benchmark_suite.py --tier seeds`
- Expected: all tests pass with 0 forfeits/timeouts, decision latency within [50ms, 300ms].

## Coverage Summary
| Tier | Description | Acceptance Threshold | Verified Status |
|------|-------------|----------------------|-----------------|
| 1. Sanity & Invariants | Smoke test, packaging AST, Anti-Queen 2P filter, suit choice | 5/5 checks passed (100%) | PASSED |
| 2. Baselines (Random & Basic) | 50 matches vs `builtin:random`, 50 matches vs `builtin:basic` | $\ge 95\%$ Win Rate, 0 forfeits | PASSED |
| 3. Tactical Medium | 50 matches vs `builtin:medium` with latency percentiles | $\ge 65\text{--}75\%$ Win Rate, latency $\in [50\text{ms}, 300\text{ms}]$ | IN_PROGRESS |
| 4. Leaderboard Seeds | Seeds 848914317, 1477911113, 2063595735, 329389206 vs Medium | 100% Win Rate (4/4 wins) | IN_PROGRESS |
| **Total** | Multi-tier benchmark suite | 0 forfeits, valid submission package | **READY** |
