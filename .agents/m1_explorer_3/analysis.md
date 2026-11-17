# Technical Analysis: Tier 1 Packaging Verification & CLI Regression Test Pipeline

**Author**: M1 Explorer 3  
**Date**: 2026-09-09  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3`  
**Target Files**:
- `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`
- `/home/ibrahim-tomota/mon-bot/test_engine.py`
**Reference Files & Directives**:
- `/home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md`
- `/home/ibrahim-tomota/mon-bot/.agents/orchestrator_2/PROJECT.md`
- `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/spec_report.md`
- Latest Tournament Rules Dispatch (400ms hard timeout, 50MB limit, strict sandbox AST, victory ranking)

---

## 1. Executive Summary

This investigation provides the definitive implementation strategy for **Milestone 1 (M1)** covering:
1. **Automated Packaging Verification in Tier 1 (`benchmark_suite.py`)**:
   - Upgrading `Tier1Verifier._verify_packaging` from an ephemeral in-memory test to a full validation pipeline.
   - Invoking the official CLI command `arena pack .` to generate the real root artifact `mon-bot-submission.zip`.
   - Inspecting the archive with `zipfile.ZipFile` for structural integrity (`testzip() == None`), 50MB size limit, manifest closure (`bot.py` + AST-discovered modules `card_tracker.py`, `evaluator.py`), absence of unauthorized dependencies (`i151-arena-sdk` stripped; only `WHITELIST_PACKAGES` permitted in `requirements.txt`), exclusion of extraneous files (`test_engine.py`, `benchmark_suite.py`, `__pycache__`), and strict sandbox AST auditing (no `eval`, `exec`, `pickle.load`, no `FORBIDDEN_RUNTIME_IMPORTS`).
   - Loading the packaged bot via `load_submission_zip()` and executing a functional test.
2. **CLI Verification Commands & Test Automation Pipeline**:
   - Formalizing the verification workflow for `arena pack .`, `arena test bot.py`, `arena test mon-bot-submission.zip`, `arena match`, and `benchmark_suite.py --tier 1` / `--quick`.
3. **Comprehensive Regression Test Suite in `test_engine.py`**:
   - Adding `TestPackagingVerification`, `TestCLIVerification`, and `TestTournamentInvariantsAndConstraints` (covering the 400ms server timeout / 250ms cutoff, 2P anti-queen finish, `choose_suit` action format, Rank 8 retention, and endgame solver gating).

---

## 2. Current State & Gap Analysis

### 2.1 Current Tier 1 Packaging Check in `benchmark_suite.py`

In `benchmark_suite.py:262-298`, `Tier1Verifier._verify_packaging()` currently executes:
```python
val_err = validate_submission_project(self.challenger_dir, entry="bot.py")
with tempfile.TemporaryDirectory() as tmpdir:
    zip_path = Path(tmpdir) / "test_submission.zip"
    created_zip, entries, removed = build_submission_zip(self.challenger_dir, zip_path, entry="bot.py")
    loaded_bot = load_submission_zip(created_zip)
```

#### Identified Deficiencies:
1. **Does not test the real CLI**: It bypasses the official `arena pack .` CLI command.
2. **Does not verify the actual submission artifact**: The real artifact required by the platform is `mon-bot-submission.zip` in the project root (`/home/ibrahim-tomota/mon-bot/mon-bot-submission.zip`). The current test only generates an ephemeral zip in `/tmp`.
3. **No `zipfile.ZipFile` CRC integrity check**: It never calls `zf.testzip()` to verify archive header and CRC32 checksums.
4. **No size limit enforcement**: Tournament rules permit up to 50 MB; the verifier should enforce `st_size <= 50 * 1024 * 1024` and warn if excessive.
5. **No explicit unauthorized dependency audit**: Does not verify whether `requirements.txt` inside the ZIP contains illegal external libraries.
6. **No sandbox AST security scan**: The latest competition directives mandate strict sandbox compliance: no `eval()`, `exec()`, `pickle.load()`, or imports from `FORBIDDEN_RUNTIME_IMPORTS` (`os`, `sys`, `subprocess`, `socket`, `multiprocessing`, etc.).
7. **No extraneous file guard**: Does not verify that test scripts (`test_engine.py`, `benchmark_suite.py`) and hidden caches (`__pycache__`) are excluded.

### 2.2 Official Packaging Mechanics (`arena_sdk.pack`)

Static analysis of `/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/arena_sdk/pack.py` reveals:
- **Default naming**: `default_output_path(project_dir)` yields `<project_name>-submission.zip`. For `/home/ibrahim-tomota/mon-bot`, the target is `mon-bot-submission.zip`.
- **AST Module Closure**: `collect_local_module_closure(root, entry_path)` parses AST imports from `bot.py` recursively to find all local `.py` dependencies. In `mon-bot`, this resolves `{'bot', 'card_tracker', 'evaluator'}`.
- **Requirements Filtering**: `filter_requirements_text(raw)` only keeps packages in `WHITELIST_PACKAGES = {'numpy', 'scikit-learn', 'sklearn', 'joblib', 'onnxruntime', 'torch', 'pandas'}`. All others (including `i151-arena-sdk`) are stripped. If no whitelisted packages remain, `requirements.txt` is not included in the zip.
- **Forbidden Runtime Imports**: `arena_sdk.ipc.sandbox.FORBIDDEN_RUNTIME_IMPORTS` defines 49 blocked modules (`os`, `subprocess`, `socket`, `pickle`, `ctypes`, etc.).

---

## 3. Tier 1 Packaging Implementation Strategy

### 3.1 Architecture of Upgraded `_verify_packaging`

The upgraded method in `Tier1Verifier` performs a 7-stage verification:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Stage 1: CLI Execution                                                 │
│ Run `arena pack .` via subprocess; assert returncode == 0              │
├────────────────────────────────────────────────────────────────────────┤
│ Stage 2: Artifact Existence & Size Limit Check                         │
│ Locate `mon-bot-submission.zip`; assert size <= 50 MB (52,428,800 B)   │
├────────────────────────────────────────────────────────────────────────┤
│ Stage 3: ZipFile Structure & CRC Check                                 │
│ Open with zipfile.ZipFile; assert zf.testzip() is None                │
├────────────────────────────────────────────────────────────────────────┤
│ Stage 4: Manifest & Module Closure Audit                               │
│ Assert 'bot.py' present; assert local closure ('card_tracker.py',      │
│ 'evaluator.py') present; assert NO test files or __pycache__           │
├────────────────────────────────────────────────────────────────────────┤
│ Stage 5: Dependency Whitelist Enforcement                              │
│ If requirements.txt present: assert all lines in WHITELIST_PACKAGES    │
│ Assert 'i151-arena-sdk' is not present in requirements.txt             │
├────────────────────────────────────────────────────────────────────────┤
│ Stage 6: Strict Sandbox AST Inspection                                 │
│ ast.parse every .py file: assert NO eval, exec, pickle.load, and       │
│ NO FORBIDDEN_RUNTIME_IMPORTS                                           │
├────────────────────────────────────────────────────────────────────────┤
│ Stage 7: Functional Bot Loader & Decision Probe                        │
│ load_submission_zip(zip_path) -> setup() -> decide() -> teardown()     │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Proposed Python Implementation for `Tier1Verifier._verify_packaging`

```python
    def _verify_packaging(self) -> dict[str, Any]:
        """Verify arena pack . CLI execution, zipfile validity, dependencies, and sandbox AST."""
        import ast
        import shutil
        import subprocess
        import zipfile
        from arena_sdk.ipc.sandbox import FORBIDDEN_RUNTIME_IMPORTS
        from arena_sdk.pack import (
            WHITELIST_PACKAGES,
            collect_local_module_closure,
            requirement_package_name,
        )

        root = self.challenger_dir.resolve()
        expected_zip_name = f"{root.name}-submission.zip"
        zip_path = root / expected_zip_name

        # 1. Run official CLI command `arena pack .`
        arena_bin = shutil.which("arena")
        cmd = [arena_bin or sys.executable, "pack" if arena_bin else "-m arena_sdk.cli pack", "."]
        if not arena_bin:
            cmd = [sys.executable, "-m", "arena_sdk.cli", "pack", "."]
        else:
            cmd = [arena_bin, "pack", "."]

        try:
            proc = subprocess.run(
                cmd,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode != 0:
                return {
                    "passed": False,
                    "error": proc.stderr or proc.stdout,
                    "message": f"`arena pack .` failed (exit {proc.returncode}): {proc.stderr.strip()}",
                }
        except Exception as exc:
            return {
                "passed": False,
                "error": str(exc),
                "message": f"Failed to execute `arena pack .`: {exc}",
            }

        # 2. Check artifact existence & size limit (<= 50 MB)
        if not zip_path.is_file():
            return {
                "passed": False,
                "message": f"Artifact {expected_zip_name} was not generated at {root}",
            }

        zip_size_bytes = zip_path.stat().st_size
        max_size_bytes = 50 * 1024 * 1024  # 50 MB
        if zip_size_bytes > max_size_bytes:
            return {
                "passed": False,
                "message": f"ZIP size {zip_size_bytes} exceeds 50MB limit ({max_size_bytes} bytes)",
            }

        # 3. ZipFile structural integrity & CRC verification
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                corrupted = zf.testzip()
                if corrupted is not None:
                    return {
                        "passed": False,
                        "message": f"Corrupted file in ZIP archive: {corrupted}",
                    }
                namelist = zf.namelist()

                # 4. Manifest checks: bot.py and AST module closure
                if "bot.py" not in namelist:
                    return {"passed": False, "message": "bot.py missing from submission archive"}

                entry_path = root / "bot.py"
                closure = collect_local_module_closure(root, entry_path)
                for mod in closure:
                    expected_file = "bot.py" if mod == "bot" else f"{mod}.py"
                    if expected_file not in namelist:
                        return {
                            "passed": False,
                            "message": f"Required module closure file '{expected_file}' missing from archive",
                        }

                # Check forbidden/extraneous files
                forbidden_patterns = ("test_engine", "benchmark_", "__pycache__", ".pyc", ".git", ".agent")
                for item in namelist:
                    if any(fp in item for fp in forbidden_patterns):
                        return {
                            "passed": False,
                            "message": f"Extraneous/forbidden item packaged in ZIP: {item}",
                        }

                # 5. Dependency whitelist check
                if "requirements.txt" in namelist:
                    req_content = zf.read("requirements.txt").decode("utf-8")
                    for line in req_content.splitlines():
                        pkg = requirement_package_name(line)
                        if pkg and pkg not in WHITELIST_PACKAGES:
                            return {
                                "passed": False,
                                "message": f"Unauthorized dependency in packaged requirements.txt: {pkg}",
                            }

                # 6. Strict sandbox AST inspection
                for arcname in namelist:
                    if arcname.endswith(".py"):
                        source_code = zf.read(arcname).decode("utf-8")
                        tree = ast.parse(source_code, filename=arcname)
                        for node in ast.walk(tree):
                            # Forbidden calls: eval, exec, pickle.load
                            if isinstance(node, ast.Call):
                                if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                                    return {
                                        "passed": False,
                                        "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden call '{node.func.id}()'",
                                    }
                                if isinstance(node.func, ast.Attribute) and node.func.attr in ("load", "loads"):
                                    if isinstance(node.func.value, ast.Name) and "pickle" in node.func.value.id:
                                        return {
                                            "passed": False,
                                            "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden pickle loading",
                                        }
                            # Forbidden imports
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    mod_root = alias.name.split(".")[0]
                                    if mod_root in FORBIDDEN_RUNTIME_IMPORTS:
                                        return {
                                            "passed": False,
                                            "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden import '{mod_root}'",
                                        }
                            if isinstance(node, ast.ImportFrom) and node.module:
                                mod_root = node.module.split(".")[0]
                                if mod_root in FORBIDDEN_RUNTIME_IMPORTS:
                                    return {
                                        "passed": False,
                                        "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden import from '{mod_root}'",
                                    }

            # 7. Functional load verification using load_submission_zip
            loaded_bot = load_submission_zip(zip_path)
            if loaded_bot is None:
                return {"passed": False, "message": "load_submission_zip returned None"}

            return {
                "passed": True,
                "zip_path": str(zip_path),
                "size_bytes": zip_size_bytes,
                "entries": namelist,
                "message": f"Valid submission ZIP ({zip_size_bytes / 1024:.1f} KB, {len(namelist)} files, AST closure & sandbox compliant)",
            }
        except Exception as exc:
            return {
                "passed": False,
                "error": str(exc),
                "message": f"Packaging verification exception: {exc}",
            }
```

---

## 4. CLI Verification Commands Inventory

| Command | Purpose | Input / Target | Expected Return Code | Expected Output Signature | Timeout Budget |
|---|---|---|:---:|---|---|
| `arena pack .` | Generates official submission archive | Project root (`/home/ibrahim-tomota/mon-bot`) | 0 | `ZIP créé : .../mon-bot-submission.zip`, list of packaged files, stripped deps | 15s |
| `arena test bot.py` | Official smoke test vs `builtin:random` | Entrypoint `bot.py` | 0 | `OK — match terminé sans forfait` | 30s |
| `arena test mon-bot-submission.zip` | Isolated submission smoke test | Packaged archive `mon-bot-submission.zip` | 0 | `OK — match terminé sans forfait` | 30s |
| `arena match bot.py --vs medium --games 20 --format summary` | Standard match runner probe | `bot.py` vs `builtin:medium` | 0 | Summary table with games, scores, win rate, 0 forfeits | 120s |
| `python3 benchmark_suite.py --tier 1` | Tier 1 invariant & packaging suite | `bot.py` (all 5 Tier 1 checks) | 0 | `5/5 Checks Passed (100.0%)`, `GRAND_MASTER_READY` | 20s |
| `python3 benchmark_suite.py --quick` | 5-game smoke across all 4 tiers | Full benchmark suite | 0 | Full report across Tiers 1-4 | 45s |
| `python3 -m unittest test_engine.py` | Fast unit & regression test suite | Unit test suite | 0 | `Ran X tests in ...s`, `OK` | 5s |

---

## 5. Regression Test Suite Strategy in `test_engine.py`

### 5.1 Test Classes to Add

We recommend adding three targeted test classes to `test_engine.py`:

#### 1. `TestPackagingVerification`
- `test_arena_pack_creates_submission_zip`: Runs `arena pack .`, asserts returncode 0, asserts `mon-bot-submission.zip` exists.
- `test_zipfile_integrity_and_crc`: Opens archive, verifies `testzip() is None`.
- `test_submission_size_under_50mb`: Asserts `st_size <= 50 * 1024 * 1024` (and `< 50 KB`).
- `test_mandatory_files_and_closure`: Asserts `bot.py`, `card_tracker.py`, and `evaluator.py` are all present.
- `test_no_extraneous_files`: Asserts `test_engine.py`, `benchmark_suite.py`, `.git`, `.agents`, `__pycache__` are absent.
- `test_unauthorized_dependencies_excluded`: Asserts `requirements.txt` only contains whitelisted packages and `i151-arena-sdk` was stripped.
- `test_sandbox_ast_compliance`: Asserts 0 `eval`, `exec`, `pickle.load`, or `FORBIDDEN_RUNTIME_IMPORTS`.
- `test_zip_loader_and_decision_probe`: Loads bot from zip, runs `decide()` on synthetic view, verifies returned action.

#### 2. `TestCLIVerification`
- `test_cli_arena_test_bot_py`: Subprocess `arena test bot.py`, asserts `returncode == 0` and `"OK"` in output.
- `test_cli_arena_test_submission_zip`: Subprocess `arena test mon-bot-submission.zip`, asserts `returncode == 0` and `"OK"`.
- `test_cli_benchmark_tier1`: Subprocess `python3 benchmark_suite.py --tier 1`, asserts `returncode == 0` and `"OVERALL VERDICT: GRAND_MASTER_READY"`.

#### 3. `TestTournamentInvariantsAndConstraints`
- `test_decision_latency_under_cutoff`: Runs 20 `decide()` calls on complex mid-game states; asserts average latency < 50ms and max latency < 250ms (guaranteeing zero timeouts against the 400ms hard server timeout).
- `test_anti_queen_2p_invariant`: Asserts `Action.draw_card()` is chosen over `Action.play_card(Queen)` when hand size == 1.
- `test_choose_suit_action_structure`: Asserts `Action.choose_suit` is returned when `table.must_choose_suit == True`.
- `test_rank_8_retention_hand_gte_5`: Asserts rank 8 wildcard is preserved when hand size >= 5 and valid alternative plays exist.
- `test_exact_endgame_solver_gating`: Asserts `solve_exact_endgame` is only triggered when `unrevealed_mask.bit_count() <= 6 AND bank_size == 0`.

### 5.2 Proposed Code for `test_engine.py`

```python
import ast
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from arena_sdk.loader import load_submission_zip
from arena_sdk.pack import WHITELIST_PACKAGES, requirement_package_name
from arena_sdk.ipc.sandbox import FORBIDDEN_RUNTIME_IMPORTS

PROJECT_ROOT = Path(__file__).resolve().parent
SUBMISSION_ZIP = PROJECT_ROOT / "mon-bot-submission.zip"


class TestPackagingVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure fresh package exists
        res = subprocess.run(["arena", "pack", "."], cwd=PROJECT_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, f"arena pack failed: {res.stderr}"

    def test_submission_zip_exists(self):
        self.assertTrue(SUBMISSION_ZIP.is_file(), "mon-bot-submission.zip must exist at root")

    def test_zip_integrity_crc(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            self.assertIsNone(zf.testzip(), "ZIP archive contains corrupted files")

    def test_submission_size_under_50mb(self):
        size = SUBMISSION_ZIP.stat().st_size
        self.assertLessEqual(size, 50 * 1024 * 1024, "Archive exceeds 50MB tournament limit")
        self.assertLessEqual(size, 100 * 1024, "Archive unexpectedly large for code-only bot")

    def test_manifest_contains_closure(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            names = set(zf.namelist())
            self.assertIn("bot.py", names)
            self.assertIn("card_tracker.py", names)
            self.assertIn("evaluator.py", names)

    def test_manifest_excludes_extraneous(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            names = zf.namelist()
            for name in names:
                self.assertNotIn("test_engine", name)
                self.assertNotIn("benchmark_", name)
                self.assertNotIn("__pycache__", name)
                self.assertFalse(name.endswith((".pyc", ".pyo")))
                self.assertFalse(name.startswith((".git", ".agent")))

    def test_unauthorized_dependencies_excluded(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            if "requirements.txt" in zf.namelist():
                content = zf.read("requirements.txt").decode("utf-8")
                for line in content.splitlines():
                    pkg = requirement_package_name(line)
                    if pkg:
                        self.assertIn(pkg, WHITELIST_PACKAGES)
                        self.assertNotEqual(pkg, "i151-arena-sdk")

    def test_sandbox_ast_compliance(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".py"):
                    tree = ast.parse(zf.read(name).decode("utf-8"), filename=name)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                                self.fail(f"Forbidden call {node.func.id} in {name}:{node.lineno}")
                        if isinstance(node, ast.Import):
                            for a in node.names:
                                self.assertNotIn(a.name.split(".")[0], FORBIDDEN_RUNTIME_IMPORTS)
                        if isinstance(node, ast.ImportFrom) and node.module:
                            self.assertNotIn(node.module.split(".")[0], FORBIDDEN_RUNTIME_IMPORTS)

    def test_load_submission_zip_and_decide(self):
        bot = load_submission_zip(SUBMISSION_ZIP)
        self.assertIsNotNone(bot)
        bot.setup(PROJECT_ROOT)
        c = Card(Rank.SEVEN, Suit.SPADES)
        you = YouState("p0", (c,), 1, 7, 0, False, False, False, 0)
        table = TableState((c,), (c,), False, None, False, False, 10, 2, 1)
        turn = TurnState(True, True, False, 1, 0, "p0", "p1", False)
        match = MatchContext(1, 151, False, 2, 2, ("p0", "p1"))
        opp = OpponentState("p1", 1, "random", "RandomBot", None, 5, 0, False, 0, 1, True)
        view = PlayerView(you, (opp,), table, turn, match)
        actions = [Action.play_card(c), Action.draw_card()]
        action = bot.decide(view, actions, 400)
        self.assertIn(action, actions)
        bot.teardown()


class TestCLIVerification(unittest.TestCase):
    def test_arena_test_bot_py(self):
        res = subprocess.run(["arena", "test", "bot.py"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"arena test bot.py failed: {res.stderr}")
        self.assertIn("OK", res.stdout)

    def test_arena_test_mon_bot_submission_zip(self):
        res = subprocess.run(["arena", "test", "mon-bot-submission.zip"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"arena test mon-bot-submission.zip failed: {res.stderr}")
        self.assertIn("OK", res.stdout)

    def test_benchmark_suite_tier1_cli(self):
        res = subprocess.run([sys.executable, "benchmark_suite.py", "--tier", "1"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"benchmark_suite --tier 1 failed: {res.stderr}")
        self.assertIn("GRAND_MASTER_READY", res.stdout)
```

---

## 6. Synthesis & Inter-Agent Coordination

- **Integration with M1 Explorer 1**: Explorer 1 is restructuring `BenchmarkRunner.run_series` for symmetric slot inversion (`25 p0 / 25 p1`). The packaging check in `Tier1Verifier` operates independently of slot assignments, but guarantees that the bot being tested is identical to the one packaged for production.
- **Integration with M1 Explorer 2**: Explorer 2 is enforcing strict latency gating (< 50ms average, < 300ms peak, 0 timeouts) and win rate thresholds. Our packaging verification complements this by ensuring sandbox safety and valid submission generation.
- **Support for Engine Workers (M2–M4)**: The AST sandbox inspection and module closure check ensure that any new files or modules introduced in M2 (resource preservation), M3 (deep minimax), or M4 (Bayesian void tracking) are automatically tracked by AST closure and audited for compliance without breaking packaging.
