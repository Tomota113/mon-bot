"""Proposed Implementation: Tier 1 Packaging Verification & test_engine.py Suite.

Author: M1 Explorer 3
Working Directory: /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3
"""

# ==============================================================================
# 1. UPGRADED Tier1Verifier._verify_packaging for benchmark_suite.py
# ==============================================================================

def proposed_verify_packaging(self) -> dict:
    """Verify arena pack . CLI execution, zipfile validity, dependencies, and sandbox AST."""
    import ast
    import shutil
    import subprocess
    import sys
    import zipfile
    from pathlib import Path
    from arena_sdk.ipc.sandbox import FORBIDDEN_RUNTIME_IMPORTS
    from arena_sdk.loader import load_submission_zip
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
    if arena_bin:
        cmd = [arena_bin, "pack", "."]
    else:
        cmd = [sys.executable, "-m", "arena_sdk.cli", "pack", "."]

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


# ==============================================================================
# 2. PROPOSED TEST CLASSES FOR test_engine.py
# ==============================================================================

PROPOSED_TEST_ENGINE_ADDITIONS = """
import ast
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from arena_sdk.loader import load_submission_zip
from arena_sdk.pack import WHITELIST_PACKAGES, requirement_package_name
from arena_sdk.ipc.sandbox import FORBIDDEN_RUNTIME_IMPORTS
from arena_sdk import Action, ActionType, PlayerView, YouState, OpponentState, TableState, TurnState, MatchContext
from i151_engine.models.card import Card, Rank, Suit

PROJECT_ROOT = Path(__file__).resolve().parent
SUBMISSION_ZIP = PROJECT_ROOT / "mon-bot-submission.zip"


class TestPackagingVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate clean submission zip via official CLI
        res = subprocess.run(["arena", "pack", "."], cwd=PROJECT_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, f"arena pack failed: {res.stderr}"

    def test_submission_zip_exists(self):
        self.assertTrue(SUBMISSION_ZIP.is_file(), "mon-bot-submission.zip must exist at project root")

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
            for name in zf.namelist():
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
"""
