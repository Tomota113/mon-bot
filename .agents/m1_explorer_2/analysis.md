# Analysis: Benchmark Threshold Alignment & Hard Latency Gating Strategy

**Author**: M1 Explorer 2  
**Date**: 2026-09-09  
**Target File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Milestone**: M1 (Symmetric Benchmark Suite R4)  
**Task Scope**:
1. Aligning benchmark thresholds in `benchmark_suite.py`:
   - Tier 2: `builtin:random` win_rate >= 98.0%, `builtin:basic` win_rate >= 98.0%, 0 forfeits.
   - Tier 3: `builtin:medium` win_rate >= 70.0% across the 50 symmetric games, 0 forfeits.
   - Tier 4: Reference seeds `[848914317, 1477911113, 2063595735, 329389206]` win rate >= 75.0% (at least 3/4 wins), 0 forfeits.
2. Implementing hard latency gating in `overall_passed`:
   - Average latency strictly < 50.0 ms (`lat_stats["mean"] < 50.0`).
   - Max latency < 300.0 ms (`lat_stats["max"] < 300.0`).
   - 0 timeouts and 0 forfeits across all tiers (`total_timeouts == 0` and `total_forfeits == 0`).

---

## 1. Context & Architectural Assessment

### 1.1 Requirements vs Current Code Base
In `ORIGINAL_REQUEST.md` (lines 45-55) and tournament regulations:
- **Tier 2 Baselines**: Win rate >= 98% vs `builtin:random` and `builtin:basic` with 0 forfeits.
- **Tier 3 Competitive Medium**: Win rate >= 70% vs `builtin:medium` across 50 symmetric games with alternating dealers and 0 forfeits.
- **Tier 4 Reference Seeds**: Win rate >= 75% across reference seeds `[848914317, 1477911113, 2063595735, 329389206]` (at least 3/4 wins) with 0 forfeits.
- **Latency & Reliability**: Average decision latency strictly < 50.0 ms, max latency < 300.0 ms, budget 400 ms (server hard cutoff), 0 timeouts, 0 forfeits across all tiers.

### 1.2 Identified Deficiencies in `benchmark_suite.py`
Inspection of `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` revealed four critical gaps:
1. **Lax Tier 2 Basic Threshold**:
   - Line 966 sets `t2_basic["win_rate_pct"] >= 80.0` (and `ReportFormatter` lines 772, 798 target 80.0%).
   - Line 964 sets `t2_random["win_rate_pct"] >= 95.0` (instead of 98.0%).
   - Both baselines must require `>= 98.0%` with `0 forfeits`.
2. **Lax Tier 3 Medium Threshold**:
   - Line 982 sets `t3_medium["win_rate_pct"] >= 65.0` (and `ReportFormatter` lines 811, 813 target 65.0%).
   - Must require `>= 70.0%` across the 50 symmetric matches.
3. **Overly Strict Tier 4 Threshold (100% vs 75%)**:
   - Line 1001 sets `t4_passed = all(sr["won"] for sr in seed_results)` requiring 4/4 (100%).
   - Must evaluate `(wins / total) * 100.0 >= 75.0` (at least 3/4 wins) with `forfeits == 0`.
4. **Complete Absence of Latency Gating in `overall_passed`**:
   - Lines 1009-1014 compute `overall_passed` exclusively from tier booleans:
     ```python
     overall_passed = (
         (not run_t1 or t1_passed)
         and (not run_t2 or t2_passed)
         and (not run_t3 or t3_passed)
         and (not run_t4 or t4_passed)
     )
     ```
   - Even if average latency were 800 ms or max latency reached 999 ms, `overall_passed` would currently return `True` (and exit code 0) if win rates passed!
   - `final_lat_stats` is computed at line 1016 and passed to `print_verdict`, but `print_verdict` (lines 884-900) does not evaluate or display the latency status.

---

## 2. Line-by-Line Implementation Strategy

### Modification Block 1: Module Docstring (Lines 6-8)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

#### Current Code (Lines 6-8):
```python
6: - Tier 2: Baselines vs builtin:random and builtin:basic (>= 95% win rate, 0 forfeits).
7: - Tier 3: Tactical match vs builtin:medium (>= 65-75% win rate, 0 forfeits, move latency profiling).
8: - Tier 4: Leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206) vs builtin:medium (100% win rate).
```

#### Proposed Replacement:
```python
- Tier 2: Baselines vs builtin:random and builtin:basic (>= 98% win rate, 0 forfeits).
- Tier 3: Tactical match vs builtin:medium (>= 70% win rate across 50 symmetric games, 0 forfeits, move latency profiling).
- Tier 4: Leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206) vs builtin:medium (>= 75% win rate, 0 forfeits).
```

---

### Modification Block 2: LatencyProfile Stats Enhancement (Lines 100-131)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

#### Rationale:
Add explicit tracking for official server limit (`timeouts_gt_400ms`), while preserving `timeouts_gt_1000ms` and `slow_moves_gt_300ms`.

#### Current Code (Lines 100-131):
```python
100:                 "max": 0.0,
101:                 "slow_moves_gt_300ms": 0,
102:                 "timeouts_gt_1000ms": 0,
103:                 "budget_compliance_pct": 100.0,
104:             }
105:         s = sorted(self.latencies_ms)
106:         n = len(s)
107: 
108:         def percentile(pct: float) -> float:
109:             k = (n - 1) * (pct / 100.0)
110:             f = int(k)
111:             c = min(f + 1, n - 1)
112:             d = k - f
113:             return round(s[f] + d * (s[c] - s[f]), 3)
114: 
115:         gt_300 = sum(1 for x in s if x > 300.0)
116:         gt_1000 = sum(1 for x in s if x > 1000.0)
117:         compliance = round(100.0 * (1.0 - gt_300 / n), 2)
118: 
119:         return {
120:             "count": n,
121:             "min": round(s[0], 3),
122:             "mean": round(sum(s) / n, 3),
123:             "median": percentile(50.0),
124:             "p90": percentile(90.0),
125:             "p95": percentile(95.0),
126:             "p99": percentile(99.0),
127:             "max": round(s[-1], 3),
128:             "slow_moves_gt_300ms": gt_300,
129:             "timeouts_gt_1000ms": gt_1000,
130:             "budget_compliance_pct": compliance,
131:         }
```

#### Proposed Replacement:
```python
                "max": 0.0,
                "slow_moves_gt_300ms": 0,
                "timeouts_gt_400ms": 0,
                "timeouts_gt_1000ms": 0,
                "budget_compliance_pct": 100.0,
            }
        s = sorted(self.latencies_ms)
        n = len(s)

        def percentile(pct: float) -> float:
            k = (n - 1) * (pct / 100.0)
            f = int(k)
            c = min(f + 1, n - 1)
            d = k - f
            return round(s[f] + d * (s[c] - s[f]), 3)

        gt_300 = sum(1 for x in s if x > 300.0)
        gt_400 = sum(1 for x in s if x > 400.0)
        gt_1000 = sum(1 for x in s if x > 1000.0)
        compliance = round(100.0 * (1.0 - gt_300 / n), 2)

        return {
            "count": n,
            "min": round(s[0], 3),
            "mean": round(sum(s) / n, 3),
            "median": percentile(50.0),
            "p90": percentile(90.0),
            "p95": percentile(95.0),
            "p99": percentile(99.0),
            "max": round(s[-1], 3),
            "slow_moves_gt_300ms": gt_300,
            "timeouts_gt_400ms": gt_400,
            "timeouts_gt_1000ms": gt_1000,
            "budget_compliance_pct": compliance,
        }
```

---

### Modification Block 3: ReportFormatter Tier 2 Display (Lines 768-804)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

#### Current Code (Lines 768-804):
```python
768:         print(
769:             f"\n{Colors.BOLD}[TIER 2: BASELINE OPPONENTS (Target >= 95% WR)]{Colors.RESET}"
770:         )
771: 
772:         def fmt_res(r: dict[str, Any]) -> str:
773:             target_wr = 95.0 if "random" in r["opponent_spec"] else 80.0
774:             passed = r["win_rate_pct"] >= target_wr and r["forfeits"] == 0
775:             status = (
776:                 f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
777:                 if passed
778:                 else f"{Colors.RED}✗ FAILED{Colors.RESET}"
779:             )
...
796:         c_color = (
797:             Colors.GREEN
798:             if (
799:                 random_res["win_rate_pct"] >= 95.0 and basic_res["win_rate_pct"] >= 80.0
800:             )
801:             else Colors.RED
802:         )
803:         print(
804:             f"  {Colors.BOLD}Tier 2 Result:{Colors.RESET} {c_color}{total_wins}/{total_games} Games Won ({total_wr:.1f}% Aggregate WR){Colors.RESET}"
805:         )
```

#### Proposed Replacement:
```python
        print(
            f"\n{Colors.BOLD}[TIER 2: BASELINE OPPONENTS (Target >= 98% WR, 0 Forfeits)]{Colors.RESET}"
        )

        def fmt_res(r: dict[str, Any]) -> str:
            target_wr = 98.0
            passed = r["win_rate_pct"] >= target_wr and r["forfeits"] == 0
            status = (
                f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
                if passed
                else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            )
            wr_str = f"{r['win_rate_pct']:.1f}% WR"
            score_str = f"{r['wins']}-{r['losses']}"
            if r["draws"]:
                score_str += f"-{r['draws']}"
            return (
                f"  {status} vs {Colors.CYAN}{r['opponent_spec']:<15}{Colors.RESET} "
                f"({r['games']:>2} games) : {score_str:>7} ({wr_str:>8}) | "
                f"Forfeits: {r['forfeits']}  [{r['opponent_name']}]"
            )

        print(fmt_res(random_res))
        print(fmt_res(basic_res))

        total_games = random_res["games"] + basic_res["games"]
        total_wins = random_res["wins"] + basic_res["wins"]
        total_wr = (total_wins / total_games) * 100.0 if total_games else 0.0
        c_color = (
            Colors.GREEN
            if (
                random_res["win_rate_pct"] >= 98.0
                and basic_res["win_rate_pct"] >= 98.0
                and random_res["forfeits"] == 0
                and basic_res["forfeits"] == 0
            )
            else Colors.RED
        )
        print(
            f"  {Colors.BOLD}Tier 2 Result:{Colors.RESET} {c_color}{total_wins}/{total_games} Games Won ({total_wr:.1f}% Aggregate WR){Colors.RESET}"
        )
```

---

### Modification Block 4: ReportFormatter Tier 3 Display (Lines 811-828)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

#### Current Code (Lines 811-828):
```python
811:         print(
812:             f"\n{Colors.BOLD}[TIER 3: COMPETITIVE TACTICAL MATCH (Target >= 65% WR vs Medium)]{Colors.RESET}"
813:         )
814:         passed = medium_res["win_rate_pct"] >= 65.0 and medium_res["forfeits"] == 0
815:         status = (
816:             f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
817:             if passed
818:             else f"{Colors.RED}✗ FAILED{Colors.RESET}"
819:         )
820:         score_str = f"{medium_res['wins']}-{medium_res['losses']}"
821:         if medium_res["draws"]:
822:             score_str += f"-{medium_res['draws']}"
823: 
824:         print(
825:             f"  {status} vs {Colors.CYAN}{medium_res['opponent_spec']:<15}{Colors.RESET} "
826:             f"({medium_res['games']:>2} games) : {score_str:>7} ({medium_res['win_rate_pct']:.1f}% WR) | "
827:             f"Forfeits: {medium_res['forfeits']}  [{medium_res['opponent_name']}]"
828:         )
```

#### Proposed Replacement:
```python
        print(
            f"\n{Colors.BOLD}[TIER 3: COMPETITIVE TACTICAL MATCH (Target >= 70% WR vs Medium, 0 Forfeits)]{Colors.RESET}"
        )
        passed = medium_res["win_rate_pct"] >= 70.0 and medium_res["forfeits"] == 0
        status = (
            f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
            if passed
            else f"{Colors.RED}✗ FAILED{Colors.RESET}"
        )
        score_str = f"{medium_res['wins']}-{medium_res['losses']}"
        if medium_res["draws"]:
            score_str += f"-{medium_res['draws']}"

        print(
            f"  {status} vs {Colors.CYAN}{medium_res['opponent_spec']:<15}{Colors.RESET} "
            f"({medium_res['games']:>2} games) : {score_str:>7} ({medium_res['win_rate_pct']:.1f}% WR) | "
            f"Forfeits: {medium_res['forfeits']}  [{medium_res['opponent_name']}]"
        )
        if "p0_wins" in medium_res and "p1_wins" in medium_res:
            p0_g = medium_res.get("p0_games", medium_res["games"] // 2)
            p1_g = medium_res.get("p1_games", medium_res["games"] - p0_g)
            p0_wr = (medium_res["p0_wins"] / p0_g * 100.0) if p0_g else 0.0
            p1_wr = (medium_res["p1_wins"] / p1_g * 100.0) if p1_g else 0.0
            print(
                f"    Symmetric split: P0 (Challenger): {medium_res['p0_wins']}/{p0_g} ({p0_wr:.1f}%) │ "
                f"P1 (Opponent): {medium_res['p1_wins']}/{p1_g} ({p1_wr:.1f}%)"
            )
```

---

### Modification Block 5: ReportFormatter Tier 4 Display (Lines 854-883)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

#### Current Code (Lines 854-883):
```python
854:     @staticmethod
855:     def print_tier4_results(seed_results: list[dict[str, Any]]) -> None:
856:         print(
857:             f"\n{Colors.BOLD}[TIER 4: LEADERBOARD REFERENCE SEEDS (Target: 100% Win Rate)]{Colors.RESET}"
858:         )
859:         wins = 0
860:         for s in seed_results:
861:             is_win = s["won"]
862:             if is_win:
863:                wins += 1
864:             status = (
865:                 f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
866:                 if is_win
867:                 else f"{Colors.RED}✗ FAILED{Colors.RESET}"
868:             )
869:             p0_s = s["scores"].get("p0", 0)
870:             p1_s = s["scores"].get("p1", 0)
871:             score_fmt = f"{p0_s}/{p1_s}"
872:             print(
873:                 f"  {status} Seed {Colors.CYAN}{s['seed']:<10}{Colors.RESET} vs {s['opponent']} : "
874:                 f"Winner = {s['winner']:<8} (Score: {score_fmt:>7}, Rounds: {s['rounds']:>2}, Steps: {s['steps']:>4})"
875:             )
876: 
877:         total = len(seed_results)
878:         pct = (wins / total) * 100.0 if total else 0.0
879:         c_color = Colors.GREEN if wins == total else Colors.RED
880:         print(
881:             f"  {Colors.BOLD}Tier 4 Result:{Colors.RESET} {c_color}{wins}/{total} Benchmark Seeds Won ({pct:.1f}%){Colors.RESET}"
882:         )
```

#### Proposed Replacement:
```python
    @staticmethod
    def print_tier4_results(seed_results: list[dict[str, Any]]) -> None:
        print(
            f"\n{Colors.BOLD}[TIER 4: LEADERBOARD REFERENCE SEEDS (Target >= 75% Win Rate, 0 Forfeits)]{Colors.RESET}"
        )
        wins = 0
        forfeits = 0
        for s in seed_results:
            is_win = s.get("won", False)
            is_forfeit = s.get("forfeit", False) or s.get("reason") != "normal"
            if is_win:
                wins += 1
            if is_forfeit:
                forfeits += 1
            status = (
                f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
                if is_win and not is_forfeit
                else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            )
            p0_s = s["scores"].get("p0", 0)
            p1_s = s["scores"].get("p1", 0)
            score_fmt = f"{p0_s}/{p1_s}"
            print(
                f"  {status} Seed {Colors.CYAN}{s['seed']:<10}{Colors.RESET} vs {s['opponent']} : "
                f"Winner = {s['winner']:<8} (Score: {score_fmt:>7}, Rounds: {s['rounds']:>2}, Steps: {s['steps']:>4})"
            )

        total = len(seed_results)
        pct = (wins / total) * 100.0 if total else 0.0
        passed = pct >= 75.0 and forfeits == 0
        c_color = Colors.GREEN if passed else Colors.RED
        print(
            f"  {Colors.BOLD}Tier 4 Result:{Colors.RESET} {c_color}{wins}/{total} Benchmark Seeds Won ({pct:.1f}%), {forfeits} Forfeits{Colors.RESET}"
        )
```

---

### Modification Block 6: ReportFormatter Verdict with Latency Gating (Lines 884-901)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

#### Current Code (Lines 884-901):
```python
884:     @staticmethod
885:     def print_verdict(all_passed: bool, latency_stats: dict[str, Any]) -> None:
886:         print(
887:             f"\n{Colors.DIM}════════════════════════════════════════════════════════════════════════════════{Colors.RESET}"
888:         )
889:         if all_passed:
890:             print(
891:                 f"{Colors.BOLD}{Colors.GREEN} OVERALL VERDICT: GRAND_MASTER_READY ★★★★★ "
892:                 f"(ALL ACCEPTANCE CRITERIA SATISFIED){Colors.RESET}"
893:             )
894:         else:
895:             print(
896:                 f"{Colors.BOLD}{Colors.RED} OVERALL VERDICT: BENCHMARK_FAILED ⚠️ "
897:                 f"(ONE OR MORE ACCEPTANCE CRITERIA WERE NOT MET){Colors.RESET}"
898:             )
899:         print(
900:             f"{Colors.DIM}════════════════════════════════════════════════════════════════════════════════{Colors.RESET}\n"
901:         )
```

#### Proposed Replacement:
```python
    @staticmethod
    def print_verdict(
        all_passed: bool,
        latency_stats: dict[str, Any],
        latency_passed: bool = True,
        total_forfeits: int = 0,
        total_timeouts: int = 0,
    ) -> None:
        print(
            f"\n{Colors.DIM}════════════════════════════════════════════════════════════════════════════════{Colors.RESET}"
        )
        if latency_stats.get("count", 0) > 0:
            lat_status = (
                f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
                if latency_passed
                else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            )
            mean_v = latency_stats.get("mean", 0.0)
            max_v = latency_stats.get("max", 0.0)
            mean_col = Colors.GREEN if mean_v < 50.0 else Colors.RED
            max_col = Colors.GREEN if max_v < 300.0 else Colors.RED
            tout_col = Colors.GREEN if total_timeouts == 0 else Colors.RED
            forfeit_col = Colors.GREEN if total_forfeits == 0 else Colors.RED
            print(
                f"  {Colors.BOLD}Hard Latency Gating:{Colors.RESET} {lat_status} "
                f"(Mean: {mean_col}{mean_v:.2f}ms{Colors.RESET} < 50.0ms │ "
                f"Max: {max_col}{max_v:.2f}ms{Colors.RESET} < 300.0ms │ "
                f"Timeouts: {tout_col}{total_timeouts}{Colors.RESET} │ "
                f"Forfeits: {forfeit_col}{total_forfeits}{Colors.RESET})"
            )
        if all_passed:
            print(
                f"{Colors.BOLD}{Colors.GREEN} OVERALL VERDICT: GRAND_MASTER_READY ★★★★★ "
                f"(ALL ACCEPTANCE CRITERIA SATISFIED){Colors.RESET}"
            )
        else:
            print(
                f"{Colors.BOLD}{Colors.RED} OVERALL VERDICT: BENCHMARK_FAILED ⚠️ "
                f"(ONE OR MORE ACCEPTANCE CRITERIA WERE NOT MET){Colors.RESET}"
            )
        print(
            f"{Colors.DIM}════════════════════════════════════════════════════════════════════════════════{Colors.RESET}\n"
        )
```

---

### Modification Block 7: Tier 2, 3, 4 Execution & Hard Gating in `run_benchmark` (Lines 963-1038)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

#### Current Code (Lines 963-1038):
```python
963:         t2_passed = (
964:             t2_random["win_rate_pct"] >= 95.0
965:             and t2_random["forfeits"] == 0
966:             and t2_basic["win_rate_pct"] >= 80.0
967:             and t2_basic["forfeits"] == 0
968:         )
969:         results_data["tier2_baselines"] = {
970:             "random": t2_random,
971:             "basic": t2_basic,
972:             "passed": t2_passed,
973:         }
974:         ReportFormatter.print_tier2_results(t2_random, t2_basic)
975: 
976:     # Execution TIER 3
977:     if run_t3:
978:         print(
979:             f"\n{Colors.DIM}Running Tier 3 Tactical Match ({games} games vs Medium)...{Colors.RESET}"
980:         )
981:         t3_medium = runner.run_series("medium", games=games, base_seed=base_seed)
982:         t3_passed = t3_medium["win_rate_pct"] >= 65.0 and t3_medium["forfeits"] == 0
983:         lat_stats = runner.latency_profile.compute_stats()
984:         results_data["tier3_tactical"] = {
985:             "medium": t3_medium,
986:             "passed": t3_passed,
987:         }
988:         results_data["latency_profile_ms"] = lat_stats
989:         ReportFormatter.print_tier3_results(t3_medium, lat_stats)
990: 
991:     # Execution TIER 4
992:     if run_t4:
993:         print(
994:             f"\n{Colors.DIM}Running Tier 4 Leaderboard Reference Seeds vs Medium...{Colors.RESET}"
995:         )
996:         ref_seeds = [848914317, 1477911113, 2063595735, 329389206]
997:         seed_results: list[dict[str, Any]] = []
998:         for s in ref_seeds:
999:             s_res = runner.run_seed("medium", s)
1000:             seed_results.append(s_res)
1001:         t4_passed = all(sr["won"] for sr in seed_results)
1002:         results_data["tier4_seeds"] = {
1003:             "seeds": seed_results,
1004:             "passed": t4_passed,
1005:         }
1006:         ReportFormatter.print_tier4_results(seed_results)
1007: 
1008:     # Final overall status
1009:     overall_passed = (
1010:         (not run_t1 or t1_passed)
1011:         and (not run_t2 or t2_passed)
1012:         and (not run_t3 or t3_passed)
1013:         and (not run_t4 or t4_passed)
1014:     )
1015: 
1016:     final_lat_stats = runner.latency_profile.compute_stats()
1017:     results_data["summary"] = {
1018:         "tier1_passed": t1_passed if run_t1 else None,
1019:         "tier2_passed": t2_passed if run_t2 else None,
1020:         "tier3_passed": t3_passed if run_t3 else None,
1021:         "tier4_passed": t4_passed if run_t4 else None,
1022:         "overall_passed": overall_passed,
1023:         "verdict": "GRAND_MASTER_READY" if overall_passed else "BENCHMARK_FAILED",
1024:     }
1025:     if "latency_profile_ms" not in results_data:
1026:         results_data["latency_profile_ms"] = final_lat_stats
1027: 
1028:     ReportFormatter.print_verdict(overall_passed, final_lat_stats)
```

#### Proposed Replacement:
```python
        t2_passed = (
            t2_random["win_rate_pct"] >= 98.0
            and t2_random["forfeits"] == 0
            and t2_basic["win_rate_pct"] >= 98.0
            and t2_basic["forfeits"] == 0
        )
        results_data["tier2_baselines"] = {
            "random": t2_random,
            "basic": t2_basic,
            "passed": t2_passed,
        }
        ReportFormatter.print_tier2_results(t2_random, t2_basic)

    # Execution TIER 3
    if run_t3:
        print(
            f"\n{Colors.DIM}Running Tier 3 Tactical Match ({games} games vs Medium)...{Colors.RESET}"
        )
        t3_medium = runner.run_series("medium", games=games, base_seed=base_seed)
        t3_passed = t3_medium["win_rate_pct"] >= 70.0 and t3_medium["forfeits"] == 0
        lat_stats = runner.latency_profile.compute_stats()
        results_data["tier3_tactical"] = {
            "medium": t3_medium,
            "passed": t3_passed,
        }
        results_data["latency_profile_ms"] = lat_stats
        ReportFormatter.print_tier3_results(t3_medium, lat_stats)

    # Execution TIER 4
    if run_t4:
        print(
            f"\n{Colors.DIM}Running Tier 4 Leaderboard Reference Seeds vs Medium...{Colors.RESET}"
        )
        ref_seeds = [848914317, 1477911113, 2063595735, 329389206]
        seed_results: list[dict[str, Any]] = []
        for s in ref_seeds:
            s_res = runner.run_seed("medium", s)
            seed_results.append(s_res)
        t4_wins = sum(1 for sr in seed_results if sr.get("won", False))
        t4_forfeits = sum(
            1 for sr in seed_results if sr.get("forfeit", False) or sr.get("reason") != "normal"
        )
        t4_win_rate_pct = (t4_wins / len(seed_results) * 100.0) if seed_results else 0.0
        t4_passed = t4_win_rate_pct >= 75.0 and t4_forfeits == 0
        results_data["tier4_seeds"] = {
            "seeds": seed_results,
            "wins": t4_wins,
            "total": len(seed_results),
            "win_rate_pct": round(t4_win_rate_pct, 2),
            "forfeits": t4_forfeits,
            "passed": t4_passed,
        }
        ReportFormatter.print_tier4_results(seed_results)

    # Global latency profiling & reliability audit across all executed matches
    final_lat_stats = runner.latency_profile.compute_stats()

    # Aggregate forfeit counting across all executed tiers
    total_forfeits = 0
    if run_t1:
        smoke_chk = t1_results.get("checks", {}).get("smoke_test", {})
        if not smoke_chk.get("passed", False):
            total_forfeits += 1
    if run_t2:
        total_forfeits += t2_random.get("forfeits", 0) + t2_basic.get("forfeits", 0)
    if run_t3:
        total_forfeits += t3_medium.get("forfeits", 0)
    if run_t4:
        total_forfeits += t4_forfeits

    # Timeout auditing: match-level timeouts + decision-level timeouts (> 1000ms or > 400ms)
    match_timeouts = 0
    if run_t2:
        match_timeouts += sum(1 for m in t2_random.get("matches", []) if m.get("reason") == "timeout")
        match_timeouts += sum(1 for m in t2_basic.get("matches", []) if m.get("reason") == "timeout")
    if run_t3:
        match_timeouts += sum(1 for m in t3_medium.get("matches", []) if m.get("reason") == "timeout")
    if run_t4:
        match_timeouts += sum(1 for s in seed_results if s.get("reason") == "timeout")

    decision_timeouts = final_lat_stats.get("timeouts_gt_1000ms", 0)
    slow_moves_300 = final_lat_stats.get("slow_moves_gt_300ms", 0)
    total_timeouts = match_timeouts + decision_timeouts

    # Hard Latency Gating:
    # 1. Average latency strictly < 50.0 ms
    # 2. Max latency < 300.0 ms
    # 3. 0 timeouts and 0 slow moves > 300ms
    if profile_latency and (run_t2 or run_t3 or run_t4):
        latency_passed = (
            final_lat_stats["count"] > 0
            and final_lat_stats["mean"] < 50.0
            and final_lat_stats["max"] < 300.0
            and decision_timeouts == 0
            and slow_moves_300 == 0
        )
    else:
        latency_passed = True

    # Final overall status: all enabled tiers must pass + hard latency gating + zero forfeits/timeouts
    overall_passed = (
        (not run_t1 or t1_passed)
        and (not run_t2 or t2_passed)
        and (not run_t3 or t3_passed)
        and (not run_t4 or t4_passed)
        and latency_passed
        and (total_forfeits == 0)
        and (total_timeouts == 0)
    )

    results_data["latency_gating"] = {
        "profiled": profile_latency,
        "decisions_count": final_lat_stats.get("count", 0),
        "mean_latency_ms": final_lat_stats.get("mean", 0.0),
        "mean_threshold_ms": 50.0,
        "mean_passed": (final_lat_stats.get("mean", 0.0) < 50.0) if final_lat_stats.get("count", 0) > 0 else True,
        "max_latency_ms": final_lat_stats.get("max", 0.0),
        "max_threshold_ms": 300.0,
        "max_passed": (final_lat_stats.get("max", 0.0) < 300.0) if final_lat_stats.get("count", 0) > 0 else True,
        "slow_moves_gt_300ms": slow_moves_300,
        "decision_timeouts_gt_1000ms": decision_timeouts,
        "match_timeouts": match_timeouts,
        "total_timeouts": total_timeouts,
        "total_forfeits": total_forfeits,
        "passed": latency_passed,
    }

    results_data["summary"] = {
        "tier1_passed": t1_passed if run_t1 else None,
        "tier2_passed": t2_passed if run_t2 else None,
        "tier3_passed": t3_passed if run_t3 else None,
        "tier4_passed": t4_passed if run_t4 else None,
        "latency_passed": latency_passed,
        "total_forfeits": total_forfeits,
        "total_timeouts": total_timeouts,
        "overall_passed": overall_passed,
        "verdict": "GRAND_MASTER_READY" if overall_passed else "BENCHMARK_FAILED",
    }
    if "latency_profile_ms" not in results_data:
        results_data["latency_profile_ms"] = final_lat_stats

    ReportFormatter.print_verdict(
        overall_passed=overall_passed,
        latency_stats=final_lat_stats,
        latency_passed=latency_passed,
        total_forfeits=total_forfeits,
        total_timeouts=total_timeouts,
    )
```

---

## 3. Interaction & Boundary Analysis with Peer Agents

### 3.1 Coordination with M1 Explorer 1 (Slot Inversion & Symmetric Series)
- `m1_explorer_1` is responsible for updating `BenchmarkRunner.run_series()` to support 25 p0 / 25 p1 matches and tracking `my_slot`.
- Our threshold check for Tier 3 (`t3_medium["win_rate_pct"] >= 70.0 and t3_medium["forfeits"] == 0`) directly consumes the output of `run_series()`.
- Furthermore, our enhanced `ReportFormatter.print_tier3_results()` gracefully detects whether `p0_wins` and `p1_wins` are present in `medium_res`, displaying the symmetric breakdown without breaking backwards compatibility if they are absent.

### 3.2 Coordination with M1 Explorer 3 (Packaging & Test Verification Pipeline)
- `m1_explorer_3` is verifying `mon-bot-submission.zip` in Tier 1.
- In `Tier 1`, any failure in `t1_results["passed"]` automatically propagates to `overall_passed = False`.
- Smoke test forfeit detection in Tier 1 is incorporated into `total_forfeits`.

### 3.3 Coordination with Engine Milestones (M2, M3, M4)
- Current measured bot latency (Tier 4: mean 6.24ms, max 190.15ms; Tier 3: mean 6.68ms, max 203.80ms) comfortably passes the strict `< 50.0ms` mean and `< 300.0ms` max limits.
- The hard gating ensures that as M3 implements deep Minimax lookahead (5-8 plies), any timing regression (e.g. mean >= 50ms or max >= 300ms) will immediately trip the benchmark and prevent premature completion claims.

---

## 4. Verification Matrix

| Check | Target / Condition | Verification Tool / Command |
|---|---|---|
| **Tier 2 Baselines** | Random >= 98.0%, Basic >= 98.0%, 0 forfeits | `python3 benchmark_suite.py --tier 2` |
| **Tier 3 Medium** | Medium >= 70.0% across 50 symmetric games, 0 forfeits | `python3 benchmark_suite.py --tier 3 --games 50` |
| **Tier 4 Seeds** | 4 seeds >= 75.0% (at least 3/4 wins), 0 forfeits | `python3 benchmark_suite.py --tier 4` |
| **Hard Latency Gating** | Mean < 50.0ms, Max < 300.0ms, 0 timeouts, 0 slow moves | Inspect `results_data["latency_gating"]["passed"]` & console verdict |
| **Zero Forfeits Gate** | Across all tiers, `total_forfeits == 0` | Confirmed by `results_data["summary"]["total_forfeits"] == 0` |
| **Exit Code** | 0 on full pass, 1 on any criterion failure | `echo $?` after run |
