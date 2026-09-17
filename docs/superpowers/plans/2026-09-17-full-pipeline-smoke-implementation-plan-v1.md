# Full-Pipeline Smoke Test Implementation Plan v1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the successful manual `python TCFMain.py -p 8059 -ts y` run into a reproducible, isolated, automatable root-level smoke test that exercises the real child entrypoints and supplies the evidence needed to resolve `KI-003` after a real-model acceptance run.

**Architecture:** Layer A starts the real `TCFMain.py` process and real Stage 1–4 entrypoints, while a PATH-level `python` dispatcher substitutes only `BertScript/TextClassification_transformers.py` with a deterministic SQLite-backed test classifier. Layer B reuses the same harness without interception and runs the production classifier through a temporary writable model facade, keeping WorkPool and other mutable state isolated.

**Tech Stack:** Python `unittest`, `subprocess`, `tempfile`, `sqlite3`, `pathlib`, POSIX process groups, Windows process groups/junctions, existing legacy CLI/stage scripts.

**Spec:** `docs/superpowers/specs/2026-09-17-full-pipeline-smoke-design-v1.md`

**Repository:** `hun186/text-category-profiler`

**Authoritative source baseline:** `98d8a9bc7b4492e7de6355a77b0cbfebe2fea57a`

**Approved design commit:** `821d8574f5e2b5220b2649966e8a4775d2f790ec`

## Global Constraints

- Do not add a production `--smoke` option, `SMOKE_MODE`, or production environment branch merely for tests.
- Layer A must execute the real root process plus the real `DatasetConverter/DataConverter.py`, `BertScript/RunClassfier.py`, `BertScript/CombineTestResult.py`, and `BertScript/Test_result_Vis.py` child entrypoints.
- Layer A may substitute only the `BertScript/TextClassification_transformers.py` inference child.
- Layer B must install no classifier interception shim.
- Both layers use a temporary WorkPool and `-TRVHost False`.
- Layer A uses `-nProc 1 -nProcSPC 1 -RMBertData False -p 18059 -exectime 20990101000000`.
- Layer A subprocess execution is opt-in through `TCP_RUN_FULL_PIPELINE_SMOKE=1`; normal discovery reports an explicit skip.
- Layer B execution is opt-in through `TCP_RUN_REAL_PIPELINE_SMOKE=1` and requires explicit external model, FixedTest, and taxonomy inputs.
- Do not auto-discover or use a developer's production FixedTest/model path in Layer A.
- Do not bypass the root's existing double visualization invocation. If that path fails, preserve the root failure as genuine integration evidence rather than changing the harness to hide it.
- `KI-003` remains Open in the implementation PR. It can close only after reviewed/merged Layer A plus a post-merge real-model Layer B PASS meet the design acceptance gate.
- `KI-002` remains Open unless separate work proves isolated root-level WeiTech acquisition and processed-delivery behavior.
- The canonical compile gate remains `python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler` and must remain exit 0.

---

## File Structure

Create:

```text
tests/smoke/__init__.py
tests/smoke/full_pipeline_harness.py
tests/smoke/python_dispatch.py
tests/smoke/smoke_classifier.py
tests/test_full_pipeline_harness.py
tests/test_smoke_classifier.py
tests/test_full_pipeline_smoke.py
tests/test_full_pipeline_real_runtime.py
tests/fixtures/full_pipeline_smoke/fixed_test/Using/#T#[Aloha]/aloha.txt
tests/fixtures/full_pipeline_smoke/fixed_test/Using/#T#[Bosh]/bosh.txt
tests/fixtures/full_pipeline_smoke/taxonomy/TopicTree_smoke.csv
tests/fixtures/full_pipeline_smoke/model/TopicAnalysis_LabelList.txt
```

Modify:

```text
.codex/workflows.md
.codex/known_issues.md
.codex/memory.md
tests/test_project_docs.py
```

Production files are not expected to change in this implementation. If Layer A exposes a new production regression, stop at that RED with a precise blocker report unless the failure is already covered by an existing accepted compatibility rule that makes the minimal correction unambiguous. Do not redesign production behavior inside the smoke PR.

---

### Task 1: Isolated root-process harness and PATH dispatcher

**Files:**
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/full_pipeline_harness.py`
- Create: `tests/smoke/python_dispatch.py`
- Create: `tests/test_full_pipeline_harness.py`

**Interfaces:**

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

Public helpers:

```python
def build_root_command(config: SmokeConfig, workpool_root: Path) -> list[str]: ...
def build_isolated_environment(config: SmokeConfig, runtime_root: Path,
                               classifier_marker: Path | None) -> dict[str, str]: ...
def create_python_wrapper(config: SmokeConfig, runtime_root: Path) -> Path: ...
def run_full_pipeline(config: SmokeConfig) -> SmokeResult: ...
def discover_workspaces(workpool_root: Path) -> tuple[Path, ...]: ...
def format_failure(result: SmokeResult, *, tail_lines: int = 120) -> str: ...
def create_model_facade(source_model_dir: Path, runtime_root: Path) -> Path: ...
```

`python_dispatch.py` reads the real interpreter from `TCP_SMOKE_REAL_PYTHON`, the dispatcher target from `TCP_SMOKE_CLASSIFIER_SCRIPT`, and writes classifier invocation evidence to `TCP_SMOKE_CLASSIFIER_MARKER` only through the smoke classifier itself.

- [ ] **Step 1: Write the command-construction RED**

Add `FullPipelineHarnessTests.test_build_root_command_is_explicit_and_isolated` asserting the command starts with `sys.executable` and absolute `TCFMain.py`, and contains explicit values for:

```text
-p 18059
-ts y
-TRVHost False
-WPRoot <temporary WorkPool>
-FTPath <explicit fixture>
-TopicTreeDir <explicit fixture taxonomy>
-TopicTreeFiles TopicTree_smoke.csv
-mdlDir <explicit fixture model metadata>
-mdlType PytorchXLM
-nProc 1
-nProcSPC 1
-RMBertData False
-exectime 20990101000000
```

Run:

```bash
python -m unittest tests.test_full_pipeline_harness.FullPipelineHarnessTests.test_build_root_command_is_explicit_and_isolated
```

Expected RED: module/helper does not exist yet.

- [ ] **Step 2: Implement `SmokeConfig`, `SmokeResult`, and `build_root_command()` minimally**

Root execution uses argv, not a shell string. Keep each explicit path/value as a separate argv item.

- [ ] **Step 3: Write RED tests for isolation environment and whitespace-safe runtime root**

Assert `TEMP`, `TMP`, `TMPDIR`, `HOME`, `HF_HOME`, and `TRANSFORMERS_CACHE` point under the runtime root. PATH is prefixed with the wrapper directory only when `intercept_classifier=True`.

Because production child commands are rendered as unquoted shell text, a system temporary parent containing whitespace is unsafe. In that case use `<repository>/.smoke-runtime/<unique-id>` and remove it after the run.

- [ ] **Step 4: Implement runtime-root/environment construction**

No mutable runtime file may escape the runtime root except the temporary repository fallback directory described above, which must be cleaned.

- [ ] **Step 5: Write dispatcher RED tests**

Prove all three behaviors:

1. `normal_child.py --x 1` is forwarded unchanged to the real interpreter.
2. `BertScript/TextClassification_transformers.py ...` is redirected to `tests/smoke/smoke_classifier.py`.
3. The selected child's exit code is returned unchanged.

- [ ] **Step 6: Implement the dispatcher and platform wrappers**

POSIX wrapper:

```sh
#!/bin/sh
exec "${TCP_SMOKE_REAL_PYTHON}" "${TCP_SMOKE_DISPATCH_SCRIPT}" "$@"
```

Windows wrapper:

```bat
@echo off
"%TCP_SMOKE_REAL_PYTHON%" "%TCP_SMOKE_DISPATCH_SCRIPT%" %*
exit /b %ERRORLEVEL%
```

The dispatcher uses absolute paths from its environment and must not recurse through PATH.

- [ ] **Step 7: Write timeout/diagnostic RED tests**

Use a child that sleeps beyond a very small test timeout. Assert `timed_out=True`, root/descendants are terminated, and `format_failure()` includes command, exit/timeout state, bounded stdout/stderr, WorkPool path, and remaining workspace suffixes.

- [ ] **Step 8: Implement process-tree lifecycle**

Use `subprocess.Popen`.

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

If descendant cleanup cannot be confirmed, report the timeout as failure; never translate it into PASS.

- [ ] **Step 9: Write model-facade RED tests**

Use a fake source model:

```text
TopicAnalysis_LabelList.txt
checkpoint-10/config.json
checkpoint-10/model.safetensors
```

Assert the facade copies top-level metadata, links `checkpoint-10`, and a facade `UsingMark.txt` does not appear in the source model.

- [ ] **Step 10: Implement `create_model_facade()`**

POSIX: `os.symlink(..., target_is_directory=True)` for checkpoint directories.

Windows: try a directory symlink; if unavailable, use:

```text
cmd /c mklink /J <facade-checkpoint> <source-checkpoint>
```

Fail clearly if there is no `checkpoint-*` directory or no safe link mechanism. Never fall back to the source model as writable `-mdlDir`.

- [ ] **Step 11: GREEN Task 1**

```bash
python -m unittest tests.test_full_pipeline_harness
```

- [ ] **Step 12: Commit Task 1**

```bash
git add tests/smoke tests/test_full_pipeline_harness.py
git commit -m "test: add isolated full-pipeline smoke harness"
```

---

### Task 2: Deterministic classifier and production-shaped fixtures

**Files:**
- Create: `tests/smoke/smoke_classifier.py`
- Create: `tests/test_smoke_classifier.py`
- Create the six fixture paths listed in File Structure.

**Interface:** `smoke_classifier.main(argv=None) -> int`.

It reads the real generated `<BertDataDir>/test.sql3`, reads the real copied `<BertDataDir>/TopicAnalysis_LabelList.txt`, writes `<BertDataDir>/test_results.tsv`, and appends exactly one record per invocation to `TCP_SMOKE_CLASSIFIER_MARKER`.

Use `Aloha` and `Bosh` because both are canonical nodes in `ClassesTree/data/TopicTree_AK4.csv`; this keeps Stage 4 compatible with its existing canonical taxonomy load.

`TopicTree_smoke.csv`:

```csv
#母類別,子類別,日期,關係,備註
AK4,Informative_AK4,209901010000,contains,
AK4,Scrap_AK4,209901010000,contains,
Informative_AK4,Aloha,209901010000,contains,
Scrap_AK4,Bosh,209901010000,contains,
```

`TopicAnalysis_LabelList.txt`:

```text
Aloha
Bosh
```

Both FixedTest documents are non-empty UTF-8 and shorter than 180 characters so the current short-message branch returns before Hugging Face tokenizer loading.

- [ ] **Step 1: Write classifier RED**

Create a temporary `test.sql3` with `sampleSrc` rows in rowid order:

```text
(Aloha, "alpha text")
(Bosh, "beta text")
(Aloha, "gamma text")
```

Assert return code 0, exactly three prediction lines, each prediction in `{Aloha, Bosh}`, and exactly one marker record.

- [ ] **Step 2: Run RED**

```bash
python -m unittest tests.test_smoke_classifier
```

Expected: FAIL because the classifier is absent.

- [ ] **Step 3: Implement tolerant current-command parsing**

Use `argparse.ArgumentParser(add_help=False)` plus `parse_known_args()` for:

```python
parser.add_argument("-ts", "--test")
parser.add_argument("-mdlDir", "--modelDir")
parser.add_argument("-BertDataDir", "--BertDatasetSubDir", required=True)
parser.add_argument("-mdlType", "--ModelType")
parser.add_argument("-ZeroShot", "--ActiveHTCZeroshot")
parser.add_argument("-MaxSeqLen", "--MaxSeqLength")
parser.add_argument("-SaveOptimizer", "--SaveOptimizer")
```

Missing dataset path, `test.sql3`, test rows, or label metadata is a hard error.

- [ ] **Step 4: Implement deterministic predictions**

Query:

```sql
SELECT OutLabel, text FROM sampleSrc ORDER BY rowid;
```

Use the row's `OutLabel` when it is in the metadata label set; otherwise cycle deterministically through sorted metadata labels. Write exactly one label per test row.

- [ ] **Step 5: Add fixture-contract tests and files**

Assert:

- both FixedTest label directories exist;
- documents are non-empty and `<180` characters;
- fixture labels are in `TopicTree_smoke.csv`;
- fixture labels are in model metadata;
- `Aloha` and `Bosh` occur in canonical `ClassesTree/data/TopicTree_AK4.csv`.

- [ ] **Step 6: GREEN Task 2**

```bash
python -m unittest tests.test_smoke_classifier tests.test_full_pipeline_harness
```

- [ ] **Step 7: Commit Task 2**

```bash
git add tests/smoke/smoke_classifier.py tests/test_smoke_classifier.py tests/fixtures/full_pipeline_smoke
git commit -m "test: add deterministic pipeline smoke classifier"
```

---

### Task 3: Layer A real-root full-pipeline smoke

**Files:**
- Create: `tests/test_full_pipeline_smoke.py`

**Consumes:** `SmokeConfig`, `run_full_pipeline()`, `format_failure()`, and Task 2 fixtures.

- [ ] **Step 1: Add opt-in test declaration**

```python
@unittest.skipUnless(
    os.environ.get("TCP_RUN_FULL_PIPELINE_SMOKE") == "1",
    "set TCP_RUN_FULL_PIPELINE_SMOKE=1 to run isolated root full-pipeline smoke",
)
class FullPipelineSmokeTests(unittest.TestCase):
    ...
```

- [ ] **Step 2: Assert exact success contract**

Before execution snapshot the repository default `WorkPool` top-level directory entries. After execution assert:

1. `returncode == 0` and `timed_out is False`;
2. no uncaught `Traceback (most recent call last)` appears in root stdout/stderr;
3. classifier marker contains exactly one invocation;
4. exactly one temporary workspace ends `_rdy_for_Spike`;
5. no workspace ending `_is_running_DataConverter`, `_is_running_RunClassfier`, `_is_running_CombineTestResult`, or `_is_running_TestResultVis` remains;
6. final workspace contains non-empty `test.tsv`, `test.sql3`, and `test_results.tsv`;
7. final workspace contains `test_results_verification.sql3`, whose result-row count equals the row count in `test.sql3`;
8. final workspace contains `logs/Test_result_Vis.log`; this is the concrete Stage 4 completion evidence because current production `_validate_visualization()` itself returns `True` unconditionally;
9. the repository default `WorkPool` top-level snapshot is unchanged.

Use `format_failure(result)` in failed assertion messages.

- [ ] **Step 3: Verify default discovery is an explicit SKIP**

```bash
python -m unittest tests.test_full_pipeline_smoke
```

Expected: `OK (skipped=1)` with the opt-in message.

- [ ] **Step 4: Run genuine Layer A root smoke**

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

Record the first real result exactly. Do not assume PASS.

- [ ] **Step 5: Handle a product-path RED without hiding it**

If the harness/fixture itself is wrong, add a focused harness/fixture RED and correct it.

If the real root path fails after the harness has correctly launched the canonical command—especially at the existing second visualization invocation—do not skip the child, suppress non-zero status, or alter expected suffixes. Record:

```text
root command
failing stage/child
exit code
stdout/stderr tail
remaining workspace suffixes
```

Then stop the implementation at this task and report the production regression for a separate corrective review. The smoke PR must not invent new production semantics merely to turn Layer A green.

- [ ] **Step 6: When Layer A is green, run exact existing compatibility suites**

```bash
python -m unittest \
  tests.test_tcf_main_characterization \
  tests.test_data_converter_stage_plan \
  tests.test_classifier_stage \
  tests.test_result_combination_stage \
  tests.test_visualization_stage \
  tests.test_stage_commands
```

All six modules exist on the authoritative baseline and must pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add tests/test_full_pipeline_smoke.py
git commit -m "test: add isolated root full-pipeline smoke"
```

---

### Task 4: Layer B real-model smoke with a safe model facade

**Files:**
- Create: `tests/test_full_pipeline_real_runtime.py`
- Modify: `tests/smoke/full_pipeline_harness.py`
- Test: `tests/test_full_pipeline_harness.py`

**Required environment when enabled:**

```text
TCP_RUN_REAL_PIPELINE_SMOKE=1
TCP_REAL_MODEL_DIR
TCP_REAL_FIXED_TEST_DIR
TCP_REAL_TOPIC_TREE_DIR
TCP_REAL_TOPIC_TREE_FILES
```

**Optional:**

```text
TCP_REAL_MODEL_TYPE=PytorchXLM
TCP_REAL_PIPELINE_TIMEOUT_SECONDS=1800
```

- [ ] **Step 1: Write environment-validation RED tests**

When the profile is disabled, discovery is one explicit skip. When enabled with a missing required variable, fail before any root process launch and name the missing variable.

- [ ] **Step 2: Implement Layer B configuration**

Validate every external input path. Create a temporary model facade from `TCP_REAL_MODEL_DIR` and pass the facade as `-mdlDir`; never pass the external source model directly as writable modelDir.

Pass FixedTest and taxonomy inputs explicitly. Install no dispatcher/wrapper interception.

Use:

```text
-TRVHost False
-WPRoot <temporary WorkPool>
-nProc 1
-nProcSPC 1
-RMBertData False
```

- [ ] **Step 3: Snapshot external source inputs before/after**

For all regular files beneath external FixedTest and source model collect:

```text
relative path
file size
mtime_ns
```

Assert both snapshots remain identical after the run. Do not hash multi-GB weights.

- [ ] **Step 4: Assert real-classifier evidence**

Require no classifier interception marker. Use final `logs/RunClassfier.log` plus root diagnostics to prove the real `TextClassification_transformers.py` path was executed.

Record CUDA availability/selection in the acceptance evidence. CUDA is not an unconditional unit-test prerequisite, but the intended post-merge H100 acceptance must show CUDA available/selected before closing `KI-003`.

- [ ] **Step 5: Verify default Layer B SKIP**

```bash
python -m unittest tests.test_full_pipeline_real_runtime
```

Expected: one explicit skip.

- [ ] **Step 6: Verify normal development coverage**

```bash
python -m unittest tests.test_full_pipeline_harness tests.test_full_pipeline_real_runtime
```

Expected without real-runtime environment: harness PASS, Layer B SKIP.

Do not claim Layer B PASS in Codex/cloud if the real model/FixedTest/GPU environment is absent.

- [ ] **Step 7: Commit Task 4**

```bash
git add tests/smoke/full_pipeline_harness.py tests/test_full_pipeline_harness.py tests/test_full_pipeline_real_runtime.py
git commit -m "test: add opt-in real-model pipeline smoke"
```

---

### Task 5: Document both profiles and preserve known-issue semantics

**Files:**
- Modify: `.codex/workflows.md`
- Modify: `.codex/known_issues.md`
- Modify: `.codex/memory.md`
- Modify: `tests/test_project_docs.py`

- [ ] **Step 1: Write documentation RED**

Extend `tests/test_project_docs.py` so current-state docs must contain:

```text
TCP_RUN_FULL_PIPELINE_SMOKE
TCP_RUN_REAL_PIPELINE_SMOKE
KI-003
KI-002
python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler
```

Run:

```bash
python -m unittest tests.test_project_docs
```

Expected RED before documentation update.

- [ ] **Step 2: Update `.codex/workflows.md`**

Document POSIX and PowerShell Layer A commands and the Layer B variables/commands without embedding any local user's actual filesystem paths. State that ordinary `python -m unittest discover -s tests` discovers both smoke modules as explicit opt-in skips.

- [ ] **Step 3: Update `.codex/known_issues.md`**

Keep `KI-003` Open. Record:

- Layer A exists and must pass when enabled;
- Layer B exists but needs post-merge real model/GPU acceptance evidence;
- resolution gate remains Layer A PASS + Layer B PASS + temporary WorkPool isolation + final `_rdy_for_Spike` + H100/CUDA evidence for the intended acceptance.

Keep `KI-002` Open and state that these smoke profiles do not exercise WeiTech queue acquisition/processed delivery.

- [ ] **Step 4: Update `.codex/memory.md`**

Keep exactly ten durable outcomes. Update outcome 10 to state that the compile gate remains restored, isolated root smoke exists, `KI-003` awaits real-runtime acceptance, and `KI-002` remains Open.

- [ ] **Step 5: GREEN docs**

```bash
python -m unittest tests.test_project_docs
```

- [ ] **Step 6: Commit Task 5**

```bash
git add .codex tests/test_project_docs.py
git commit -m "docs: document full-pipeline smoke verification"
```

---

## Final Verification Before PR

- [ ] Fast smoke infrastructure:

```bash
python -m unittest tests.test_full_pipeline_harness tests.test_smoke_classifier
```

- [ ] Layer A enabled:

```bash
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
```

Use the PowerShell equivalent on Windows.

- [ ] Layer B default behavior:

```bash
python -m unittest tests.test_full_pipeline_real_runtime
```

Expected without real-runtime variables: explicit SKIP.

- [ ] Existing project/root/workpool/documentation gates:

```bash
python -m unittest \
  tests.test_project_docs \
  tests.test_package_layout \
  tests.test_tcf_main_characterization \
  tests.test_tcf_workpool_characterization \
  tests.test_classifier_stage \
  tests.test_result_combination_stage \
  tests.test_visualization_stage
```

- [ ] Full discovery:

```bash
python -m unittest discover -s tests
```

Expected: dependency-light tests PASS; Layer A and Layer B are skipped unless enabled.

- [ ] Canonical compile gate:

```bash
python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler
```

Expected exit status: `0`.

- [ ] Hygiene:

```bash
git diff --check
git status --short --branch
```

No `.smoke-runtime`, temporary WorkPool, classifier marker, or model-facade artifact may remain in the working tree.

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

Completion report fields:

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

1. genuine RED/GREEN for harness, dispatcher, classifier, and Layer A;
2. whether Layer A exposed a production integration regression; if yes, stop-state evidence rather than a hidden workaround;
3. Layer A root command, exit code, final workspace suffix, and canonical artifacts;
4. proof only the model inference child was intercepted;
5. proof repository default WorkPool was unchanged;
6. normal-discovery SKIP behavior for both smoke modules;
7. Layer B implementation status and whether it was executable in the implementation environment;
8. confirmation the real model is accessed through a temporary facade instead of being used as writable modelDir;
9. full unittest discovery result;
10. canonical compileall exit status;
11. `git diff --check` and working-tree state;
12. confirmation `KI-003` remains Open pending post-merge real-runtime acceptance;
13. confirmation `KI-002` remains Open.

End with:

```text
Full-pipeline smoke implementation ready for post-merge review and H100 real-runtime acceptance.
```

---

## Post-Merge H100 Acceptance Procedure

Run against the reviewed/merged `main` baseline.

PowerShell:

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
expected classifier/combination/visualization completion evidence exists
external FixedTest/model source snapshots unchanged
temporary WorkPool cleaned after assertions
```

Only after that evidence is reviewed should a small follow-up documentation change move `KI-003` to Recently Resolved. `KI-002` remains independent and Open.
