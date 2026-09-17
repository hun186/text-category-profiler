# Full-Pipeline Smoke Test Design v1

## Metadata

- Repository: `hun186/text-category-profiler`
- Authoritative hosted baseline at design time: `98d8a9bc7b4492e7de6355a77b0cbfebe2fea57a`
- Baseline meaning: merge commit of PR #83 (`fix: resolve KI-004 compile blockers`)
- Date: 2026-09-17
- Status: Approved for implementation planning
- Supersedes: none
- Related known issues: `KI-002`, `KI-003`

## Problem Statement

The repository now has strong dependency-light characterization and unit coverage, but that coverage does not prove that the real root command can launch the real child entrypoints and complete the filesystem handoff chain. Recent manual runtime execution exposed this gap directly: lightweight tests passed while real execution found unresolved runtime bindings in `DatasetConverter.py` and later a module-scope/layout regression in `Test_result_Vis.py`.

The user has now successfully exercised the real command:

```text
python TCFMain.py -p 8059 -ts y
```

against a real FixedTest/model environment. That experience must become a reproducible, isolated, automatable smoke test so the same class of regression is detected before manual runtime use.

Existing tests remain necessary but insufficient:

- `tests/test_tcf_main_characterization.py` proves root sequencing with fake subprocesses.
- `tests/test_dataconverter_fixture_integration.py` proves a small Stage 1 worker/split/TSV flow.
- Stage-specific suites prove Stage 2–4 lifecycle boundaries in isolation.
- `tests/test_tcf_workpool_characterization.py` proves important WorkPool policies with temporary directories.

None of those runs the canonical root command through all child Python entrypoints as real subprocesses.

## Goals

1. Add a reproducible smoke profile that starts from the canonical root CLI and launches the canonical child scripts through the same shell boundaries used in production.
2. Isolate the default smoke from real WorkPool, production FixedTest directories, real model output directories, network services, and hosted Dash servers.
3. Keep DataConverter, RunClassfier, CombineTestResult, and Test_result_Vis entrypoints real. Do not replace those stages with mocks.
4. Replace only the expensive/non-deterministic model inference child with a deterministic smoke classifier in the hermetic profile.
5. Add a second opt-in real-runtime profile that uses a real model and FixedTest source while still writing mutable pipeline state into a temporary WorkPool.
6. Treat any failure revealed by the real root/child pipeline as a genuine integration regression. Do not bypass a failure merely to make the smoke green.
7. Provide explicit evidence gates for resolving `KI-003` while leaving `KI-002` open until isolated root-level WorkPool acquisition/delivery coverage exists.

## Non-Goals

This design does not:

- benchmark inference speed or accuracy;
- train a model;
- test Elasticsearch;
- test SDSMS-specific merge behavior;
- test WeiTech queue acquisition/destructive delivery in the first KI-003 smoke;
- start a long-running Dash server;
- require an H100 for the hermetic profile;
- add a production `--smoke` CLI option;
- add a hidden production behavior mode merely for tests;
- replace existing unit/characterization suites;
- close `KI-002` solely because the new smoke uses a temporary WorkPool.

## Design Principle: Real Boundaries, Minimal Substitution

The smoke must preserve the boundaries that previously hid regressions.

Required execution shape:

```text
real subprocess
  -> TCFMain.py
     -> shell command -> DatasetConverter/DataConverter.py
     -> shell command -> BertScript/RunClassfier.py
        -> shell command -> model inference child
     -> shell command -> BertScript/CombineTestResult.py
     -> shell command -> BertScript/Test_result_Vis.py
     -> root delivery/completion
```

Layer A may substitute only the model inference child invoked by RunClassfier. It must not directly call `PipelineOrchestrator.run()` with mocked stage functions.

## Two-Layer Smoke Architecture

### Layer A — Hermetic full-pipeline smoke

Purpose: deterministic root-to-final-handoff integration verification without a real GPU/model.

It runs the real root command and real Stage 1–4 entrypoint scripts. It uses:

- a temporary WorkPool;
- a committed tiny FixedTest fixture;
- a committed tiny taxonomy fixture;
- a committed tiny model-metadata fixture;
- `nProcess=1` and `nProcessSPC=1`;
- non-hosted visualization (`-TRVHost False`);
- no dataset removal/backup cleanup before assertions;
- no real network service;
- a PATH-level Python-command shim that intercepts only `BertScript/TextClassification_transformers.py`.

All other `python ...` child commands are forwarded to the same real interpreter used to start the smoke.

Layer A is opt-in and executes only when:

```text
TCP_RUN_FULL_PIPELINE_SMOKE=1
```

Without that variable, `tests.test_full_pipeline_smoke` must be discovered as an explicit skip with an actionable message.

### Layer B — Opt-in real-runtime smoke

Purpose: verify the same root pipeline with the real Pytorch classifier/model runtime.

It:

- executes only when `TCP_RUN_REAL_PIPELINE_SMOKE=1`;
- uses the real root CLI and real Stage 1–4 child scripts;
- installs no classifier interception shim;
- uses a temporary WorkPool and non-hosted Stage 4;
- forces `nProcess=1` and `nProcessSPC=1`;
- captures stdout/stderr and final artifacts;
- must terminate with root exit code 0 to count as successful evidence.

Required environment variables:

```text
TCP_REAL_MODEL_DIR
TCP_REAL_FIXED_TEST_DIR
TCP_REAL_TOPIC_TREE_DIR
TCP_REAL_TOPIC_TREE_FILES
```

Optional:

```text
TCP_REAL_MODEL_TYPE
TCP_REAL_PIPELINE_TIMEOUT_SECONDS
```

Defaults:

```text
TCP_REAL_MODEL_TYPE=PytorchXLM
TCP_REAL_PIPELINE_TIMEOUT_SECONDS=1800
```

`TCP_REAL_TOPIC_TREE_FILES` is the same comma-separated form accepted by `--TopicTreeFiles`, for example the user’s current `TopicTree.csv,TopicTree_AK4.csv` environment.

The real-runtime profile formalizes the user’s successful manual run rather than replacing it with mocks.

## Exact Test Infrastructure Files

Create:

```text
tests/smoke/__init__.py
tests/smoke/full_pipeline_harness.py
tests/smoke/python_dispatch.py
tests/smoke/smoke_classifier.py
tests/test_full_pipeline_smoke.py
tests/test_full_pipeline_real_runtime.py
```

Fixture root:

```text
tests/fixtures/full_pipeline_smoke/
```

Documentation updates:

```text
.codex/workflows.md
.codex/known_issues.md
.codex/memory.md
```

Production files should not change merely to make the smoke possible. If the smoke exposes a real integration defect, fix that defect separately with a focused RED test and the smallest relevant production change.

## Hermetic Test Harness

`tests/smoke/full_pipeline_harness.py` owns smoke orchestration only. It must not import and invoke the four pipeline stages directly.

Responsibilities:

1. Create a temporary runtime root and temporary WorkPool.
2. Build the canonical root command with explicit FixedTest, taxonomy, model metadata, WorkPool, process-count, model-type, port, and execution-time values.
3. Set isolation-oriented environment variables (`TEMP`, `TMP`, `TMPDIR`, `HOME`, Hugging Face cache variables) to temporary locations.
4. Put a cross-platform `python` shim at the front of `PATH` for Layer A only.
5. Execute `TCFMain.py` with `subprocess.run(..., check=False, capture_output=True, text=True)`.
6. Use a Layer A timeout of 180 seconds.
7. Return a structured result with command, exit code, stdout, stderr, temporary WorkPool, final workspace candidates, and artifact paths.
8. Produce bounded failure diagnostics that identify the failing stage without dumping unbounded logs.
9. Clean the runtime root after assertions.

Legacy shell rendering does not quote path arguments. The harness must therefore use a whitespace-free runtime root. It may use the system temp directory when that path is whitespace-free; otherwise it must create a temporary `.smoke-runtime` directory beneath the repository root, clean it after the test, and ensure that directory is ignored by Git.

## PATH-Level Python Dispatch

`tests/smoke/python_dispatch.py` is invoked by the generated platform wrapper named `python`.

Wrapper forms:

- POSIX: executable command named `python`.
- Windows: `python.cmd`, relying on normal `PATHEXT` command resolution.

The wrapper forwards its argv to `python_dispatch.py` together with the absolute real interpreter path through a test-only environment variable.

Dispatch behavior:

```text
if requested script normalizes to BertScript/TextClassification_transformers.py:
    execute tests/smoke/smoke_classifier.py with the original classifier args
else:
    execute the real sys.executable with the original argv unchanged
```

The dispatcher must preserve child exit codes.

The root process itself is started with `sys.executable`; it is not started through the shim.

No production `SMOKE_MODE`, production environment branch, alternate root renderer, or alternate Stage 2 renderer is introduced.

## Deterministic Smoke Classifier

`tests/smoke/smoke_classifier.py` accepts the existing Pytorch classifier command arguments needed by the current renderer, including:

```text
-ts
-mdlDir
-BertDataDir
-mdlType
-ZeroShot
-MaxSeqLen
-SaveOptimizer
```

Unknown forwarded arguments that are part of the current classifier command should be parsed compatibly rather than causing the smoke backend to diverge from the production command surface.

Behavior:

1. Open the actual generated `<BertDataDir>/test.sql3`.
2. Read the actual test-row order/count required for predictions.
3. Read the actual `<BertDataDir>/TopicAnalysis_LabelList.txt` copied by RunClassfier.
4. Produce canonical `<BertDataDir>/test_results.tsv` with exactly one valid label for each test row. Deterministic cycling through the sorted label list is sufficient.
5. Write a test-only invocation marker to the path supplied in `TCP_SMOKE_CLASSIFIER_MARKER` so the harness can prove the model child was intercepted exactly once.
6. Exit 0.

It must not fabricate Stage 3 or Stage 4 artifacts.

## Committed Smoke Fixtures

### FixedTest

Path:

```text
tests/fixtures/full_pipeline_smoke/fixed_test/Using/
```

Use at least two valid production taxonomy labels and at least one short UTF-8 document per label. Prefer labels already represented by repository InfoScore data, such as labels proven by the current runtime taxonomy, rather than inventing test-only taxonomy semantics.

Each text must remain shorter than the smoke `MaxSeqLength` so the existing short-message tokenization path returns before loading a Hugging Face tokenizer.

### Taxonomy

Path:

```text
tests/fixtures/full_pipeline_smoke/taxonomy/TopicTree_smoke.csv
```

The file must use the exact format accepted by the current production `ClassesTree` loader. Implementation derives the file shape by reading that loader/current taxonomy tests; it must not introduce a test-only taxonomy parser.

It contains exactly the labels required by the smoke FixedTest plus any structural parent/root row the production loader requires.

### Model metadata

Path:

```text
tests/fixtures/full_pipeline_smoke/model/TopicAnalysis_LabelList.txt
```

It contains exactly the smoke classifier labels and no weights/checkpoints.

## Canonical Layer A Root Command

Use fixed smoke port:

```text
18059
```

Use fixed execution ID because every run has a unique temporary WorkPool:

```text
20990101000000
```

Equivalent root command:

```text
<sys.executable> TCFMain.py
  -p 18059
  -ts y
  -TRVHost False
  -WPRoot <temporary WorkPool>
  -FTPath <repo>/tests/fixtures/full_pipeline_smoke/fixed_test/Using
  -TopicTreeDir <repo>/tests/fixtures/full_pipeline_smoke/taxonomy
  -TopicTreeFiles TopicTree_smoke.csv
  -mdlDir <repo>/tests/fixtures/full_pipeline_smoke/model
  -mdlType PytorchXLM
  -nProc 1
  -nProcSPC 1
  -RMBertData False
  -exectime 20990101000000
```

Boolean spelling must match the existing parser. The port is not opened because `TRVHost=False`; it remains part of the legacy dataset naming contract.

## Required Layer A Assertions

A PASS proves:

1. Root process exits 0.
2. stdout/stderr contain no uncaught traceback.
3. DataConverter produced non-empty `test.tsv` and `test.sql3` under the temporary WorkPool.
4. RunClassfier ran as a real child entrypoint.
5. The classifier marker proves the smoke classifier intercepted exactly one model inference child.
6. `test_results.tsv` contains exactly one prediction per test row.
7. CombineTestResult created its canonical verification/combined output artifacts.
8. Test_result_Vis ran in non-hosted mode.
9. The final workspace ends with `_rdy_for_Spike`.
10. No `_is_running_DataConverter`, `_is_running_RunClassfier`, `_is_running_CombineTestResult`, or `_is_running_TestResultVis` workspace remains.
11. The repository default `WorkPool` directory has the same directory-entry snapshot before and after the smoke; the test must not create the smoke execution dataset there.
12. The temporary runtime root is removed after assertions.

Assertions prefer canonical files and suffixes over log text. Log text is diagnostic support only.

## Root Double-Visualization Rule

The current root compatibility contract renders and executes two visualization commands. The smoke must exercise both; it must not mock, skip, or special-case the second invocation.

If Layer A reveals that the first non-hosted visualization completes to `_rdy_for_Spike` and the second then fails, treat that as a genuine integration defect:

1. add a focused RED reproducing the actual root/runtime failure;
2. determine the intended compatibility semantics from source/history;
3. make the smallest behavior-preserving production correction;
4. rerun Layer A.

The harness must never hide this failure.

## Layer B Root Command

Layer B reuses the same harness without the PATH shim.

It passes:

```text
-TRVHost False
-WPRoot <temporary WorkPool>
-FTPath %TCP_REAL_FIXED_TEST_DIR%
-TopicTreeDir %TCP_REAL_TOPIC_TREE_DIR%
-TopicTreeFiles %TCP_REAL_TOPIC_TREE_FILES%
-mdlDir %TCP_REAL_MODEL_DIR%
-mdlType %TCP_REAL_MODEL_TYPE%
-nProc 1
-nProcSPC 1
-RMBertData False
```

The source model, FixedTest, and taxonomy directories are inputs; pipeline datasets and stage handoffs remain under the temporary WorkPool.

Layer B assertions are the Layer A assertions except there is no classifier interception marker. Instead, diagnostics must prove the production `TextClassification_transformers.py` command ran. Record whether PyTorch selected CUDA or CPU. For the intended H100 acceptance run, completion evidence must record CUDA execution.

The test must snapshot the FixedTest source tree before/after and fail if the pipeline mutates it.

## Test Discovery Policy

Layer A module:

```text
tests/test_full_pipeline_smoke.py
```

Default discovery behavior: `SKIP` with message:

```text
set TCP_RUN_FULL_PIPELINE_SMOKE=1 to run isolated root full-pipeline smoke
```

Execution command:

```text
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
```

Layer B module:

```text
tests/test_full_pipeline_real_runtime.py
```

Default discovery behavior: `SKIP` with message explaining the required real-runtime environment variables.

Execution is enabled only by:

```text
TCP_RUN_REAL_PIPELINE_SMOKE=1
```

The workflow documents PowerShell and POSIX forms separately.

## Failure Handling and Diagnostics

Layer A timeout: 180 seconds.

Layer B timeout: `TCP_REAL_PIPELINE_TIMEOUT_SECONDS`, default 1800 seconds.

Timeout is a smoke failure. The harness must terminate the root process and its child process tree as safely as the platform permits.

On failure, include:

- root command with sensitive external paths reduced to diagnostic-safe forms where appropriate;
- exit code or timeout;
- bounded stdout/stderr tail;
- temporary WorkPool path;
- remaining stage/workspace suffixes;
- discovered intermediate artifacts.

Do not swallow root fail-fast exceptions or translate non-zero results into PASS.

## Isolation Guarantees

Both layers explicitly redirect mutable pipeline state.

Required:

- WorkPool root: temporary;
- dataset directories: under temporary WorkPool;
- TEMP/TMP/TMPDIR: temporary;
- HOME: temporary where platform-safe;
- Hugging Face caches: temporary in Layer A;
- hosted Dash server: disabled;
- dataset removal/backup cleanup: disabled through `-RMBertData False`;
- Layer A FixedTest/taxonomy/model inputs: committed read-only fixtures;
- Layer B FixedTest/taxonomy/model inputs: external inputs, not WorkPool destinations.

Layer A must never auto-discover a developer’s production FixedTest or model directory.

## Documentation and Known-Issue Semantics

Update `.codex/workflows.md` with exact PowerShell and POSIX commands for Layer A and Layer B.

### KI-003

Do not resolve `KI-003` when only Layer A is implemented.

Move `KI-003` to Recently Resolved only after all are true on a reviewed/merged baseline:

1. Layer A passes.
2. Layer B passes using a real model and FixedTest source.
3. Layer B mutable pipeline state is isolated to a temporary WorkPool.
4. Evidence records root exit 0 and final `_rdy_for_Spike` completion.
5. For the intended H100 acceptance run, evidence records CUDA model execution.
6. `.codex/workflows.md` contains repeatable commands for both layers.

### KI-002

`KI-002` remains Open unless separate work adds and proves isolated root-level WeiTech WorkPool acquisition plus processed-delivery lifecycle coverage.

Layer A/B temporary WorkPool evidence is useful but does not exercise the destructive queue transitions described by KI-002.

## Acceptance Criteria

Implementation is accepted when:

- Layer A executes the real root and all four canonical stage entrypoints as subprocesses;
- only the model inference child is substituted in Layer A;
- Layer A uses no production smoke flag/branch;
- all Layer A mutable pipeline state is isolated;
- Layer A reaches exit 0 and `_rdy_for_Spike` with canonical artifacts;
- current double visualization behavior is exercised rather than hidden;
- Layer B exists and can run the real model path without source edits;
- both modules default to explicit actionable skips when their opt-in variables are absent;
- workflows document exact commands;
- `KI-003` closes only after reviewed Layer B PASS evidence;
- `KI-002` stays Open unless separately proven.

## Verification Strategy

TDD applies at three levels:

1. Harness tests: root command construction, whitespace-safe runtime root choice, PATH dispatch, timeout/failure diagnostics, artifact discovery, and default WorkPool non-mutation check.
2. Layer A subprocess smoke with deterministic classifier.
3. Layer B real-runtime smoke on the actual model/FixedTest/GPU host.

Existing gates remain mandatory:

```text
python -m unittest discover -s tests
python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler
```

Explicit smoke verification:

```text
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
TCP_RUN_REAL_PIPELINE_SMOKE=1 ... python -m unittest tests.test_full_pipeline_real_runtime
```

Completion reports must distinguish PASS from intentional SKIP and must not claim KI-003 resolved until Layer B evidence exists.
