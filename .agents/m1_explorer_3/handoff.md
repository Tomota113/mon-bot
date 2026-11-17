# Handoff Report: Tier 1 Packaging Verification & CLI Regression Test Pipeline

**Milestone**: M1 (Symmetric Benchmark Suite R4)  
**Agent**: M1 Explorer 3  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3`  
**Target Files**:
- `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`
- `/home/ibrahim-tomota/mon-bot/test_engine.py`

---

## 1. Observation

1. **Current `Tier1Verifier._verify_packaging` in `benchmark_suite.py` (lines 262–298)**:
   - Uses SDK Python functions `validate_submission_project(self.challenger_dir, entry="bot.py")` and `build_submission_zip(self.challenger_dir, zip_path, entry="bot.py")` creating a temporary file in `tempfile.TemporaryDirectory()`.
   - Never calls the platform CLI command `arena pack .`.
   - Does not verify that `/home/ibrahim-tomota/mon-bot/mon-bot-submission.zip` is created at the repository root.
   - Does not verify archive CRC integrity with `zipfile.ZipFile.testzip()`.
   - Does not verify the tournament limit of 50 MB (`st_size <= 50 * 1024 * 1024`).
   - Does not verify AST sandbox constraints (forbidden calls `eval`, `exec`, `pickle.load` or imports in `FORBIDDEN_RUNTIME_IMPORTS`).
   - Does not check for forbidden extraneous files (`test_engine.py`, `benchmark_suite.py`, `__pycache__`).

2. **Official CLI Behavior (`arena pack .`)**:
   - Running `arena pack .` in `/home/ibrahim-tomota/mon-bot`:
     ```
     ZIP créé : /home/ibrahim-tomota/mon-bot/mon-bot-submission.zip
       3 fichier(s) : bot.py, card_tracker.py, evaluator.py
       requirements.txt nettoyé — retiré : i151-arena-sdk

     Prochaine étape : uploadez ce ZIP sur le dashboard arène.
     ```
     Exit code: `0`.
   - Resulting ZIP file: `/home/ibrahim-tomota/mon-bot/mon-bot-submission.zip`, size: `11,049 bytes` (well within the 50 MB limit).
   - Contents inspected via `zipfile.ZipFile('mon-bot-submission.zip', 'r').namelist()`:
     `['bot.py', 'card_tracker.py', 'evaluator.py']`.

3. **Official CLI Smoke Test (`arena test`)**:
   - Running `arena test bot.py`:
     ```
     OK — match terminé sans forfait
     ```
     Exit code: `0`.
   - Running `arena test mon-bot-submission.zip`:
     ```
     OK — match terminé sans forfait
     ```
     Exit code: `0`.

4. **SDK Packaging Rules (`arena_sdk.pack` & `arena_sdk.ipc.sandbox`)**:
   - `arena_sdk/pack.py:14-24`: `WHITELIST_PACKAGES = frozenset({'numpy', 'scikit-learn', 'sklearn', 'joblib', 'onnxruntime', 'torch', 'pandas'})`.
   - `arena_sdk/pack.py:221-229`: `collect_local_module_closure(root, entry_path)` dynamically computes transitive imports from `bot.py`.
   - `arena_sdk/pack.py:344-364`: `filter_requirements_text` strips non-whitelisted dependencies like `i151-arena-sdk`.
   - `arena_sdk/ipc.sandbox:16-68`: `FORBIDDEN_RUNTIME_IMPORTS` blocks 49 modules including `os`, `sys`, `subprocess`, `socket`, `pickle`, `ctypes`, etc.

5. **Existing `test_engine.py` Coverage**:
   - Contains 12 unit tests across `TestBitboardEngine`, `TestZobristHashing`, `TestExactEndgameSolver`, `TestSuitStarvation`, and `TestCardTracker`.
   - Completely lacks tests for:
     - Packaging verification (`arena pack .`, zip structure, AST closure, dependency stripping).
     - CLI command verification (`arena test bot.py`, `arena test mon-bot-submission.zip`, `benchmark_suite.py --tier 1`).
     - Tournament invariants under the new tournament regulations (400ms hard server timeout, 250ms cutoff, 2P anti-queen finish, rank 8 preservation, endgame solver activation constraints).

---

## 2. Logic Chain

1. **From Observation 1 & 2**: The current Tier 1 packaging check in `benchmark_suite.py` only builds an ephemeral ZIP in `/tmp` and does not test the real user command `arena pack .` nor verify the resulting artifact `mon-bot-submission.zip`. Therefore, a broken packaging setup in the project root would pass Tier 1 silently.
2. **From Observation 2 & 4**: `arena pack .` relies on AST closure from `bot.py` and strips non-whitelisted requirements. For `mon-bot`, the closure consists of `bot.py`, `card_tracker.py`, and `evaluator.py`. `requirements.txt` contains `i151-arena-sdk`, which is correctly stripped.
3. **From Observation 4 & Tournament Regulations**: Official tournament constraints forbid `eval()`, `exec()`, `pickle.load()`, and `FORBIDDEN_RUNTIME_IMPORTS`, and limit submission archives to 50 MB. To prevent disqualification, Tier 1 and unit regression tests must verify these rules on the generated ZIP.
4. **From Observation 3**: Both `arena test bot.py` and `arena test mon-bot-submission.zip` run successfully via CLI. Verifying both in automated tests ensures end-to-end sandbox execution parity.
5. **From Observation 5**: `test_engine.py` is fast (< 0.01s for existing tests) and ideal for regression gating. Adding `TestPackagingVerification`, `TestCLIVerification`, and `TestTournamentInvariantsAndConstraints` will catch packaging breaks, illegal imports, and timeout violations prior to running lengthy tournament benchmarks.

---

## 3. Caveats

1. **Subprocess Performance**: Running `arena pack .` and `arena test` inside `test_engine.py` spawns subprocesses that add ~0.5s to test execution time. This remains well within acceptable fast test limits (< 2 seconds total).
2. **Path Dependency**: Subprocess calls require `arena` to be in `PATH` (or use `sys.executable -m arena_sdk.cli`). The implementation should gracefully use `shutil.which("arena")` with a fallback to `sys.executable -m arena_sdk.cli`.
3. **M1 Sibling Coordination**: Implementation of changes to `benchmark_suite.py` should be applied alongside M1 Explorer 1 (symmetric pairing) and M1 Explorer 2 (threshold alignment & latency gating) by the orchestrator/implementer.

---

## 4. Conclusion

1. **`benchmark_suite.py` (Tier 1)**: Upgrade `Tier1Verifier._verify_packaging()` to:
   - Execute `arena pack .` via subprocess.
   - Check `mon-bot-submission.zip` existence and size limit (<= 50 MB).
   - Inspect archive with `zipfile.ZipFile`: call `testzip()`, assert presence of `bot.py` and AST module closure (`card_tracker.py`, `evaluator.py`).
   - Audit dependencies: ensure only `WHITELIST_PACKAGES` in `requirements.txt` and `i151-arena-sdk` is stripped.
   - Enforce sandbox AST security: assert 0 calls to `eval`, `exec`, `pickle.load` and 0 imports of `FORBIDDEN_RUNTIME_IMPORTS`.
   - Functionally load via `load_submission_zip()`.
2. **`test_engine.py`**: Add `TestPackagingVerification`, `TestCLIVerification`, and `TestTournamentInvariantsAndConstraints` as fully drafted in `analysis.md`.

---

## 5. Verification Method

To verify these findings and the proposed implementation:

1. **Inspect current packaging artifact and CLI execution**:
   ```bash
   cd /home/ibrahim-tomota/mon-bot
   arena pack .
   python3 -c "import zipfile; zf = zipfile.ZipFile('mon-bot-submission.zip'); print(zf.namelist()); assert zf.testzip() is None"
   arena test bot.py
   arena test mon-bot-submission.zip
   ```
   *Expected*: Exit code 0, `['bot.py', 'card_tracker.py', 'evaluator.py']` in zip, "OK — match terminé sans forfait".

2. **Verify Tier 1 Benchmark Suite**:
   ```bash
   cd /home/ibrahim-tomota/mon-bot
   python3 benchmark_suite.py --tier 1
   ```
   *Expected*: Exit code 0, 5/5 checks passed.

3. **Verify Existing and New Unit Tests**:
   ```bash
   cd /home/ibrahim-tomota/mon-bot
   python3 -m unittest test_engine.py
   ```
   *Expected*: All tests pass with exit code 0.

4. **Invalidation Conditions**:
   - `arena pack .` fails to generate `mon-bot-submission.zip`.
   - `mon-bot-submission.zip` exceeds 50 MB or fails `testzip()`.
   - `requirements.txt` inside the ZIP retains `i151-arena-sdk` or contains non-whitelisted packages.
   - Packaged files contain `eval`, `exec`, or `FORBIDDEN_RUNTIME_IMPORTS`.
