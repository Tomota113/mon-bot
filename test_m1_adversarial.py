"""Adversarial and Stress Test Harness for Milestone M1 Verification.

Empirically challenges:
1. Latency gating failure modes (mean >= 50ms, max >= 300ms, slow moves, decision & match timeouts).
2. Packaging verification failure modes (corrupted ZIP, oversized ZIP, missing closure, forbidden AST, forbidden imports, forbidden paths).
"""

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock as mock
import zipfile
from pathlib import Path

from arena_sdk.ipc.sandbox import FORBIDDEN_RUNTIME_IMPORTS
from arena_sdk.pack import WHITELIST_PACKAGES, requirement_package_name
from benchmark_suite import (
    BenchmarkRunner,
    LatencyProfile,
    Tier1Verifier,
    run_benchmark,
)

PROJECT_ROOT = Path(__file__).resolve().parent
SUBMISSION_ZIP = PROJECT_ROOT / "mon-bot-submission.zip"


class TestLatencyGatingFailureModes(unittest.TestCase):
    """Stress-tests the latency gating predicates and overall_passed computation."""

    @staticmethod
    def _evaluate_gating(
        lat_stats: dict,
        match_timeouts: int = 0,
        total_forfeits: int = 0,
        run_tier: bool = True,
        t_passed: bool = True,
    ) -> tuple[bool, bool]:
        decision_timeouts = lat_stats.get("timeouts_gt_1000ms", 0)
        slow_moves_300 = lat_stats.get("slow_moves_gt_300ms", 0)
        total_timeouts = match_timeouts + decision_timeouts

        latency_passed = (
            lat_stats["count"] > 0
            and lat_stats["mean"] < 50.0
            and lat_stats["max"] < 300.0
            and decision_timeouts == 0
            and slow_moves_300 == 0
        ) if run_tier else True

        overall_passed = (
            t_passed
            and latency_passed
            and (total_forfeits == 0)
            and (total_timeouts == 0)
        )
        return latency_passed, overall_passed

    def test_latency_mean_boundary_fails_gating(self):
        """A mean latency of exactly 50.0 ms must fail gating (< 50.0 is strict)."""
        p = LatencyProfile()
        p.record(50.0)
        p.record(50.0)
        stats = p.compute_stats()
        self.assertEqual(stats["mean"], 50.0)
        lp, op = self._evaluate_gating(stats)
        self.assertFalse(lp, "Mean == 50.0ms must fail latency gating")
        self.assertFalse(op, "Mean == 50.0ms must fail overall_passed")

    def test_latency_mean_exceeded_fails_gating(self):
        """A mean latency above 50.0 ms (e.g. 58.5 ms) must fail gating."""
        p = LatencyProfile()
        p.record(55.0)
        p.record(62.0)
        stats = p.compute_stats()
        self.assertGreater(stats["mean"], 50.0)
        lp, op = self._evaluate_gating(stats)
        self.assertFalse(lp, "Mean > 50.0ms must fail latency gating")
        self.assertFalse(op, "Mean > 50.0ms must fail overall_passed")

    def test_latency_max_boundary_fails_gating(self):
        """A max latency of exactly 300.0 ms must fail gating (< 300.0 is strict)."""
        p = LatencyProfile()
        p.record(10.0)
        p.record(300.0)
        stats = p.compute_stats()
        self.assertEqual(stats["max"], 300.0)
        lp, op = self._evaluate_gating(stats)
        self.assertFalse(lp, "Max == 300.0ms must fail latency gating")
        self.assertFalse(op, "Max == 300.0ms must fail overall_passed")

    def test_latency_max_exceeded_fails_gating(self):
        """A max latency > 300.0 ms must fail gating."""
        p = LatencyProfile()
        p.record(10.0)
        p.record(315.0)
        stats = p.compute_stats()
        self.assertGreater(stats["max"], 300.0)
        self.assertGreaterEqual(stats["slow_moves_gt_300ms"], 1)
        lp, op = self._evaluate_gating(stats)
        self.assertFalse(lp, "Max > 300.0ms must fail latency gating")
        self.assertFalse(op, "Max > 300.0ms must fail overall_passed")

    def test_latency_decision_timeout_fails_gating(self):
        """A decision exceeding 1000.0 ms must fail both latency and timeout gating."""
        p = LatencyProfile()
        p.record(10.0)
        p.record(1050.0)
        stats = p.compute_stats()
        self.assertGreaterEqual(stats["timeouts_gt_1000ms"], 1)
        lp, op = self._evaluate_gating(stats)
        self.assertFalse(lp, "Decision timeout must fail latency gating")
        self.assertFalse(op, "Decision timeout must fail overall_passed")

    def test_latency_server_timeout_400ms_fails_gating(self):
        """A decision move of 450 ms exceeds 300ms threshold and must fail gating."""
        p = LatencyProfile()
        p.record(10.0)
        p.record(450.0)
        stats = p.compute_stats()
        self.assertGreaterEqual(stats["timeouts_gt_400ms"], 1)
        self.assertGreaterEqual(stats["slow_moves_gt_300ms"], 1)
        lp, op = self._evaluate_gating(stats)
        self.assertFalse(lp, "Move > 400ms must fail latency gating")
        self.assertFalse(op, "Move > 400ms must fail overall_passed")

    def test_match_timeout_fails_overall(self):
        """Even if per-move latency passed, a match timeout must fail overall_passed."""
        p = LatencyProfile()
        for x in [10.0, 15.0, 20.0]:
            p.record(x)
        stats = p.compute_stats()
        lp, op = self._evaluate_gating(stats, match_timeouts=1)
        self.assertTrue(lp, "Move latency was fast")
        self.assertFalse(op, "Match timeout must fail overall_passed")

    def test_match_forfeit_fails_overall(self):
        """Even if latency passed, a forfeit must fail overall_passed."""
        p = LatencyProfile()
        p.record(15.0)
        stats = p.compute_stats()
        lp, op = self._evaluate_gating(stats, total_forfeits=1)
        self.assertTrue(lp, "Move latency was fast")
        self.assertFalse(op, "Forfeit must fail overall_passed")

    def test_compliant_profile_passes(self):
        """A profile meeting all criteria (< 50ms mean, < 300ms max, 0 timeouts/forfeits) passes."""
        p = LatencyProfile()
        for x in [5.0, 12.0, 25.0, 35.0, 8.0]:
            p.record(x)
        stats = p.compute_stats()
        lp, op = self._evaluate_gating(stats)
        self.assertTrue(lp)
        self.assertTrue(op)

    def test_e2e_run_benchmark_gating_integration(self):
        """Empirically invokes run_benchmark with injected latency violation and asserts exit code 1."""
        def make_mock_res(win_rate_pct=100.0, forfeits=0, reason="normal"):
            return {
                "opponent_spec": "medium",
                "opponent_name": "medium_bot",
                "games": 2,
                "wins": 2 if win_rate_pct == 100.0 else 0,
                "losses": 0 if win_rate_pct == 100.0 else 2,
                "draws": 0,
                "forfeits": forfeits,
                "win_rate": win_rate_pct / 100.0,
                "win_rate_pct": win_rate_pct,
                "symmetric": True,
                "p0_games": 1,
                "p0_wins": 1 if win_rate_pct == 100.0 else 0,
                "p0_win_rate_pct": win_rate_pct,
                "p1_games": 1,
                "p1_wins": 1 if win_rate_pct == 100.0 else 0,
                "p1_win_rate_pct": win_rate_pct,
                "starter_me_games": 1,
                "starter_me_wins": 1 if win_rate_pct == 100.0 else 0,
                "starter_me_win_rate_pct": win_rate_pct,
                "starter_opp_games": 1,
                "starter_opp_wins": 1 if win_rate_pct == 100.0 else 0,
                "starter_opp_win_rate_pct": win_rate_pct,
                "matches": [{"reason": reason, "won": (win_rate_pct == 100.0), "my_slot": "p0", "starter_bot": "mon-bot"}],
            }

        # Case 1: Injected slow mean (55ms)
        with mock.patch.object(BenchmarkRunner, "run_series", return_value=make_mock_res()):
            with mock.patch.object(BenchmarkRunner, "__init__", lambda self, *args, **kwargs: None):
                runner = BenchmarkRunner()
                runner.challenger_dir = PROJECT_ROOT
                runner.latency_profile = LatencyProfile()
                for _ in range(5):
                    runner.latency_profile.record(55.0)
                with mock.patch("benchmark_suite.BenchmarkRunner", return_value=runner):
                    code = run_benchmark(bot_path_str="bot.py", tier_choice="3", games=2, verbose=False)
                    self.assertEqual(code, 1, "run_benchmark must exit 1 on latency mean violation")

        # Case 2: Injected max spike (320ms)
        with mock.patch.object(BenchmarkRunner, "run_series", return_value=make_mock_res()):
            with mock.patch.object(BenchmarkRunner, "__init__", lambda self, *args, **kwargs: None):
                runner = BenchmarkRunner()
                runner.challenger_dir = PROJECT_ROOT
                runner.latency_profile = LatencyProfile()
                runner.latency_profile.record(10.0)
                runner.latency_profile.record(320.0)
                with mock.patch("benchmark_suite.BenchmarkRunner", return_value=runner):
                    code = run_benchmark(bot_path_str="bot.py", tier_choice="3", games=2, verbose=False)
                    self.assertEqual(code, 1, "run_benchmark must exit 1 on latency max violation")


class TestPackagingVerificationFailureModes(unittest.TestCase):
    """Stress-tests Tier1 packaging verifier failure modes against malformed artifacts."""

    def test_missing_zip_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "bot.py").write_text("def setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n")
            verifier = Tier1Verifier(p / "bot.py", p)
            # Mock arena pack to do nothing, leaving no zip file
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("was not generated", res["message"])

    def test_corrupted_zip_bytes_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            zip_p = p / f"{p.name}-submission.zip"
            zip_p.write_bytes(b"INVALID_HEADER_GARBAGE_NOT_A_ZIP")
            (p / "bot.py").write_text("def setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n")
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("File is not a zip file", res["message"])

    def test_crc_corrupted_member_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", "def setup(d): pass\n")
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                with mock.patch.object(zipfile.ZipFile, "testzip", return_value="bot.py"):
                    res = verifier._verify_packaging()
                    self.assertFalse(res["passed"])
                    self.assertIn("Corrupted file in ZIP archive", res["message"])

    def test_oversized_zip_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            zip_p = p / f"{p.name}-submission.zip"
            zip_p.write_bytes(b"0")
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                with mock.patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value.st_size = 51 * 1024 * 1024
                    res = verifier._verify_packaging()
                    self.assertFalse(res["passed"])
                    self.assertIn("exceeds 50MB limit", res["message"])

    def test_missing_entry_point_bot_py_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("evaluator.py", "# no bot.py\n")
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("bot.py missing from submission archive", res["message"])

    def test_missing_closure_file_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "bot.py").write_text("import card_tracker\ndef setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n")
            (p / "card_tracker.py").write_text("# tracker\n")
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", (p / "bot.py").read_text())
                # card_tracker.py omitted intentionally from ZIP
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("missing from archive", res["message"])

    def test_extraneous_forbidden_file_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "bot.py").write_text("def setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n")
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", (p / "bot.py").read_text())
                zf.writestr("test_engine.py", "# extraneous file\n")
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("Extraneous/forbidden item", res["message"])

    def test_unauthorized_dependency_in_requirements_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "bot.py").write_text("def setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n")
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", (p / "bot.py").read_text())
                zf.writestr("requirements.txt", "requests==2.31.0\n")
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("Unauthorized dependency in packaged requirements.txt: requests", res["message"])

    def test_forbidden_import_socket_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            code = "import socket\ndef setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n"
            (p / "bot.py").write_text(code)
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", code)
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("forbidden import 'socket'", res["message"])

    def test_forbidden_import_from_os_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            code = "from os import environ\ndef setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n"
            (p / "bot.py").write_text(code)
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", code)
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("forbidden import from 'os'", res["message"])

    def test_forbidden_eval_call_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            code = "def setup(d): pass\ndef decide(v,l,t): eval('1'); return l[0]\ndef teardown(): pass\n"
            (p / "bot.py").write_text(code)
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", code)
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("forbidden call 'eval()'", res["message"])

    def test_forbidden_exec_call_fails_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            code = "def setup(d): pass\ndef decide(v,l,t): exec('pass'); return l[0]\ndef teardown(): pass\n"
            (p / "bot.py").write_text(code)
            zip_p = p / f"{p.name}-submission.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr("bot.py", code)
            verifier = Tier1Verifier(p / "bot.py", p)
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                res = verifier._verify_packaging()
                self.assertFalse(res["passed"])
                self.assertIn("forbidden call 'exec()'", res["message"])

    def test_forbidden_path_literals_fail_verification(self):
        for bad_path in ("/dev/shm/table.bin", "/etc/passwd", "/proc/meminfo"):
            with tempfile.TemporaryDirectory() as td:
                p = Path(td)
                code = f"PATH = '{bad_path}'\ndef setup(d): pass\ndef decide(v,l,t): return l[0]\ndef teardown(): pass\n"
                (p / "bot.py").write_text(code)
                zip_p = p / f"{p.name}-submission.zip"
                with zipfile.ZipFile(zip_p, "w") as zf:
                    zf.writestr("bot.py", code)
                verifier = Tier1Verifier(p / "bot.py", p)
                with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")):
                    res = verifier._verify_packaging()
                    self.assertFalse(res["passed"])
                    self.assertIn("reading outside submission_dir", res["message"])

    def test_production_submission_passes_packaging_verification(self):
        """Verifies that the actual project mon-bot passes packaging verification cleanly."""
        verifier = Tier1Verifier(PROJECT_ROOT / "bot.py", PROJECT_ROOT)
        res = verifier._verify_packaging()
        self.assertTrue(res["passed"], f"Production packaging verification failed: {res}")


if __name__ == "__main__":
    unittest.main()
