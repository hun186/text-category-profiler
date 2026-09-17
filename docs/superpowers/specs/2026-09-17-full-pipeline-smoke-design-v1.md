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

The repository now has strong dependency-light characterization and unit coverage, but that coverage does not prove that the real root command can launch the real child entrypoints and complete the filesystem handoff chain. The recent manual runtime sequence exposed this gap directly: lightweight tests passed while real execution found unresolved runtime bindings in `DatasetConverter.py` and later a module-scope/layout regression in `Test_result_Vis.py`.

The user has now successfully exercised the real command:

```text
python TCFMain.py -p 8059 -ts y
```

against a real FixedTest/model environment. That experience must be converted into a reproducible, isolated, automatable smoke test so the same class of regression is detected before manual runtime use.

Existing tests are necessary but insufficient:

- `tests/test_tcf_main_characterization.py` proves root sequencing with fake subprocesses.
- `tests/test_dataconverter_fixture_integration.py` proves a small Stage 1 worker/split/TSV flow.
- Stage-specific suites prove Stage 2–4 lifecycle boundaries in isolation.
- `tests/test_tcf_workpool_characterization.py` proves important WorkPool policies with temporary directories.

None of those runs the canonical root command through all child Python entrypoints as real subprocesses.

## Goals

1. Add a reproducible full-pipeline smoke profile that starts from the canonical root CLI and launches the canonical child scripts through the same shell boundaries used in production.
2. Make the default smoke isolated from real WorkPool, production FixedTest directories, real model output directories, network services, and hosted Dash servers.
3. Keep DataConverter, RunClassfier, CombineTestResult, and Test_result_Vis entrypoints real. Do not replace those stages with mocks.
4. Replace only the expensive/non-deterministic model inference child with a deterministic smoke classifier in the hermetic profile.
5. Add a second opt-in real-runtime profile that uses a real model/GPU and a real FixedTest source while still writing all mutable pipeline state into a temporary WorkPool.
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

The required execution shape is:

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

The hermetic profile may substitute only the model inference child invoked by RunClassfier. It must not directly call `PipelineOrchestrator.run()` with mocked stage functions, because that would repeat existing characterization coverage and would not catch direct-script/bootstrap/scope failures.

## Two-Layer Smoke Architecture

### Layer A — Hermetic full-pipeline smoke

Purpose: deterministic root-to-final-handoff integration verification without a real GPU/model.

It runs the real root command and real Stage 1–4 entrypoint scripts. It uses:

- a temporary WorkPool;
- a tiny committed FixedTest fixture;
- a tiny committed taxonomy fixture;
- a tiny committed model-metadata fixture;
- one process for normal work and one process for SPC work;
- non-hosted visualization (`-TRVHost False`);
- no cleanup/removal of the dataset during the assertion phase;
- no real network service;
- a test harness Python-command shim that intercepts only the expensive `BertScript/TextClassification_transformers.py` child invocation.

All other `python ...` child commands are forwarded to the same real interpreter used to start the smoke.

### Layer B — Opt-in real-runtime smoke

Purpose: verify the same root pipeline with the real PytorchXLM classifier/model runtime.

This profile:

- is skipped unless explicitly enabled;
- uses the real root CLI;
- uses real Stage 1–4 child scripts;
- does not install the classifier interception shim;
- accepts a real model directory and FixedTest directory from environment variables;
- still uses a temporary WorkPool and non-hosted Stage 4;
- forces `nProcess=1` and `nProcessSPC=1` for predictability;
- records stdout/stderr and final artifacts;
- must terminate with root exit code 0 to count as successful evidence.

The real-runtime profile formalizes the user’s successful manual experience rather than replacing it with mocks.

## Hermetic Test Harness

Create a focused helper module under tests, conceptually:

```text
tests/smoke/full_pipeline_harness.py
```

Responsibilities:

1. Create and clean a `TemporaryDirectory` for all mutable runtime state.
2. Build the root command with explicit paths so it cannot select a real WorkPool, FixedTest directory, or model directory by discovery.
3. Set isolation-oriented environment variables (`TEMP`, `TMP`, `TMPDIR`, `HOME`, Hugging Face cache variables where applicable) to temporary locations.
4. Create a cross-platform `python` command shim at the front of `PATH`.
5. Execute `TCFMain.py` with `subprocess.run(..., check=False, capture_output=True, text=True)` and a finite timeout.
6. Return a structured smoke result containing exit code, stdout, stderr, temporary WorkPool path, and discovered final workspace/artifacts.
7. On failure, preserve enough stdout/stderr in the assertion message to identify the failing stage and child command.

The harness must not import and call the four stages directly.

## Python Command Shim

Production root/stage command specifications intentionally use the literal executable name `python`. The smoke should exploit that existing seam rather than changing production command rendering.

The harness creates a temporary executable command named `python`:

- POSIX: executable shell wrapper or equivalent launcher named `python`.
- Windows: `python.cmd` (or another command form resolved by `cmd.exe`/`PATHEXT`).

Behavior:

```text
if requested script == BertScript/TextClassification_transformers.py:
    run the deterministic smoke classifier with the forwarded classifier arguments
else:
    exec the real sys.executable with the original arguments unchanged
```

The shim must preserve child exit codes.

The root process itself should be started with `sys.executable`, not the shim. The shim exists only because production child commands deliberately render `python ...`.

No production `SMOKE_MODE`, no production environment branch, and no alternate stage command renderer are introduced.

## Deterministic Smoke Classifier

Create a test-only script, conceptually:

```text
tests/smoke/smoke_classifier.py
```

It accepts the subset of classifier CLI arguments needed from the existing Pytorch command, including at minimum:

```text
-ts
-mdlDir
-BertDataDir
-mdlType
-ZeroShot
-MaxSeqLen
-SaveOptimizer
```

Behavior:

1. Open the actual generated `<BertDataDir>/test.sql3`.
2. Read the number/order of rows needed to produce a prediction for each test sample.
3. Read the actual `<BertDataDir>/TopicAnalysis_LabelList.txt` copied by RunClassfier.
4. Produce the canonical `<BertDataDir>/test_results.tsv` with exactly one valid label per test row.
5. Exit 0.

It must not fabricate downstream combined/visualization artifacts. Stage 3 and Stage 4 must create those themselves.

The smoke classifier tests command/lifecycle integration, not model quality.

## Committed Smoke Fixtures

Add a small fixture tree under:

```text
tests/fixtures/full_pipeline_smoke/
```

It contains:

### FixedTest fixture

A minimal `Using` tree with at least two taxonomy labels and short UTF-8 documents. Texts must be shorter than the configured `MaxSeqLength` so the current short-message tokenization path can return without loading a Hugging Face tokenizer.

The labels must use the same filename/directory conventions that the real FixedTest loader expects.

### Taxonomy fixture

A minimal topic-tree input accepted by the current production taxonomy loader and containing exactly the smoke labels required by the FixedTest fixture.

The fixture is intentionally small and deterministic; implementation must derive the exact CSV/file shape from the current `ClassesTree` loader rather than introduce a new parser.

### Smoke model metadata fixture

A read-only directory containing the metadata required by the real RunClassfier preparation path, especially `TopicAnalysis_LabelList.txt` with the smoke labels.

It does not contain real model weights or checkpoints because the expensive model child is intercepted in Layer A.

## Canonical Hermetic Root Command

The harness must build the equivalent of:

```text
<sys.executable> TCFMain.py
  -p <reserved smoke port>
  -ts y
  -TRVHost False
  -WPRoot <temporary WorkPool>
  -FTPath <fixture FixedTest/Using>
  -TopicTreeDir <fixture taxonomy directory>
  -TopicTreeFiles <fixture taxonomy filename>
  -mdlDir <fixture smoke model metadata directory>
  -mdlType PytorchXLM
  -nProc 1
  -nProcSPC 1
  -RMBertData False
  -exectime <unique deterministic-format smoke execution id>
```

The exact boolean spelling must match the current CLI parser.

The port must not matter for network serving because `TRVHost=False`; it remains present because the legacy dataset naming contract includes the port.

## Required Hermetic Assertions

A successful hermetic smoke must prove all of the following:

1. Root process exits 0.
2. stdout/stderr do not contain an uncaught traceback.
3. DataConverter child actually ran and produced a non-empty `test.tsv` and `test.sql3` inside the temporary WorkPool.
4. RunClassfier child actually ran; the smoke classifier child was invoked exactly once for the model inference command.
5. `test_results.tsv` exists and contains one prediction per test row.
6. CombineTestResult child actually ran and created its canonical verification/combined result artifacts.
7. Test_result_Vis child actually ran in non-hosted mode.
8. Final dataset workspace reaches the canonical `_rdy_for_Spike` suffix.
9. No `_is_running_DataConverter`, `_is_running_RunClassfier`, `_is_running_CombineTestResult`, or `_is_running_TestResultVis` workspace remains after success.
10. No mutable output is written into the real/default `WorkPool` selected by repository defaults.
11. The test cleans its temporary workspace after assertions.

Assertions should prefer canonical artifacts/suffixes over fragile log text. Log/stage text may be used only as supporting diagnostics.

## Root Double-Visualization Rule

The current root compatibility contract deliberately renders/runs two visualization commands. The smoke must not bypass the second invocation.

If a non-hosted root smoke reveals that the first Stage 4 invocation transitions the workspace to `_rdy_for_Spike` and the second invocation then fails, that is a real integration defect. The implementation must:

1. capture the failure with a focused regression test;
2. reconcile actual intended compatibility behavior;
3. apply the smallest behavior-preserving correction;
4. rerun the full root smoke.

The test harness must not silently skip, mock, or special-case the second Stage 4 invocation just to make the smoke pass.

## Real-Runtime Profile

Create an opt-in unittest module conceptually:

```text
tests/test_full_pipeline_real_runtime.py
```

Enable only when:

```text
TCP_RUN_REAL_PIPELINE_SMOKE=1
```

Required environment variables:

```text
TCP_REAL_MODEL_DIR
TCP_REAL_FIXED_TEST_DIR
```

Optional environment variable:

```text
TCP_REAL_MODEL_TYPE
```

Default model type: `PytorchXLM`.

This profile uses the same harness without the Python command shim. It uses the committed taxonomy fixture unless an implementation-proven reason requires an explicit taxonomy override.

It must still use:

```text
-TRVHost False
-WPRoot <temporary WorkPool>
-nProc 1
-nProcSPC 1
-RMBertData False
```

The source FixedTest/model directories are read-only inputs from the perspective of the test.

A real-runtime PASS requires:

- root exit 0;
- real model inference command executed rather than intercepted;
- final `_rdy_for_Spike` workspace present;
- expected classifier/combination/visualization artifacts present;
- no mutation of the source FixedTest directory;
- no pipeline dataset created under the repository’s default real WorkPool.

GPU presence is runtime evidence, not an unconditional code prerequisite; the test records whether PyTorch selected CUDA or CPU. For the intended H100 verification, CUDA execution evidence should be included in the completion report.

## Test Discovery Policy

The hermetic full-pipeline smoke is an integration smoke, not a lightweight unit test.

It should be explicitly runnable as:

```text
python -m unittest tests.test_full_pipeline_smoke
```

To avoid making the normal lightweight suite unexpectedly expensive, the implementation may gate actual subprocess execution behind:

```text
TCP_RUN_FULL_PIPELINE_SMOKE=1
```

If gated, the module must be discovered as a clear skip with an actionable message, not silently pass.

The project verification workflow must document the explicit command required for release/refactor runtime verification.

The real-runtime profile remains separately opt-in through `TCP_RUN_REAL_PIPELINE_SMOKE=1`.

## Failure Handling and Diagnostics

The harness must use a finite timeout. A timeout is a smoke failure and must terminate the full subprocess tree as safely as the platform permits.

On non-zero root exit, the test report must include:

- root command;
- exit code;
- tail or bounded sections of stdout/stderr;
- temporary WorkPool path during test execution;
- stage/workspace suffixes that remained.

Do not swallow root fail-fast exceptions or convert non-zero stage results into a passing smoke.

## Isolation Guarantees

Layer A and Layer B must both explicitly redirect mutable pipeline state to temporary locations.

At minimum:

- WorkPool root: temporary;
- execution-specific dataset directory: under temporary WorkPool;
- TEMP/TMP/TMPDIR: temporary;
- HOME: temporary where safe for the platform;
- Hugging Face caches: temporary for Layer A and preferably temporary for Layer B unless doing so would force a network download; Layer B may preserve an existing cache via an explicitly documented read-only/configured path;
- hosted Dash server: disabled;
- dataset removal/backup cleanup: disabled until after assertions.

The smoke must never auto-discover and use a developer’s production FixedTest or model directory in Layer A.

## Documentation and Known-Issue Semantics

Update `.codex/workflows.md` with two explicit commands:

```text
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
TCP_RUN_REAL_PIPELINE_SMOKE=1 ... python -m unittest tests.test_full_pipeline_real_runtime
```

Platform-specific environment syntax may be shown for PowerShell and POSIX shells.

### KI-003

Do not mark `KI-003` resolved when only Layer A is implemented.

`KI-003` can move to Recently Resolved only after all of these are true on a reviewed/merged baseline:

1. Hermetic root full-pipeline smoke passes.
2. Real-runtime opt-in smoke passes using a real model and FixedTest source.
3. The real-runtime smoke writes mutable pipeline state only to a temporary WorkPool.
4. Evidence records root exit 0 and final `_rdy_for_Spike` completion.
5. The workflow documents how to repeat both profiles.

### KI-002

`KI-002` remains Open after KI-003 unless the implementation separately adds and proves isolated root-level WeiTech WorkPool acquisition and processed-delivery lifecycle coverage.

The new temporary WorkPool smoke is useful evidence for root isolation, but it does not by itself exercise the destructive queue/processed transitions described by KI-002.

## Expected File Shape

Likely new files:

```text
tests/smoke/__init__.py
tests/smoke/full_pipeline_harness.py
tests/smoke/smoke_classifier.py
tests/test_full_pipeline_smoke.py
tests/test_full_pipeline_real_runtime.py
tests/fixtures/full_pipeline_smoke/...
```

Likely documentation changes:

```text
.codex/workflows.md
.codex/known_issues.md
.codex/memory.md
```

Production files should not need changes merely to support the smoke.

If the smoke exposes a real integration defect, that defect must be fixed in the smallest relevant production file with a focused RED test before the root smoke is made green.

## Acceptance Criteria

The implementation is accepted when:

- Layer A executes the real root and all four canonical stage entrypoints as subprocesses;
- only the model inference child is substituted in Layer A;
- all mutable pipeline state is isolated under temporary paths;
- Layer A reaches exit 0 and `_rdy_for_Spike` with canonical intermediate/final artifacts;
- the existing root double-visualization behavior is exercised rather than hidden;
- Layer B exists as an explicit opt-in real-model smoke using the same root path;
- Layer B can be run on the user’s model/GPU host without editing source code;
- documentation records exact repeatable commands;
- `KI-003` is closed only after real-runtime PASS evidence exists;
- `KI-002` remains Open unless separately proven.

## Verification Strategy

Implementation should use TDD at three levels:

1. Harness unit tests for command construction, PATH shim dispatch, timeout/failure diagnostics, and artifact discovery.
2. Hermetic subprocess smoke with deterministic classifier.
3. Opt-in real-runtime smoke on a host with the actual model/FixedTest environment.

The existing lightweight suite and canonical compile gate remain required regression gates.

At minimum, final implementation verification includes:

```text
python -m unittest tests.test_full_pipeline_smoke
python -m unittest tests.test_full_pipeline_real_runtime
python -m unittest discover -s tests
python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler
```

For the two smoke modules, the report must distinguish PASS from intentional SKIP caused by the opt-in environment variables.
