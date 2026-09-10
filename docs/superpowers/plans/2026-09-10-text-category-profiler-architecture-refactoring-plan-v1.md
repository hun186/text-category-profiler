# text-category-profiler Architecture Refactoring Implementation Plan v1

## Document control

| Item | Value |
| --- | --- |
| Repository | `hun186/text-category-profiler` |
| Branch | Target: `main`; inspected local branch: `work` |
| Actual baseline HEAD | Local source: `e745a55fef4412ab516ae1146248fbb1872f9a34`. A direct `git ls-remote https://github.com/hun186/text-category-profiler.git refs/heads/main` check was attempted on 2026-09-10 but the environment's CONNECT tunnel returned HTTP 403. Therefore hosted HEAD could not be independently re-confirmed; the inspected local commit exactly matches the user-supplied hosted `main` HEAD. Every implementation phase must re-run the baseline gate below before editing. |
| Design path | `docs/superpowers/specs/2026-09-10-text-category-profiler-architecture-refactoring-design-v1.md` |
| Design version | Architecture Refactoring Design v1 |
| Design source baseline | `aac3453a15faa06e1d9415c2c127a15f7af35092` |
| Plan version | Architecture Refactoring Implementation Plan v1 |
| Supersedes | None |
| Source inspected | `TCFMain.py`; `TCF_Params/TCFParameters.py`; `text_category_profiler/pipeline/TCF_utils.py`; all files in `DatasetConverter/adapters/` and `DatasetConverter/core/`; `DatasetConverter/DataConverter.py`, `config.py`, and `stage.py`; `BertScript/RunClassfier.py`, `CombineTestResult.py`, and `Test_result_Vis.py`; all files under `tests/`; `.codex/project.md`, `memory.md`, `architecture.md`, `contracts.md`, `workflows.md`, and `known_issues.md`; Design v1. Imports/callers were followed into pipeline, logging, filesystem, taxonomy, data, and concurrency helpers where required to identify boundaries. |
| Scope | A behavior-preserving, incremental refactor of root configuration, shell-process execution, orchestration, work-pool/filesystem lifecycle, and Stage 2–4 activation boundaries, with characterization first and compatibility entrypoints retained. |
| Explicit non-goals | Model replacement; TensorFlow/PyTorch migration; tokenizer or taxonomy behavior changes; output-schema or CLI redesign; HTTP/API, LangGraph, or async rewrite; unrelated broad cleanup; first-round package relocation; removal of `TCFMain.py` or canonical stage scripts; shell/argv modernization. |

> **Execution workflow:** Follow the `superpowers:writing-plans` discipline: execute one checkbox at a time, run the stated RED before implementation, make only the minimum change needed for GREEN, run the regression command, review the diff, and commit at every checkpoint. This environment did not expose a `superpowers:writing-plans` skill file, so this document records the workflow explicitly rather than claiming that an unavailable skill was loaded.

## Baseline gate (repeat at the start of every PR)

```bash
git fetch origin main
git rev-parse origin/main
git status --short --branch
```

Expected: record the real `origin/main` SHA; start from a clean branch based on it. If it differs from `e745a55f...`, inspect `git diff e745a55f..origin/main --` for every file named in the relevant phase and update only source-dependent details in this plan. Stop and raise a **Design blocker** if the approved four-stage model, compatibility entrypoints, filesystem handoffs, or legacy-shell premise no longer exists. A missing `origin`/network is a baseline blocker for implementation, not permission to invent a SHA.

## Source findings that constrain implementation

1. `TCFMain.py` currently sequences `DataConvert` → `RunClassfier` → conditional `ArticleAnalysis`; `ArticleAnalysis` runs `CombineTestResult` → `TestResultVis` → conditional SDSMS merge → `BackupAndClean`.
2. `run_stage_command()` uses `subprocess.run(command, shell=True, check=False)` and raises `RuntimeError` on non-zero return. `TestResultVis()` deliberately makes one base invocation and then a second invocation after appending non-empty WeiTech options; this plan preserves both.
3. `TCF_Params/TCFParameters.py` parses process arguments at import time. `setArguments()` reparses, normalizes paths/execution time, renames WeiTech input, mutates `FinalOfferedOutputFNrePatList`, and discovers process counts.
4. `ClassfierOptionParser(argv=None)` owns the canonical options. Training forces test off; when both are false, test becomes true. `convert_to_args_str()` iterates namespace insertion order, skips only the empty string, and forwards `False`, `None`, zero, and spaces without new quoting.
5. Stage handoffs are directory suffixes such as `_is_running_DataConverter`, `_rdy_for_RunClassfier`, `_is_running_RunClassfier`, `_rdy_for_CombineTestResult`, and later visualization states. Dataset artifacts include `train.tsv`, `dev.tsv`, `test.tsv`, `test.sql3`, `dataset_total_with_filename_FixedTest.sql3`, and result patterns.
6. DatasetConverter already has the approved dependency-light `StagePlan → StageContext` boundary and typed configuration slices. This program consumes that stage as-is and adds regression/import-direction gates; it must not fold those modules back into `DataConverter.py`.
7. Stage 2–4 scripts still execute large bodies under `if __name__ == '__main__'`, mix activation/filesystem/model work, and contain internal `os.system()` calls. Root process isolation comes first; stage-internal commands are migrated later behind the same legacy-shell runner without changing command strings.
8. `.codex/workflows.md` now identifies `python -m unittest discover -s tests` and the DatasetConverter fixture command, while `.codex/known_issues.md` still says no canonical smoke test exists. This is documentation drift, not an architecture blocker.

## Program invariants and PR gates

- Preserve option names, aliases, defaults, namespace keys/order, bool normalization, canonical script paths, shell strings, `shell=True`, output names, stage suffixes, stage order, conditions, logging intent, and failure propagation.
- No real model, GPU, Elasticsearch, database service, or WorkPool is used by tests. All destructive behavior uses `tempfile.TemporaryDirectory`, fixtures, fake runners, and fake filesystem/ownership adapters.
- A phase may merge only after its targeted tests, `python -m unittest discover -s tests`, DatasetConverter fixture where indicated, `python -m compileall` for changed Python modules, and `git diff --check` pass.
- Do not use pytest, lint, typecheck, CI, or full GPU/model commands: none is established by the inspected repository.
- Each phase is a separate reviewable PR. Rebase/re-run the baseline gate between phases; later phases consume only merged interfaces.

---

# Phase 0 / PR 1 — Compatibility safety net and current-state reconciliation

## Task 1: Freeze CLI parsing and argument-forwarding contracts

**Goal**

Create executable coverage for all canonical option strings, aliases/defaults, train/test normalization, and exact namespace-to-command forwarding before production extraction begins.

**Files**

* **Inspect:** `text_category_profiler/pipeline/TCF_utils.py`, all callers of `ClassfierOptionParser` and `convert_to_args_str`
* **Create:** `tests/test_tcf_cli_contract.py`
* **Modify:** none
* **Test:** `tests/test_tcf_cli_contract.py`

**Existing behavior protected**

Every `add_argument` option/alias/default; training forcing `test=False`; false/false becoming `test=True`; insertion-order rendering by `convert_to_args_str()`; skipping only `''`; preserving values including `False`, `0`, and `None`; lack of added shell quoting.

**Interfaces**

* **Consumes:** `ClassfierOptionParser(argv=list[str])`, `convert_to_args_str(argparse.Namespace)`
* **Produces:** a frozen executable CLI/forwarding contract only; no product API

**Steps**

* [ ] Write `ClassifierCliContractTests.test_canonical_aliases_and_defaults_are_stable`, `test_train_disables_test`, `test_false_train_and_test_normalizes_to_test`, and `test_convert_to_args_str_preserves_legacy_iteration_and_filtering`. Encode the complete parser action table as explicit tuples `(dest, option_strings, default)` so removal or alias/default drift is visible in review.
* [ ] Run RED: `python -m unittest tests.test_tcf_cli_contract`. Expected failure: `ModuleNotFoundError` until the new characterization module exists; after creating the test module, all assertions must immediately describe and pass against baseline source. If an assertion fails, correct the observation—not production code—and document the discovered baseline in the test.
* [ ] Implement minimal change: no product change. Complete the characterization expectations using `parser._actions` obtained by patching `argparse.ArgumentParser.parse_args` only if needed to inspect metadata; call the public parser for behavioral assertions.
* [ ] Run GREEN: `python -m unittest tests.test_tcf_cli_contract`. Expected: all tests pass without filesystem/model activation.
* [ ] Run regression tests: `python -m unittest discover -s tests`.
* [ ] Update documentation if required: none unless source observation contradicts `.codex/contracts.md`; if so, correct only `CONTRACT-CLI-001` in this same commit.
* [ ] Commit checkpoint: `git add tests/test_tcf_cli_contract.py .codex/contracts.md && git commit -m "test: characterize CLI forwarding contracts"` (omit unchanged docs).

**Acceptance criteria:** The test fails on any missing/renamed alias or changed default and compares the exact forwarded string for an ordered Namespace containing empty string, false, zero, `None`, and a path with a space.

## Task 2: Freeze root orchestration, command, failure, and visualization behavior

**Goal**

Characterize root behavior without importing heavyweight stage runtimes or launching child processes.

**Files**

* **Inspect:** `TCFMain.py`, `TCF_Params/TCFParameters.py`, `text_category_profiler/core/log_display.py`
* **Create:** `tests/test_tcf_main_characterization.py`
* **Modify:** none
* **Test:** `tests/test_tcf_main_characterization.py`

**Existing behavior protected**

Exact Stage 1–4 command prefixes and forwarded args; canonical order; `ArticleAnalysis` only when `args.test is True`; SDSMS merge only for `SDSMS`/`SDSMS_Prediction`; non-zero abort; train exit after classifier; and both `TestResultVis()` invocations, including a second identical command when all WeiTech paths are empty.

**Interfaces**

* **Consumes:** current functions `run_stage_command`, `DataConvert`, `RunClassfier`, `CombineTestResult`, `TestResultVis`, `ArticleAnalysis`
* **Produces:** fake-call traces and exact expected command strings

**Steps**

* [ ] Write tests `test_run_stage_command_uses_legacy_shell_flags`, `test_nonzero_stage_aborts_with_command_and_code`, `test_canonical_stage_order_for_test_run`, `test_article_analysis_is_skipped_when_test_false`, `test_sdsms_merge_is_conditional`, `test_stage_command_prefixes_and_forwarding`, and `test_visualization_runs_base_then_weitech_command_even_when_options_empty`. Load `TCFMain.py` with `unittest.mock.patch.dict(sys.modules, ...)` lightweight fakes before import; use a recording completed-process fake.
* [ ] Run RED: `python -m unittest tests.test_tcf_main_characterization`. Expected failure is missing test module first; once authored, any failure means the harness has accidentally activated a dependency or the expected observation is wrong. Do not alter production behavior to make characterization pass.
* [ ] Implement minimal change: test harness/fakes only. Use temporary paths for the dataset-file check and patch `exit_program`, timing, loggers, conformer, directory picker, and merger.
* [ ] Run GREEN: `python -m unittest tests.test_tcf_main_characterization`. Expected call trace: DataConverter, RunClassfier, CombineTestResult, visualization base, visualization WeiTech; a non-zero fake raises before the next call.
* [ ] Run regression tests: `python -m unittest discover -s tests`.
* [ ] Update documentation if required: add no conclusions about double invocation being a defect; it remains a compatibility behavior.
* [ ] Commit checkpoint: `git add tests/test_tcf_main_characterization.py && git commit -m "test: characterize root pipeline behavior"`.

**Acceptance criteria:** Tests neither invoke `subprocess.run` for real nor touch a real WorkPool, and they prove the second visualization invocation rather than deleting it.

## Task 3: Freeze handoff, work selection, output patterns, backup, and cleanup

**Goal**

Capture destructive and naming behavior in isolated directories before introducing filesystem adapters.

**Files**

* **Inspect:** `TCFMain.py`, `TCF_Params/TCFParameters.py`, `text_category_profiler/pipeline/TCF_utils.py`, `text_category_profiler/core/utilities.py`, stage suffix handling in all canonical scripts
* **Create:** `tests/test_tcf_workpool_characterization.py`, `tests/fixtures/workpool/.gitkeep`
* **Modify:** none
* **Test:** `tests/test_tcf_workpool_characterization.py`

**Existing behavior protected**

Reverse-sorted WeiTech workID selection restricted to IDs also present in the WorkPool; move to sibling `AutoBertClassify_Processing`; dataset names/suffixes; `FinalOfferedOutputFNrePatList` base order and one-time SDSMS extension per fresh module state; `RemoveBertDataDir` and non-empty workID backup conditions; move to `AutoBertClassify_Processed`; Linux chown path selection; validation/error propagation.

**Interfaces**

* **Consumes:** `DataConvert`, `BackupAndClean`, `setArguments`, `datasetDirOutputDirPickers`, `TaskConnector`
* **Produces:** temporary-directory artifact/call traces

**Steps**

* [ ] Write tests named `test_weitech_selects_newest_matching_id_and_moves_to_processing`, `test_no_weitech_job_aborts`, `test_dataset_picker_preserves_name_and_stage_suffixes`, `test_final_output_patterns_base_and_sdsms`, `test_remove_flag_controls_general_backup`, `test_work_id_controls_delivery_backup_and_processed_move`, and `test_linux_ownership_calls_are_preserved`. Patch command execution and use only temporary trees.
* [ ] Run RED: `python -m unittest tests.test_tcf_workpool_characterization`. Expected initial missing-module failure; after authoring, correct test setup until it passes current behavior. Never point an argument at repository or external WorkPool directories.
* [ ] Implement minimal change: test/fixture only; create fresh module loads for mutable-global assertions so test order does not hide repeated-extension behavior.
* [ ] Run GREEN: `python -m unittest tests.test_tcf_workpool_characterization`.
* [ ] Run regression tests: `python -m unittest tests.test_dataconverter_fixture_integration && python -m unittest discover -s tests`.
* [ ] Update documentation if required: none.
* [ ] Commit checkpoint: `git add tests/test_tcf_workpool_characterization.py tests/fixtures/workpool/.gitkeep && git commit -m "test: characterize workpool lifecycle"`.

**Acceptance criteria:** No test path escapes its temporary root; movement, backup, delete, rename, and chown are represented by fixture state or fakes; all named handoff strings and patterns are explicit assertions.

## Task 4: Reconcile the documented lightweight smoke test

**Goal**

Resolve the verified current-state contradiction without changing runtime behavior.

**Files**

* **Inspect:** `.codex/workflows.md`, `.codex/known_issues.md`, `tests/test_project_docs.py`
* **Create:** none
* **Modify:** `.codex/known_issues.md`, `tests/test_project_docs.py`
* **Test:** `tests/test_project_docs.py`

**Existing behavior protected**

The lightweight suite and DatasetConverter fixture remain distinguished from unavailable full model/GPU validation.

**Interfaces**

* **Consumes:** documented commands verified in repository
* **Produces:** resolved `KI-001` wording/status that says lightweight tests exist but full pipeline validation remains unavailable

**Steps**

* [ ] Write failing test `ProjectDocumentationTests.test_known_issues_agrees_with_lightweight_smoke_command`, requiring the known-issues file to mention `python -m unittest discover -s tests` and not claim that no test/smoke command exists.
* [ ] Run RED: `python -m unittest tests.test_project_docs.ProjectDocumentationTests.test_known_issues_agrees_with_lightweight_smoke_command`. Expected failure because `KI-001` still makes the stale claim.
* [ ] Implement minimal change: move `KI-001` to Recently Resolved with its verified lightweight command and add a narrowly worded open issue, only if useful, that full model/WorkPool smoke validation remains unavailable. Keep `KI-002` open.
* [ ] Run GREEN: repeat the targeted command; expected pass.
* [ ] Run regression tests: `python -m unittest discover -s tests && git diff --check`.
* [ ] Update documentation if required: this task is the documentation update.
* [ ] Commit checkpoint: `git add .codex/known_issues.md tests/test_project_docs.py && git commit -m "docs: reconcile lightweight test status"`.

**Acceptance criteria:** Workflows and known issues no longer contradict one another, and neither claims a full model test exists.

**PR 1 gate:** Review only tests/fixtures/current-state docs. No product source changes. Confirm all required characterization targets from Design §18 are asserted.

---

# Phase 1 / PR 2 — Root configuration boundary

## Task 5: Separate root Parse/Normalize/Validate/Plan from activation

**Goal**

Stop `TCF_Params.TCFParameters` from parsing CLI at import while retaining Namespace compatibility and the current `setArguments()` behavior through a thin activation wrapper.

**Files**

* **Inspect:** `TCF_Params/TCFParameters.py`, `DatasetConverter/config.py`, `DatasetConverter/stage.py`, all imports of `ROOTPATHList`, `FinalOfferedOutputFNrePatList`, and `setArguments`
* **Create:** `text_category_profiler/pipeline/configuration.py`, `tests/test_pipeline_configuration.py`
* **Modify:** `TCF_Params/TCFParameters.py`, `TCFMain.py`
* **Test:** `tests/test_pipeline_configuration.py`, Tasks 1–3 suites

**Existing behavior protected**

Canonical Namespace; path slash normalization; default execution time; SDSMS extraction task; output patterns; WeiTech-input rename/replacement-directory creation; process counts; platform/debug/DRN root policy; legacy imports.

**Interfaces**

* **Consumes:** `ClassfierOptionParser(argv)`, existing constants, injected clock/platform/process-count providers
* **Produces:** frozen `PipelinePlan(args, root_paths, final_output_patterns)` with defensive copies; `activate_pipeline_runtime(plan, filesystem, process_source)` returning `PipelineContext`; compatibility `setArguments(argv=None)` returning the activated Namespace

The names are justified by the approved DatasetConverter pattern and existing `StagePlan`/`StageContext`; `PipelinePlan` avoids pretending the root is another data stage.

**Steps**

* [ ] Write failing tests `test_import_does_not_parse_process_argv`, `test_build_pipeline_plan_has_no_filesystem_or_process_side_effects`, `test_sdsms_plan_owns_fresh_output_patterns`, `test_activation_renames_weitech_input_and_discovers_process_counts`, and `test_legacy_set_arguments_returns_namespace`. Add an AST/import subprocess guard like `test_dataconverter_import_boundary.py`.
* [ ] Run RED: `python -m unittest tests.test_pipeline_configuration`. Expected failures: missing module/classes and import-time parser call remains.
* [ ] Implement minimal change: move pure policies into `configuration.py`; remove module-level `args = ClassfierOptionParser()`; compute compatibility `ROOTPATHList` lazily only through plan construction; keep constants and a `setArguments(argv=None)` wrapper. Inject filesystem/clock/process providers only at activation. Do not convert every argparse field into a dataclass.
* [ ] Run GREEN: `python -m unittest tests.test_pipeline_configuration tests.test_tcf_cli_contract tests.test_tcf_main_characterization tests.test_tcf_workpool_characterization`.
* [ ] Run regression tests: `python -m unittest tests.test_dataconverter_fixture_integration && python -m unittest discover -s tests && python -m compileall TCFMain.py TCF_Params text_category_profiler/pipeline`.
* [ ] Update documentation if required: update `.codex/architecture.md` and `.codex/contracts.md` to describe the new root boundary while retaining CLI authority in `ClassfierOptionParser`.
* [ ] Commit checkpoint: `git add TCF_Params/TCFParameters.py TCFMain.py text_category_profiler/pipeline/configuration.py tests/test_pipeline_configuration.py .codex/architecture.md .codex/contracts.md && git commit -m "refactor: separate root configuration activation"`.

**Acceptance criteria:** Importing `TCFParameters` does not parse argv, rename/create paths, calculate process counts, or mutate output patterns; `setArguments()` at the compatibility boundary reproduces characterization.

---

# Phase 2 / PR 3 — Legacy-compatible process and command boundaries

## Task 6: Introduce the shared legacy shell process runner

**Goal**

Place existing subprocess semantics behind a dependency-light interface before changing any command owner.

**Files**

* **Inspect:** all `subprocess.run`/`os.system` occurrences in root and canonical stage scripts
* **Create:** `text_category_profiler/execution/__init__.py`, `text_category_profiler/execution/process.py`, `tests/test_process_runner.py`
* **Modify:** `TCFMain.py`
* **Test:** `tests/test_process_runner.py`, `tests/test_tcf_main_characterization.py`

**Existing behavior protected**

String commands, `shell=True`, `check=False`, returned completed object, non-zero RuntimeError message, logging callback, and immediate downstream abort.

**Interfaces**

* **Consumes:** command string and stage name
* **Produces:** `ProcessRunner` protocol with `run(command: str, stage_name: str)`; `LegacyShellProcessRunner(run_process=subprocess.run, failure_reporter=stage_failed)`

**Steps**

* [ ] Write failing tests `test_protocol_accepts_string_command`, `test_legacy_runner_calls_subprocess_with_shell_true_check_false`, `test_nonzero_result_reports_and_raises`, and `test_root_compatibility_function_delegates_to_default_runner`.
* [ ] Run RED: `python -m unittest tests.test_process_runner`. Expected failure: `text_category_profiler.execution.process` does not exist.
* [ ] Implement minimal change: implement protocol/adapter; make `TCFMain.run_stage_command(CMD, stage_name, runner=None)` delegate to a legacy runner while preserving two-argument callers.
* [ ] Run GREEN: `python -m unittest tests.test_process_runner tests.test_tcf_main_characterization`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall TCFMain.py text_category_profiler/execution`.
* [ ] Update documentation if required: record execution dependency direction in `.codex/architecture.md`; explicitly state argv-list is deferred.
* [ ] Commit checkpoint: `git add TCFMain.py text_category_profiler/execution tests/test_process_runner.py .codex/architecture.md && git commit -m "refactor: isolate legacy shell execution"`.

**Acceptance criteria:** Root has one replaceable runner seam and exact shell behavior remains; no argv list, quoting change, retry, or async execution is introduced.

## Task 7: Represent root stage commands without changing rendered strings

**Goal**

Make root command assembly pure and independently testable.

**Files**

* **Inspect:** command construction in `TCFMain.py`, `convert_to_args_str`
* **Create:** `text_category_profiler/pipeline/commands.py`, `tests/test_stage_commands.py`
* **Modify:** `TCFMain.py`
* **Test:** `tests/test_stage_commands.py`, Task 2 suite

**Existing behavior protected**

`python` executable spelling, canonical relative script paths, exact forwarded argument order/text, visualization WeiTech aliases and append order, including unchanged second-command behavior.

**Interfaces**

* **Consumes:** stage name, script path, Namespace, optional literal suffixes
* **Produces:** frozen `StageCommand(stage, executable, script, forwarded_args, suffixes=())` with `render_shell()`; builders `dataset_command`, `classifier_command`, `combine_command`, `visualization_commands`

**Steps**

* [ ] Write failing tests comparing every builder's output byte-for-byte with Task 2 captured commands, including spaces/unquoted paths and zero/false values.
* [ ] Run RED: `python -m unittest tests.test_stage_commands`. Expected failure: command module and `StageCommand` are absent.
* [ ] Implement minimal change: create immutable representation and pure builders; change root stage functions to pass `.render_shell()` to the runner. `visualization_commands()` must return a two-element tuple.
* [ ] Run GREEN: `python -m unittest tests.test_stage_commands tests.test_tcf_main_characterization tests.test_process_runner`.
* [ ] Run regression tests: `python -m unittest discover -s tests && git diff --check`.
* [ ] Update documentation if required: add command specification to `.codex/architecture.md`; external contracts stay unchanged.
* [ ] Commit checkpoint: `git add TCFMain.py text_category_profiler/pipeline/commands.py tests/test_stage_commands.py .codex/architecture.md && git commit -m "refactor: describe root stage commands"`.

**Acceptance criteria:** Characterization strings are identical and no model/stage process starts in command tests.

---

# Phase 3 / PR 4 — Orchestrator and isolated WorkPool lifecycle

## Task 8: Extract canonical sequencing into a pipeline orchestrator

**Goal**

Make `TCFMain.py` a compatibility composition root and transfer sequence/conditions to an injected orchestrator without transferring stage implementation details.

**Files**

* **Inspect:** `TCFMain.py`, configuration and command interfaces from PRs 2–3
* **Create:** `text_category_profiler/pipeline/orchestrator.py`, `tests/test_pipeline_orchestrator.py`
* **Modify:** `TCFMain.py`
* **Test:** `tests/test_pipeline_orchestrator.py`, root characterization

**Existing behavior protected**

Four-stage order; test condition; train short-circuit/exit semantics; SDSMS merger placement; dependent-stage abort; whole-run timing and final summary intent.

**Interfaces**

* **Consumes:** `PipelineContext`; injected callable stage ports `convert`, `classify`, `combine`, `visualize`, `merge`, `deliver`
* **Produces:** `PipelineOrchestrator.run()` call trace/return; no cross-stage imports

**Steps**

* [ ] Write failing tests `test_test_pipeline_runs_four_stages_in_order`, `test_non_test_pipeline_stops_after_classifier`, `test_failure_prevents_following_stages`, `test_sdsms_merge_precedes_delivery`, and `test_stage_ports_do_not_import_stage_implementations`.
* [ ] Run RED: `python -m unittest tests.test_pipeline_orchestrator`. Expected failure: orchestrator is absent.
* [ ] Implement minimal change: injected callables and explicit run method only; retain existing root functions as adapters and `main(argv=None)` as parse/activate/compose/run. Move no stage-specific filesystem or command code into orchestrator.
* [ ] Run GREEN: `python -m unittest tests.test_pipeline_orchestrator tests.test_tcf_main_characterization`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall TCFMain.py text_category_profiler/pipeline`.
* [ ] Update documentation if required: update architecture dependency arrows and root entrypoint description.
* [ ] Commit checkpoint: `git add TCFMain.py text_category_profiler/pipeline/orchestrator.py tests/test_pipeline_orchestrator.py .codex/architecture.md && git commit -m "refactor: extract pipeline orchestration"`.

**Acceptance criteria:** `TCFMain.py` composes boundaries; orchestrator knows stages only through ports; all ordering/conditional/failure tests pass.

## Task 9: Extract WorkPool and delivery filesystem adapters

**Goal**

Move selection/movement/backup/cleanup/chown policy behind explicit boundaries while preserving validation and errors.

**Files**

* **Inspect:** `TCFMain.DataConvert`, `BackupAndClean`, `TCF_utils.TaskConnector`, filesystem helpers
* **Create:** `text_category_profiler/filesystem/__init__.py`, `text_category_profiler/filesystem/legacy.py`, `text_category_profiler/pipeline/workpool.py`, `tests/test_workpool_manager.py`
* **Modify:** `TCFMain.py`
* **Test:** `tests/test_workpool_manager.py`, Task 3 suite

**Existing behavior protected**

Reverse-sort/membership work selection; processing/processed directories; failure when no candidate; exact backup patterns and conditions; general cleanup flag; Linux ownership calls; existing caught final move exception behavior; dataset-output validation remains at stage boundary.

**Interfaces**

* **Consumes:** frozen `WorkPoolPlan` derived from PipelinePlan; injected `FileSystem` operations and existing backup callback
* **Produces:** `WorkPoolManager.acquire()` returning selected workID; `DeliveryManager.backup_and_complete(dataset_dir)`; `LegacyFileSystem` adapter

**Steps**

* [ ] Write failing tests using `TemporaryDirectory` and `RecordingFileSystem`: `test_acquire_selects_latest_matching_work`, `test_acquire_fails_before_command_when_empty`, `test_complete_uses_exact_output_patterns`, `test_remove_flag_controls_cleanup`, `test_complete_moves_processing_to_processed`, `test_linux_chown_scope_matches_baseline`, and `test_adapter_propagates_validation_and_backup_errors`.
* [ ] Run RED: `python -m unittest tests.test_workpool_manager`. Expected failure: modules/interfaces absent.
* [ ] Implement minimal change: thin wrappers over `os`, `shutil`, `MKDIR`, `OSWALK`, `chownPath`, and `BackupAIPredictResultAndDelTempFile`; preserve call ordering/catches exactly. Inject managers into root stage adapters.
* [ ] Run GREEN: `python -m unittest tests.test_workpool_manager tests.test_tcf_workpool_characterization tests.test_pipeline_orchestrator`.
* [ ] Run regression tests: `python -m unittest tests.test_dataconverter_fixture_integration && python -m unittest discover -s tests && git diff --check`.
* [ ] Update documentation if required: update `.codex/architecture.md` and `KI-002` evidence/workaround only; do not mark KI-002 resolved until isolated root integration exists.
* [ ] Commit checkpoint: `git add TCFMain.py text_category_profiler/filesystem text_category_profiler/pipeline/workpool.py tests/test_workpool_manager.py .codex/architecture.md .codex/known_issues.md && git commit -m "refactor: isolate workpool lifecycle"`.

**Acceptance criteria:** Production adapters retain operations/errors and all tests are isolated. No real WorkPool path appears in test arguments.

---

# Phase 4 / PR 5 — Stage 2 and Stage 3 boundaries

## Task 10: Add classifier planning/activation and isolate model commands

**Goal**

Turn `RunClassfier.py` into a compatibility entrypoint over testable plan/activation/main functions without changing model/tokenizer logic.

**Files**

* **Inspect:** full `BertScript/RunClassfier.py`, `TextClassification_transformers.py`, TF batch template, output consumers
* **Create:** `BertScript/classifier_stage.py`, `tests/test_classifier_stage.py`
* **Modify:** `BertScript/RunClassfier.py`
* **Test:** `tests/test_classifier_stage.py`, `tests/test_combine_test_result_model_types.py`, `tests/test_model_directory_resolution.py`

**Existing behavior protected**

Workspace suffix transitions; model selection; count DB names; label/model copying; TF and PyTorch command strings/redirection/background flags; optimizer/max sequence options; stable-file waits; result moves; training/test branches and logs.

**Interfaces**

* **Consumes:** Namespace, directory picker, filesystem adapter, ProcessRunner, model/output adapters
* **Produces:** `ClassifierPlan(args, dataset_dir, output_dir, command)` before activation; `activate_classifier(plan, ...)`; `run_classifier_stage(context)`; compatibility `main(argv=None)`

**Steps**

* [ ] Write failing tests `test_plan_preserves_pytorch_command`, `test_plan_preserves_tf_template_flags`, `test_activation_renames_ready_to_running`, `test_nonzero_model_command_aborts_before_handoff`, `test_test_success_handoffs_to_combine`, and `test_training_keeps_background_semantics`. Use fake DB counts, stable-file adapter, filesystem, and runner.
* [ ] Run RED: `python -m unittest tests.test_classifier_stage`. Expected failure: module/interfaces absent.
* [ ] Implement minimal change: extract only command/planning/activation seams; use `LegacyShellProcessRunner` for former `os.system` command calls while preserving exact rendered strings and legacy handling. Leave ML imports/algorithms and canonical file path intact; `RunClassfier.py` delegates under its main guard.
* [ ] Run GREEN: `python -m unittest tests.test_classifier_stage tests.test_combine_test_result_model_types tests.test_model_directory_resolution`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall BertScript/RunClassfier.py BertScript/classifier_stage.py`.
* [ ] Update documentation if required: document internal stage API and retained script contract in architecture/contracts.
* [ ] Commit checkpoint: `git add BertScript/RunClassfier.py BertScript/classifier_stage.py tests/test_classifier_stage.py .codex/architecture.md .codex/contracts.md && git commit -m "refactor: isolate classifier stage lifecycle"`.

**Acceptance criteria:** No model/GPU runs in tests; exact command/suffix/artifact behavior is covered; no TensorFlow, PyTorch, tokenizer, or model behavior is modernized.

## Task 11: Add result-combination planning/activation boundary

**Goal**

Separate workspace activation and artifact validation from combination logic while retaining the canonical script.

**Files**

* **Inspect:** full `BertScript/CombineTestResult.py`, classifier outputs, visualization inputs
* **Create:** `BertScript/result_combination_stage.py`, `tests/test_result_combination_stage.py`
* **Modify:** `BertScript/CombineTestResult.py`
* **Test:** `tests/test_result_combination_stage.py`, model-type tests

**Existing behavior protected**

Ready/running suffix; DB glob `dataset_total_with_filename*.sql3`; `TopicAnalysis_LabelList.txt`, `test.sql3`, `test_results.tsv`; model-type mapping; warnings/errors; produced combined artifacts; next-stage handoff.

**Interfaces**

* **Consumes:** Namespace, filesystem/artifact adapters, existing combination functions
* **Produces:** `ResultCombinationPlan`; `activate_result_combination(plan, ...)`; `run_result_combination_stage(context)`; compatibility `main(argv=None)`

**Steps**

* [ ] Write failing tests `test_plan_records_canonical_input_names`, `test_activation_renames_ready_to_running`, `test_missing_sources_preserves_warning_contract`, `test_model_type_mapping_is_unchanged`, `test_failure_prevents_visualization_handoff`, and `test_success_uses_existing_handoff_suffix` using tiny temporary SQLite/TSV fixtures or fakes where pandas would otherwise dominate.
* [ ] Run RED: `python -m unittest tests.test_result_combination_stage`. Expected missing module/interfaces.
* [ ] Implement minimal change: extract lifecycle and call the unchanged computational functions; dependency-load pandas/matplotlib only when execution reaches computation. Keep the script path/main guard.
* [ ] Run GREEN: `python -m unittest tests.test_result_combination_stage tests.test_combine_test_result_model_types`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall BertScript/CombineTestResult.py BertScript/result_combination_stage.py`.
* [ ] Update documentation if required: document Stage 3 boundary and unchanged artifacts.
* [ ] Commit checkpoint: `git add BertScript/CombineTestResult.py BertScript/result_combination_stage.py tests/test_result_combination_stage.py .codex/architecture.md .codex/contracts.md && git commit -m "refactor: isolate result combination stage"`.

**Acceptance criteria:** Result computation/output schema is unchanged; lifecycle is testable without a model or real work pool; Stage 3 never calls Stage 4.

---

# Phase 5 / PR 6 — Visualization boundary and hygiene gates

## Task 12: Add visualization planning/activation boundary without changing Dash behavior

**Goal**

Reduce `Test_result_Vis.py`'s entrypoint/runtime coupling while leaving its large visualization and callback implementation in place.

**Files**

* **Inspect:** full `BertScript/Test_result_Vis.py`, local `Test_result_Vis_utils.py`, `VisParameters*.py`, `pages/`, delivery consumers
* **Create:** `BertScript/visualization_stage.py`, `tests/test_visualization_stage.py`
* **Modify:** `BertScript/Test_result_Vis.py`
* **Test:** `tests/test_visualization_stage.py`, root double-invocation characterization

**Existing behavior protected**

Dataset suffix transitions; artifact names; hosted/non-hosted conditions; WeiTech input/output behavior; filesystem operations; server command and kill command strings; callbacks/layout; root's two process invocations.

**Interfaces**

* **Consumes:** Namespace, filesystem and ProcessRunner adapters, lazily supplied visualization application factory
* **Produces:** `VisualizationPlan`; `activate_visualization(plan, ...)`; `run_visualization_stage(context)`; compatibility `main(argv=None)`

**Steps**

* [ ] Write failing tests `test_plan_preserves_host_and_weitech_options`, `test_activation_uses_canonical_suffix`, `test_nonhosted_path_does_not_start_server`, `test_hosted_path_preserves_kill_and_server_commands`, `test_failure_does_not_mark_stage_complete`, and `test_importing_stage_plan_does_not_import_dash`.
* [ ] Run RED: `python -m unittest tests.test_visualization_stage`. Expected missing module/interfaces.
* [ ] Implement minimal change: isolate only entrypoint plan/activation and shell calls; import Dash-heavy implementation lazily. Do not edit callbacks, layout, schema, visualization algorithms, or root invocation count.
* [ ] Run GREEN: `python -m unittest tests.test_visualization_stage tests.test_tcf_main_characterization tests.test_stage_commands`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall BertScript/Test_result_Vis.py BertScript/visualization_stage.py`.
* [ ] Update documentation if required: architecture/contracts record the internal seam and unchanged external entrypoint.
* [ ] Commit checkpoint: `git add BertScript/Test_result_Vis.py BertScript/visualization_stage.py tests/test_visualization_stage.py .codex/architecture.md .codex/contracts.md && git commit -m "refactor: isolate visualization stage lifecycle"`.

**Acceptance criteria:** Planning imports without Dash; fake-runner tests cover shell calls; UI behavior is untouched; the root still launches visualization twice as characterized.

## Task 13: Enforce dependency direction and finalize current-state documentation

**Goal**

Add narrow architecture guards and reconcile current-state docs after all boundaries exist; do not relocate packages.

**Files**

* **Inspect:** all new modules, canonical entrypoints, `tests/test_package_layout.py`, `.codex/*.md` current-state files
* **Create:** none
* **Modify:** `tests/test_package_layout.py`, `.codex/architecture.md`, `.codex/contracts.md`, `.codex/workflows.md`, `.codex/known_issues.md`, `.codex/memory.md`
* **Test:** `tests/test_package_layout.py`, `tests/test_project_docs.py`

**Existing behavior protected**

Compatibility paths, DatasetConverter's split modules and import-light boundary, stage-to-stage independence, no giant shared utility, established safe commands only.

**Interfaces**

* **Consumes:** final import graph and verified commands
* **Produces:** AST dependency tests and accurate current-state documentation

**Steps**

* [ ] Write failing tests `test_shared_boundaries_do_not_import_stage_implementations`, `test_stage_implementations_do_not_import_next_stage`, `test_datasetconverter_stage_plan_modules_remain_present`, and `test_legacy_entrypoints_remain_present`. Make the first two fail against a temporary forbidden import fixture or current violation before correcting imports; do not encode style preferences beyond Design v1.
* [ ] Run RED: `python -m unittest tests.test_package_layout`. Expected failure on at least the newly exposed dependency violation; if current graph already passes, verify test sensitivity with `self.subTest` against a synthetic AST string, then remove no production behavior.
* [ ] Implement minimal change: correct only imports that violate approved arrows; update docs to actual state. Mark `KI-002` resolved only if Task 9 provides repeatable isolated lifecycle coverage; otherwise retain it with updated workaround.
* [ ] Run GREEN: `python -m unittest tests.test_package_layout tests.test_project_docs`.
* [ ] Run regression tests: `python -m unittest tests.test_dataconverter_fixture_integration && python -m unittest discover -s tests && python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler && git diff --check`.
* [ ] Update documentation if required: this task performs final reconciliation. Keep `.codex/memory.md` to at most ten durable outcomes and do not add a transcript.
* [ ] Commit checkpoint: `git add tests/test_package_layout.py .codex/architecture.md .codex/contracts.md .codex/workflows.md .codex/known_issues.md .codex/memory.md && git commit -m "docs: record refactored pipeline boundaries"`.

**Acceptance criteria:** Dependency gates match Design v1, DatasetConverter remains intact, all entrypoint paths exist, docs list only verified commands, and no repository/package relocation was introduced.

---

## Deferred follow-ups (not part of these six PRs)

These require separate design/review after the characterization program is stable:

1. Replace shell strings with argv-list execution and remove `shell=True`.
2. Decide, with product evidence, whether `TestResultVis()`'s second invocation is intentional or a defect.
3. Broader package relocation or deletion of compatibility entrypoints.
4. ML framework/model/tokenizer modernization, retry frameworks, output schema changes, CLI redesign, APIs, LangGraph, or async execution.

## Dependency ordering rationale

The safety net lands alone so reviews can validate observations independently of refactoring. Root configuration follows because import-time parsing/global mutation makes every later boundary harder to load safely. The legacy process adapter precedes command specifications and orchestration so fake execution can prove exact compatibility. Orchestration precedes WorkPool extraction because lifecycle ownership becomes explicit only after sequence ownership is isolated. Stage 2 and Stage 3 then reuse stable runner/filesystem patterns; visualization is last because its import graph and UI runtime are largest. Hygiene checks close the program rather than triggering an early repository move.

## Design/source reconciliation, assumptions, and blockers

- **No architecture blocker found** in inspected local source. The current source strengthens Design v1's premise: DatasetConverter has already advanced beyond the design baseline and must be preserved.
- **Baseline verification risk:** hosted GitHub could not be reached from this environment. Implementation must not proceed until a future session records the actual `origin/main` SHA. Local `work` is not named `main`, although its HEAD equals the supplied hosted SHA.
- **Minor source/design detail:** current root execution already uses `subprocess.run` with non-zero checking, while stage internals still use `os.system`. The plan first preserves root semantics, then migrates only stage command calls through the legacy runner in stage-specific PRs.
- **Mutable-global risk:** repeated `setArguments()` calls can repeatedly extend `FinalOfferedOutputFNrePatList`; characterize fresh-process/current behavior, then make each `PipelinePlan` own fresh patterns without changing one-run output.
- **Heavy import risk:** Stage 2–4 modules can require unavailable ML/Dash/data dependencies. Tests must load extracted plan modules with fakes/lazy imports and must not claim a full stage run.
- **Command quoting risk:** current forwarding is unsafe-looking but observable. Preserve it exactly; modernization is deferred.

## Final self-review checklist

- [ ] Every Design v1 acceptance area maps to Tasks 1–13 or an explicitly deferred follow-up.
- [ ] No task changes model, tokenizer, taxonomy, CLI, schemas, APIs, async behavior, or broad layout.
- [ ] Every task names concrete tests, interfaces, error expectations, and commands; no placeholder work remains.
- [ ] Names `PipelinePlan`, `PipelineContext`, `ProcessRunner`, `LegacyShellProcessRunner`, `StageCommand`, `PipelineOrchestrator`, `WorkPoolManager`, and stage plan/context functions are consistent.
- [ ] Every implementation task is RED → minimal implementation → GREEN → regression → checkpoint.
- [ ] CLI, forwarding, ordering, conditions, abort, names, work selection, patterns, backup/clean, commands, and visualization double invocation are protected before extraction.
- [ ] Destructive tests use temporary directories/fakes only.
- [ ] DatasetConverter `StagePlan → StageContext`, config, adapters, core modules, fixture, and dependency-light import tests remain intact.
- [ ] Each PR is independently usable/reviewable and keeps compatibility entrypoints.
