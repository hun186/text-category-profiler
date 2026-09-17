# Full-Pipeline Smoke Test Implementation Plan v1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the successful manual `python TCFMain.py -p 8059 -ts y` experience into a reproducible, isolated, automatable root-level smoke test that exercises the real child entrypoints and provides the evidence needed to resolve `KI-003` after a real-model acceptance run.

**Architecture:** Add two test-only smoke profiles. Layer A starts the real `TCFMain.py` process and real Stage 1–4 entrypoints, but places a PATH-level `python` dispatcher in front of child commands so only `BertScript/TextClassification_transformers.py` is replaced by a deterministic SQLite-backed smoke classifier. Layer B reuses the same harness without interception, creates a temporary writable model facade around the external real model, and runs the production classifier while keeping WorkPool and other mutable state isolated.

**Tech Stack:** Python `unittest`, `subprocess`, `tempfile`, `sqlite3`, `pathlib`, POSIX process groups, Windows process groups/junctions, existing legacy CLI/stage scripts.

**Spec:** `docs/superpowers/specs/2026-09-17-full-pipeline-smoke-design-v1.md`

**Repository:** `hun186/text-category-profiler`

**Authoritative source baseline:** `98d8a9bc7b4492e7de6355a77b0cbfebe2fea57a`

**Approved design commit:** `821d8574f5e2b5220b2649966e8a4775d2f790ec`

## Global Constraints

- Do not add a production `--smoke` option, production `SMOKE_MODE`, or production environment branch merely for tests.
- Layer A must execute the real root process plus the real `DatasetConverter/DataConverter.py`, `BertScript/RunClassfier.py`, `BertScript/CombineTestResult.py`, and `BertScript/Test_result_Vis.py` child entrypoints.
- Layer A may substitute only the `BertScript/TextClassification_transformers.py` inference child.
- Layer B must install no classifier interception shim.
- Both layers must use a temporary WorkPool and `-TRVHost False`.
- Layer A uses `-nProc 1 -nProcSPC 1 -RMBertData False -p 18059 -exectime 20990101000000`.
- Layer A actual subprocess execution is opt-in through `TCP_RUN_FULL_PIPELINE_SMOKE=1`; normal discovery must report an explicit skip.
- Layer B actual execution is opt-in through `TCP_RUN_REAL_PIPELINE_SMOKE=1` and requires explicit external model, FixedTest, and taxonomy inputs.
- Do not auto-discover or use a developer's production FixedTest/model path in Layer A.
- Do not bypass the root's existing double visualization invocation. If that path fails, treat it as a real integration regression and add a focused RED before the smallest production correction.
- `KI-003` remains Open in the implementation PR until reviewed/merged Layer A plus a post-merge real-model Layer B PASS provide the spec's acceptance evidence.
- `KI-002` remains Open unless separate work proves isolated root-level WeiTech acquisition and processed-delivery lifecycle behavior.
- The canonical compile gate remains `python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler` and must stay green.

---

## File Structure

Create the following focused test infrastructure:

```text
tests/smoke/__init__.py
    Package marker only.

tests/smoke/full_pipeline_harness.py
    Runtime-root creation, command construction, isolation environment,
    wrapper generation, subprocess-tree lifecycle, artifact discovery,
    model-facade construction, and structured smoke result.

tests/smoke/python_dispatch.py
    PATH-level child dispatcher. Forwards every normal child to the real
    interpreter and intercepts only TextClassification_transformers.py.

tests/smoke/smoke_classifier.py
    Deterministic test-only classifier: reads real generated test.sql3 and
    writes canonical test_results.tsv.

tests/test_full_pipeline_harness.py
    Fast unit tests for command construction, wrapper dispatch, runtime-root
    safety, timeout diagnostics, artifact discovery, and model facade.

tests/test_smoke_classifier.py
    Fast unit tests for the deterministic classifier.

tests/test_full_pipeline_smoke.py
    Opt-in Layer A real-root subprocess smoke.

tests/test_full_pipeline_real_runtime.py
    Opt-in Layer B real-model/GPU smoke.

tests/fixtures/full_pipeline_smoke/...
    Small FixedTest/taxonomy/model-metadata fixture.
```

Modify only documentation during normal implementation:

```text
.codex/workflows.md
.codex/known_issues.md
.codex/memory.md
```

Production files are **not expected to change**. If Layer A exposes a real production defect, change only the smallest relevant production file after first adding a focused regression test that reproduces that defect.

---

### Task 1: Build the isolated root-process harness and PATH dispatcher

**Files:**
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/full_pipeline_harness.py`
- Create: `tests/smoke/python_dispatch.py`
- Create: `tests/test_full_pipeline_harness.py`

**Interfaces:**
- Produces `SmokeConfig`, a frozen dataclass with at least:

```python
@dataclass(frozen=True)
class SmokeConfig:
    repository_root: Path
    fixed_test_dir: Path
    topic_tree_dir: Path
    topic_tree_files: str
    model_dir: Path
    model_type: str = "PytorchXLM"
    port: int = 18059
    execution_time: str = "20990101000000"
    timeout_seconds: int = 180
    intercept_classifier: bool = True
```

- Produces `SmokeResult`, containing:

```python
@dataclass(frozen=True)
class SmokeResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    runtime_root: Path
    workpool_root: Path
    workspaces: tuple[Path, ...]
    classifier_marker: Path | None
    timed_out: bool
```

- Produces these public helpers:

```python
def build_root_command(config: SmokeConfig, workpool_root: Path) -> list[str]: ...
def build_isolated_environment(config: SmokeConfig, runtime_root: Path,
                               classifier_marker: Path | None) -> dict[str, str]: ...
def create_python_wrapper(config: SmokeConfig, runtime_root: Path) -> Path: ...
def run_full_pipeline(config: SmokeConfig) -> SmokeResult: ...
def discover_workspaces(workpool_root: Path) -> tuple[Path, ...]: ...
def format_failure(result: SmokeResult, *, tail_lines: int = 120) -> str: ...
```

- Produces a Layer B helper:

```python
def create_model_facade(source_model_dir: Path, runtime_root: Path) -> Path: ...
```

The facade copies small top-level metadata needed by RunClassfier and links `checkpoint-*` directories to the real model source. Production writes such as `UsingMark.txt` therefore land in the temporary facade, not in the external model directory.

- `python_dispatch.py` reads the absolute real interpreter from `TCP_SMOKE_REAL_PYTHON` and the smoke classifier path from `TCP_SMOKE_CLASSIFIER_SCRIPT`.

- [ ] **Step 1: Write RED unit tests for canonical command construction**

Add tests asserting `build_root_command()` begins with `sys.executable, TCFMain.py`, contains all explicit isolation arguments, and never relies on default WorkPool/FixedTest/model discovery.

Representative assertion:

```python
command = build_root_command(config, Path("/tmp/smoke/WorkPool"))
joined = " ".join(command)
self.assertEqual(command[:2], [sys.executable, str(ROOT / "TCFMain.py")])
self.assertIn("-TRVHost False", joined)
self.assertIn("-nProc 1", joined)
self.assertIn("-nProcSPC 1", joined)
self.assertIn("-RMBertData False", joined)
self.assertIn("-p 18059", joined)
self.assertIn("-exectime 20990101000000", joined)
```

- [ ] **Step 2: Run the focused command-construction test and record genuine RED**

Run:

```bash
python -m unittest tests.test_full_pipeline_harness.FullPipelineHarnessTests.test_build_root_command_is_explicit_and_isolated
```

Expected: FAIL because the harness does not yet exist.

- [ ] **Step 3: Implement `SmokeConfig`, `SmokeResult`, and `build_root_command()` minimally**

The command must render explicit paths as separate argv elements for the root process, while respecting the legacy boolean spellings accepted by current `ClassfierOptionParser`.

- [ ] **Step 4: Add RED tests for whitespace-safe runtime roots and isolated environment**

Test that `build_isolated_environment()` redirects:

```text
TEMP
TMP
TMPDIR
HOME
HF_HOME
TRANSFORMERS_CACHE
```

and prepends the wrapper directory to `PATH` only when classifier interception is enabled.

If the system temp parent contains whitespace, the runtime root must fall back to `<repo>/.smoke-runtime/<unique-id>` and be removed after execution.

- [ ] **Step 5: Implement runtime-root/environment construction**

Do not create mutable files outside the runtime root except the repository fallback `.smoke-runtime`, which must be removed on cleanup.

- [ ] **Step 6: Add RED dispatch tests**

Use a temporary fake real Python executable/recording script to prove:

1. `python_dispatch.py normal_child.py --x 1` forwards unchanged to the real interpreter.
2. `python_dispatch.py BertScript/TextClassification_transformers.py ...` invokes the smoke classifier instead.
3. Exit codes propagate unchanged.

- [ ] **Step 7: Implement `python_dispatch.py` and platform wrappers**

Generated wrapper behavior:

POSIX conceptual form:

```sh
#!/bin/sh
exec "${TCP_SMOKE_REAL_PYTHON}" "${TCP_SMOKE_DISPATCH_SCRIPT}" "$@"
```

Windows conceptual form:

```bat
@echo off
"%TCP_SMOKE_REAL_PYTHON%" "%TCP_SMOKE_DISPATCH_SCRIPT%" %*
exit /b %ERRORLEVEL%
```

The dispatcher itself must use absolute `sys.executable`/environment-provided paths so forwarded children do not recurse back through the shim.

- [ ] **Step 8: Add RED tests for subprocess timeout and bounded diagnostics**

Use a child that sleeps longer than a tiny test timeout. Assert `timed_out=True`, the process is terminated, and `format_failure()` returns bounded stdout/stderr plus remaining workspace suffixes.

- [ ] **Step 9: Implement process-tree execution**

Use `subprocess.Popen` rather than bare `subprocess.run` so timeout cleanup can terminate descendants.

POSIX:

```python
start_new_session=True
os.killpg(process.pid, signal.SIGKILL)
```

Windows:

```python
creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], ...)
```

If `taskkill` itself fails, terminate the root process and report that child-tree cleanup could not be fully confirmed; do not translate timeout into PASS.

- [ ] **Step 10: Add RED tests for model-facade isolation**

Build a fake source model containing:

```text
TopicAnalysis_LabelList.txt
checkpoint-10/config.json
checkpoint-10/model.safetensors   (tiny dummy test file)
```

Assert the facade has its own copied `TopicAnalysis_LabelList.txt`, a linked `checkpoint-10`, and writing `UsingMark.txt` into the facade does not create that file in the source model directory.

- [ ] **Step 11: Implement `create_model_facade()`**

POSIX: directory symlink via `os.symlink(..., target_is_directory=True)`.

Windows: try directory symlink first; if unavailable, create a junction with:

```text
cmd /c mklink /J <facade-checkpoint> <source-checkpoint>
```

Fail with an actionable test error if no checkpoint directory exists or no safe directory-link mechanism is available. Never fall back to running Layer B directly against the external writable model directory.

- [ ] **Step 12: Run Task 1 tests**

```bash
python -m unittest tests.test_full_pipeline_harness
```

Expected: PASS.

- [ ] **Step 13: Commit Task 1**

```bash
git add tests/smoke tests/test_full_pipeline_harness.py
git commit -m "test: add isolated full-pipeline smoke harness"
```

---

### Task 2: Add deterministic classifier and production-shaped smoke fixtures

**Files:**
- Create: `tests/smoke/smoke_classifier.py`
- Create: `tests/test_smoke_classifier.py`
- Create: `tests/fixtures/full_pipeline_smoke/fixed_test/Using/#T#[Aloha]/aloha.txt`
- Create: `tests/fixtures/full_pipeline_smoke/fixed_test/Using/#T#[Bosh]/bosh.txt`
- Create: `tests/fixtures/full_pipeline_smoke/taxonomy/TopicTree_smoke.csv`
- Create: `tests/fixtures/full_pipeline_smoke/model/TopicAnalysis_LabelList.txt`

**Interfaces:**
- `smoke_classifier.main(argv=None) -> int`
- Reads the real generated `test.sql3` and writes `<BertDataDir>/test_results.tsv`.
- Writes one line to `TCP_SMOKE_CLASSIFIER_MARKER` per invocation.

The fixture labels `Aloha` and `Bosh` are deliberate: both are already canonical repository taxonomy nodes in `ClassesTree/data/TopicTree_AK4.csv`, so Stage 4's existing taxonomy loading remains compatible.

`TopicTree_smoke.csv` content:

```csv
#母類別,子類別,日期,關係,備註
AK4,Informative_AK4,209901010000,contains,
AK4,Scrap_AK4,209901010000,contains,
Informative_AK4,Aloha,209901010000,contains,
Scrap_AK4,Bosh,209901010000,contains,
```

`TopicAnalysis_LabelList.txt` content:

```text
Aloha
Bosh
```

Each FixedTest text must be short, non-empty UTF-8 text comfortably below `MaxSeqLength=180` so the existing short-message path does not need to load a tokenizer.

- [ ] **Step 1: Write RED classifier tests using a temporary SQLite `sampleSrc` table**

Create `test.sql3` with ordered rows:

```text
(Aloha, "alpha text")
(Bosh, "beta text")
(Aloha, "gamma text")
```

Write matching `TopicAnalysis_LabelList.txt`, run `smoke_classifier.main([...])`, and assert:

```text
return code = 0
test_results.tsv has 3 non-empty lines
every line is in {Aloha, Bosh}
marker has exactly one invocation record
```

- [ ] **Step 2: Run focused classifier test and record RED**

```bash
python -m unittest tests.test_smoke_classifier
```

Expected: FAIL because the smoke classifier is not implemented.

- [ ] **Step 3: Implement tolerant CLI parsing**

Use `argparse.ArgumentParser(add_help=False)` plus `parse_known_args()` for the current Pytorch command surface:

```python
parser.add_argument("-ts", "--test")
parser.add_argument("-mdlDir", "--modelDir")
parser.add_argument("-BertDataDir", "--BertDatasetSubDir", required=True)
parser.add_argument("-mdlType", "--ModelType")
parser.add_argument("-ZeroShot", "--ActiveHTCZeroshot")
parser.add_argument("-MaxSeqLen", "--MaxSeqLength")
parser.add_argument("-SaveOptimizer", "--SaveOptimizer")
```

Unknown current renderer arguments are tolerated; missing `BertDatasetSubDir`, missing `test.sql3`, empty test rows, or empty label metadata are hard failures.

- [ ] **Step 4: Implement deterministic predictions**

Query:

```sql
SELECT OutLabel, text FROM sampleSrc ORDER BY rowid;
```

Prefer emitting the row's `OutLabel` when it exists in the model metadata label set; otherwise deterministically cycle through the sorted metadata labels. This keeps every output valid while preserving row count/order.

Write exactly one prediction label per line to `test_results.tsv`.

- [ ] **Step 5: Add the committed fixture tree**

Do not copy full production taxonomy or model weights into tests.

- [ ] **Step 6: Add fixture-contract tests**

Assert:

- both FixedTest label directories exist;
- all fixture texts are non-empty and shorter than 180 characters;
- every fixture label is present in `TopicTree_smoke.csv`;
- every fixture label appears in the model metadata label list;
- `Aloha` and `Bosh` are also present in the canonical `ClassesTree/data/TopicTree_AK4.csv` source.

- [ ] **Step 7: Run Task 2 tests**

```bash
python -m unittest tests.test_smoke_classifier tests.test_full_pipeline_harness
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add tests/smoke/smoke_classifier.py tests/test_smoke_classifier.py tests/fixtures/full_pipeline_smoke
git commit -m "test: add deterministic pipeline smoke classifier"
```

---

### Task 3: Add and make Layer A root full-pipeline smoke genuinely pass

**Files:**
- Create: `tests/test_full_pipeline_smoke.py`
- Modify only if a real smoke-discovered production defect requires it: the smallest relevant production file plus its existing focused test module.

**Interfaces:**
- Uses `SmokeConfig` and `run_full_pipeline()` from Task 1.
- Uses committed fixtures from Task 2.

- [ ] **Step 1: Write the opt-in Layer A test**

Structure:

```python
@unittest.skipUnless(
    os.environ.get("TCP_RUN_FULL_PIPELINE_SMOKE") == "1",
    "set TCP_RUN_FULL_PIPELINE_SMOKE=1 to run isolated root full-pipeline smoke",
)
class FullPipelineSmokeTests(unittest.TestCase):
    def test_root_pipeline_reaches_spike_ready_workspace(self):
        ...
```

The test snapshots the repository's default `WorkPool` directory entries before execution, runs the real root, then asserts:

1. `returncode == 0` and `timed_out is False`;
2. no uncaught `Traceback (most recent call last)` in root stdout/stderr;
3. exactly one classifier-interception marker record;
4. exactly one final temporary workspace ending `_rdy_for_Spike`;
5. no `_is_running_DataConverter`, `_is_running_RunClassfier`, `_is_running_CombineTestResult`, or `_is_running_TestResultVis` directories remain;
6. final workspace contains non-empty `test.tsv`, `test.sql3`, and `test_results.tsv`;
7. `test_results_verification.sql3` exists and contains the same number of result rows as `test.sql3`;
8. Stage 4 output validation artifacts required by its current production path exist;
9. default repository `WorkPool` directory-entry snapshot is unchanged.

On failure call `format_failure(result)` in the assertion message.

- [ ] **Step 2: Confirm normal discovery skips Layer A**

```bash
python -m unittest tests.test_full_pipeline_smoke
```

Expected: `OK (skipped=1)` with the actionable environment message.

- [ ] **Step 3: Run Layer A enabled and record the first genuine root result**

POSIX:

```bash
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
```

PowerShell:

```powershell
$env:TCP_RUN_FULL_PIPELINE_SMOKE='1'
python -m unittest tests.test_full_pipeline_smoke
Remove-Item Env:TCP_RUN_FULL_PIPELINE_SMOKE
```

Do **not** assume the first enabled run will pass.

- [ ] **Step 4: If Layer A exposes a production regression, preserve the RED before fixing it**

This is a hard scope rule:

- Do not alter the harness to skip a failing canonical child.
- Do not suppress the second visualization invocation.
- Do not convert a child non-zero exit into success.

If the failure is the anticipated second non-hosted visualization lifecycle collision, first add a focused regression to the existing root/visualization characterization suite that reproduces the exact state transition and command invocation semantics. Inspect source/history to determine intended compatibility behavior, then apply the smallest production correction supported by that evidence.

If a different production regression appears, add the smallest focused RED in that component's existing test module before changing production.

If intended behavior cannot be established from current source/history/tests, stop this task and report the exact blocker rather than inventing semantics.

- [ ] **Step 5: Rerun the focused defect test and Layer A until both are green**

The Layer A test is authoritative for this task.

- [ ] **Step 6: Run the focused Stage 1–4/root compatibility suites**

```bash
python -m unittest \
  tests.test_tcf_main_characterization \
  tests.test_data_converter_stage_plan \
  tests.test_classifier_stage \
  tests.test_result_combination_stage \
  tests.test_visualization_stage \
  tests.test_stage_commands
```

Use the actual existing Stage 2/3 test module names if they differ; do not create aliases merely to satisfy this command.

- [ ] **Step 7: Commit Task 3**

If only the smoke test changed:

```bash
git add tests/test_full_pipeline_smoke.py
git commit -m "test: add isolated root full-pipeline smoke"
```

If a real production regression was also fixed, make that correction a separate commit after its focused RED/GREEN cycle, for example:

```bash
git commit -m "fix: preserve non-hosted visualization lifecycle"
```

Do not squash the smoke addition and an unrelated runtime correction into an opaque single change during development.

---

### Task 4: Add Layer B real-model smoke with safe model facade

**Files:**
- Create: `tests/test_full_pipeline_real_runtime.py`
- Modify: `tests/smoke/full_pipeline_harness.py` only as needed for Layer B facade/result evidence.
- Test: `tests/test_full_pipeline_harness.py`

**Interfaces:**
- Required environment:

```text
TCP_RUN_REAL_PIPELINE_SMOKE=1
TCP_REAL_MODEL_DIR
TCP_REAL_FIXED_TEST_DIR
TCP_REAL_TOPIC_TREE_DIR
TCP_REAL_TOPIC_TREE_FILES
```

- Optional:

```text
TCP_REAL_MODEL_TYPE=PytorchXLM
TCP_REAL_PIPELINE_TIMEOUT_SECONDS=1800
```

- [ ] **Step 1: Write RED environment-validation tests**

When enabled but a required variable is missing, fail immediately with the missing variable name before launching any root process.

When not enabled, normal discovery must report a single explicit skip.

- [ ] **Step 2: Implement the Layer B test configuration**

Validate all external paths before execution.

Build the temporary model facade from `TCP_REAL_MODEL_DIR` and pass the facade path as `-mdlDir`. Never pass the external source model directory directly to production root execution.

Pass external FixedTest/taxonomy paths explicitly.

Use:

```text
-TRVHost False
-WPRoot <temporary WorkPool>
-nProc 1
-nProcSPC 1
-RMBertData False
```

Install no PATH classifier interception shim.

- [ ] **Step 3: Snapshot external source inputs**

Before/after Layer B, collect a metadata snapshot for FixedTest and source model sufficient to catch accidental writes without hashing multi-GB weights:

```text
relative path
file size
mtime_ns
```

At minimum include all regular files. Assert the snapshot is unchanged after the smoke.

Because the real model is accessed through checkpoint links in the temporary facade, `UsingMark.txt` and other writable top-level model state must remain inside the facade.

- [ ] **Step 4: Capture real-classifier evidence**

The result/diagnostics must establish that no interception marker was used and that the real `TextClassification_transformers.py` command was rendered/executed. Inspect the final workspace's `logs/RunClassfier.log` as supporting evidence.

Record CUDA availability from the same environment. Do not make CUDA an unconditional test prerequisite; the post-merge H100 acceptance run must separately record CUDA availability as true before `KI-003` closure.

- [ ] **Step 5: Run default Layer B discovery**

```bash
python -m unittest tests.test_full_pipeline_real_runtime
```

Expected: explicit SKIP when not enabled.

- [ ] **Step 6: Do not fabricate a real-runtime PASS in Codex/cloud environments**

If the implementation environment lacks the user's real model/FixedTest/GPU, report Layer B as `SKIP/not executed`, not PASS.

The first authoritative Layer B acceptance run occurs after merge on the user's real runtime host.

- [ ] **Step 7: Run Task 4 unit coverage**

```bash
python -m unittest tests.test_full_pipeline_harness tests.test_full_pipeline_real_runtime
```

Expected in a normal development environment: harness tests PASS, real-runtime test SKIP.

- [ ] **Step 8: Commit Task 4**

```bash
git add tests/smoke/full_pipeline_harness.py tests/test_full_pipeline_harness.py tests/test_full_pipeline_real_runtime.py
git commit -m "test: add opt-in real-model pipeline smoke"
```

---

### Task 5: Document the two smoke profiles and reconcile KI-003 without closing it early

**Files:**
- Modify: `.codex/workflows.md`
- Modify: `.codex/known_issues.md`
- Modify: `.codex/memory.md`
- Test: `tests/test_project_docs.py`

**Interfaces:**
- Documents exact Layer A and Layer B commands.
- `KI-003` stays Open in this implementation PR unless a reviewed merged baseline has already received a successful H100 Layer B acceptance run, which is not expected during initial implementation.
- `KI-002` stays Open.

- [ ] **Step 1: Add/adjust doc assertions first**

Update `tests/test_project_docs.py` so current-state docs must mention:

```text
TCP_RUN_FULL_PIPELINE_SMOKE
TCP_RUN_REAL_PIPELINE_SMOKE
KI-003
KI-002
```

and preserve the canonical compile gate.

Run the focused doc test and record RED before changing docs.

- [ ] **Step 2: Update `.codex/workflows.md`**

Document POSIX Layer A:

```bash
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
```

PowerShell Layer A:

```powershell
$env:TCP_RUN_FULL_PIPELINE_SMOKE='1'
python -m unittest tests.test_full_pipeline_smoke
Remove-Item Env:TCP_RUN_FULL_PIPELINE_SMOKE
```

Document Layer B environment variables and both shell forms without embedding any real local user path into repository docs.

State explicitly that normal `python -m unittest discover -s tests` discovers these modules as opt-in skips.

- [ ] **Step 3: Update `.codex/known_issues.md`**

Keep `KI-003` Open, but replace the old workaround/evidence with the new status:

- Layer A hermetic root smoke exists and passes when explicitly enabled.
- Layer B real-runtime smoke exists but requires post-merge real model/GPU execution evidence.
- Resolution gate is Layer A PASS + Layer B PASS + temporary WorkPool isolation + final `_rdy_for_Spike` + H100/CUDA evidence for the intended acceptance run.

Keep `KI-002` Open and explicitly note that the new smoke does not exercise WeiTech queue acquisition/processed delivery.

- [ ] **Step 4: Update `.codex/memory.md` without adding an eleventh outcome**

Keep exactly ten durable outcomes. Update outcome 10 to record that:

- repository compile gate remains restored;
- isolated root full-pipeline smoke exists;
- `KI-003` awaits real-runtime acceptance evidence;
- `KI-002` remains Open.

- [ ] **Step 5: Run documentation tests**

```bash
python -m unittest tests.test_project_docs
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add .codex tests/test_project_docs.py
git commit -m "docs: document full-pipeline smoke verification"
```

---

## Final Verification Before PR

- [ ] Run fast smoke infrastructure tests:

```bash
python -m unittest \
  tests.test_full_pipeline_harness \
  tests.test_smoke_classifier
```

- [ ] Run Layer A enabled:

POSIX:

```bash
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
```

PowerShell equivalent must also be documented; execute on the available platform.

- [ ] Confirm Layer B default behavior is an intentional skip:

```bash
python -m unittest tests.test_full_pipeline_real_runtime
```

- [ ] Run project docs/package/root compatibility gates:

```bash
python -m unittest \
  tests.test_project_docs \
  tests.test_package_layout \
  tests.test_tcf_main_characterization \
  tests.test_tcf_workpool_characterization
```

- [ ] Run full discovery:

```bash
python -m unittest discover -s tests
```

Expected: all dependency-light tests pass; Layer A and Layer B modules are skipped unless their opt-in variables are present.

- [ ] Run canonical compile gate:

```bash
python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler
```

Expected exit status: `0`.

- [ ] Run repository hygiene:

```bash
git diff --check
git status --short --branch
```

- [ ] Verify no generated `.smoke-runtime`, temporary WorkPool, classifier marker, or model-facade artifact remains in the working tree.

---

## PR Scope and Completion Report

Suggested implementation branch:

```text
codex/implement-ki-003-full-pipeline-smoke
```

Suggested PR title:

```text
test: add isolated full-pipeline smoke verification
```

The completion report must include:

```text
Repository
Branch
Hosted starting SHA
Local starting SHA
Resulting SHA(s)
Spec path + spec commit
Plan path + plan commit
Changed files
```

Then report:

1. genuine RED/GREEN evidence for harness, dispatcher, classifier, and Layer A;
2. whether Layer A exposed any new production integration regression and, if so, its separate focused RED/fix commit;
3. Layer A root command, exit code, final workspace suffix, and canonical artifacts;
4. proof that only the model inference child was intercepted;
5. proof that the repository default WorkPool was unchanged;
6. normal-discovery skip behavior for both smoke modules;
7. Layer B implementation status and why it was or was not executable in the implementation environment;
8. confirmation that real model source is accessed through a temporary facade rather than used as the writable `modelDir`;
9. full unittest discovery result;
10. canonical compileall exit status;
11. `git diff --check` and working-tree state;
12. confirmation that `KI-003` remains Open pending post-merge real-runtime acceptance;
13. confirmation that `KI-002` remains Open.

End with:

```text
Full-pipeline smoke implementation ready for post-merge review and H100 real-runtime acceptance.
```

---

## Post-Merge H100 Acceptance Procedure

After the implementation PR is reviewed and merged, run Layer B on the user's actual runtime host using the merged `main` baseline.

PowerShell shape:

```powershell
$env:TCP_RUN_REAL_PIPELINE_SMOKE='1'
$env:TCP_REAL_MODEL_DIR='<real output model directory>'
$env:TCP_REAL_FIXED_TEST_DIR='<real FixedTest Using directory>'
$env:TCP_REAL_TOPIC_TREE_DIR='<real taxonomy directory>'
$env:TCP_REAL_TOPIC_TREE_FILES='TopicTree.csv,TopicTree_AK4.csv'
$env:TCP_REAL_MODEL_TYPE='PytorchXLM'
$env:TCP_REAL_PIPELINE_TIMEOUT_SECONDS='1800'
python -m unittest tests.test_full_pipeline_real_runtime
```

Acceptance evidence required before closing `KI-003`:

```text
root exit 0
CUDA available/selected by the production classifier path
final workspace = *_rdy_for_Spike
real TextClassification_transformers.py executed
expected classifier/combination/visualization artifacts exist
external FixedTest/model source snapshots unchanged
temporary WorkPool cleaned after assertions
```

Only after that evidence is reviewed should a small follow-up docs change move `KI-003` to Recently Resolved. `KI-002` remains independent and Open.