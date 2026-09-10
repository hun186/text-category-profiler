# text-category-profiler Architecture Refactoring Implementation Plan v1.1

## Document control

| Item | Value |
| --- | --- |
| Repository | `hun186/text-category-profiler` |
| Branch | Target: `main`; inspected local branch: `work` |
| Actual baseline HEAD | Local source: `6f9d1e5931ffe0595584d3cf536976b84799eeb5` (PR #67 merge commit), matching the review-confirmed hosted `main` baseline supplied for this correction. A fresh `git ls-remote https://github.com/hun186/text-category-profiler.git refs/heads/main` attempt on 2026-09-10 was blocked by the environment's CONNECT tunnel (HTTP 403), so hosted HEAD could not be independently fetched. Every implementation phase must re-run the baseline gate below before editing. |
| Design path | `docs/superpowers/specs/2026-09-10-text-category-profiler-architecture-refactoring-design-v1.md` |
| Design version | Architecture Refactoring Design v1 |
| Design source baseline | `aac3453a15faa06e1d9415c2c127a15f7af35092` |
| Plan version | Architecture Refactoring Implementation Plan v1.1 |
| Supersedes | Architecture Refactoring Implementation Plan v1 |
| Source inspected | `TCFMain.py`; `TCF_Params/TCFParameters.py`; `text_category_profiler/pipeline/TCF_utils.py`; all files in `DatasetConverter/adapters/` and `DatasetConverter/core/`; `DatasetConverter/DataConverter.py`, `config.py`, and `stage.py`; `BertScript/RunClassfier.py`, `CombineTestResult.py`, and `Test_result_Vis.py`; all files under `tests/`; `.codex/project.md`, `memory.md`, `architecture.md`, `contracts.md`, `workflows.md`, and `known_issues.md`; Design v1. Imports/callers were followed into pipeline, logging, filesystem, taxonomy, data, and concurrency helpers where required to identify boundaries. |
| Scope | A behavior-preserving, incremental refactor of root configuration, shell-process execution, orchestration, work-pool/filesystem lifecycle, and Stage 2–4 activation boundaries, with characterization first and compatibility entrypoints retained. |
| Explicit non-goals | Model replacement; TensorFlow/PyTorch migration; tokenizer or taxonomy behavior changes; output-schema or CLI redesign; HTTP/API, LangGraph, or async rewrite; unrelated broad cleanup; first-round package relocation; removal of `TCFMain.py` or canonical stage scripts; shell/argv modernization. |

## Writing-plan header

- **Goal:** Deliver six independently reviewable, behavior-preserving refactoring PRs that separate root configuration, command/process execution, orchestration, WorkPool/filesystem lifecycle, and Stage 2–4 activation boundaries without changing externally observable behavior.
- **Architecture:** Retain the approved four-stage pipeline and compatibility entrypoints; apply Parse/Normalize/Validate/Plan before activation, pure command specifications, injected orchestration ports, policy-aware process execution, isolated filesystem adapters, and the existing DatasetConverter `StagePlan → StageContext` precedent.
- **Tech Stack:** Python scripts and `unittest`; TensorFlow/PyTorch classifier commands; Dash/Plotly visualization; SQLite/file handoffs; shell-compatible legacy commands.
- **Spec:** `docs/superpowers/specs/2026-09-10-text-category-profiler-architecture-refactoring-design-v1.md` — **Architecture Refactoring Design v1** remains authoritative and unchanged.
- **Global Constraints:** Preserve CLI, command strings, stage ordering, handoff names, artifacts, per-call-site failure semantics, DatasetConverter architecture, and external compatibility. Use no real model/GPU/service/WorkPool in tests. Do not redesign the architecture, widen scope, create Design v2, or unify legacy failure semantics in this program.

> **Execution workflow:** Characterization-only Tasks 1–3 use **observe baseline → write characterization → baseline PASS → sensitivity check → restore → PASS**; absence of a not-yet-created test module is not RED evidence. Tasks that actually change implementation continue to use genuine **RED → minimal implementation → GREEN → regression → checkpoint**. Never modify production source merely to manufacture test sensitivity. This environment did not expose a `superpowers:writing-plans` skill file, so this document records the workflow explicitly rather than claiming that an unavailable skill was loaded.

## Baseline gate (repeat at the start of every PR)

```bash
git fetch origin main
git rev-parse origin/main
git status --short --branch
```

Expected: record the real `origin/main` SHA; start from a clean branch based on it. If it differs from `6f9d1e5...`, inspect `git diff 6f9d1e5..origin/main --` for every file named in the relevant phase and update only source-dependent details in this plan. Stop and raise a **Design blocker** if the approved four-stage model, compatibility entrypoints, filesystem handoffs, or legacy-shell premise no longer exists. A missing `origin`/network is a baseline blocker for implementation, not permission to invent a SHA.

## Source findings that constrain implementation

1. `TCFMain.py` currently sequences `DataConvert` → `RunClassfier` → conditional `ArticleAnalysis`; `ArticleAnalysis` runs `CombineTestResult` → `TestResultVis` → conditional SDSMS merge → `BackupAndClean`.
2. `run_stage_command()` uses `subprocess.run(command, shell=True, check=False)` and raises `RuntimeError` on non-zero return. `TestResultVis()` deliberately makes one base invocation and then a second invocation after appending non-empty WeiTech options; this plan preserves both.
3. `TCF_Params/TCFParameters.py` parses process arguments at import time. `setArguments()` reparses, normalizes paths/execution time, renames WeiTech input, mutates `FinalOfferedOutputFNrePatList`, and discovers process counts.
4. `ClassfierOptionParser(argv=None)` owns the canonical options. Training forces test off; when both are false, test becomes true. `convert_to_args_str()` iterates namespace insertion order, skips only the empty string, and forwards `False`, `None`, zero, and spaces without new quoting.
5. Stage handoffs are directory suffixes such as `_is_running_DataConverter`, `_rdy_for_RunClassfier`, `_is_running_RunClassfier`, `_rdy_for_CombineTestResult`, and later visualization states. Dataset artifacts include `train.tsv`, `dev.tsv`, `test.tsv`, `test.sql3`, `dataset_total_with_filename_FixedTest.sql3`, and result patterns.
6. DatasetConverter already has the approved dependency-light `StagePlan → StageContext` boundary and typed configuration slices. This program consumes that stage as-is and adds regression/import-direction gates; it must not fold those modules back into `DataConverter.py`.
7. Stage 2–4 scripts still execute large bodies under `if __name__ == '__main__'`, mix activation/filesystem/model work, and contain internal `os.system()` calls. Root process isolation comes first. Later stage extraction may share the execution mechanism, but it must retain each call site's own failure policy rather than inheriting the root fail-fast policy.
8. `.codex/workflows.md` now identifies `python -m unittest discover -s tests` and the DatasetConverter fixture command, while `.codex/known_issues.md` still says no canonical smoke test exists. This is documentation drift, not an architecture blocker.

## Verified Stage 2–4 failure-semantics map

This map is source evidence for Tasks 2, 6, 8, 10, and 12. It distinguishes the command mechanism from the owner call site's failure decision; characterization must freeze these observations before extraction.

| Owner / call site | Current mechanism | Non-zero handling | Python exception handling | Subsequent validation / observable continuation | Required preservation |
| --- | --- | --- | --- | --- | --- |
| `TCFMain.run_stage_command()` | `subprocess.run(CMD, shell=True, check=False)` | Explicitly inspects `returncode`; reports via `stage_failed`, raises `RuntimeError`, and prevents following root stages | Invocation exceptions are not caught here | None after a non-zero result | Root-only fail-fast policy remains exact |
| `RunClassfier.py`: Windows environment activation `os.system(WindowsAnacondaPromptCMD)` | `os.system` | Return code is ignored | No local catch; a Python exception from the call propagates | Continues to execute the batch file | Ignore non-zero; do not graft root abort semantics onto it |
| `RunClassfier.py`: Linux `os.system(f"chmod 700 {BatFile}")` | `os.system` | Return code is ignored | No local catch; a Python exception propagates | Rewrites the batch path and executes it next | Ignore non-zero; retain subsequent command execution |
| `RunClassfier.py`: TF batch `os.system(BatFile)` | `os.system` | Return code is ignored | No local catch; a Python exception propagates | In test mode, later `WaitUntilFileIsStable` checks prediction artifacts before moves/handoff; training uses the existing background behavior | Preserve ignored status plus downstream artifact/wait behavior |
| `RunClassfier.py`: PyTorch/model `os.system(BatCMD)` | `os.system` inside `try/except Exception` | Return code is ignored | Python exceptions are caught and warned, then execution continues | In test mode, later `WaitUntilFileIsStable` validates expected result files before handoff; training retains background behavior | Preserve ignored status, warning-on-Python-exception, and later validation |
| `CombineTestResult.py` | No active `os.system` or `subprocess` call found | Not applicable | Not applicable | Its existing computation/filesystem failures remain owned by the stage | Do not invent a process policy |
| `Test_result_Vis.py`: upload callback via `CommandExecutor(TCFMainCMD)` | `CommandExecutor` calls `subprocess.run(..., shell=True, check=True)` in its worker | A non-zero result becomes `CalledProcessError` inside the worker | `CommandExecutor` catches `Exception`, prints failure, and does not re-raise to the callback; the callback joins and continues | Callback prints completion and continues | Preserve the adapter's internally caught failure behavior; do not replace it with root fail-fast |
| `Test_result_Vis.py`: summary `os.system(CMD)` | `os.system` | Return code is ignored | No local catch; a Python exception propagates | Continues with completion log, summary-file discovery, and SQLite update work | Preserve ignored status and subsequent artifact processing |

The Linux `pkill` `os.system` block and other shown `os.system` lines in these canonical files are commented out and are not active call sites. Future unification of exit-code/exception semantics requires new characterization, an explicit behavior-change decision, and a separate follow-up; it is outside this behavior-preserving program.

## Program invariants and PR gates

- Preserve option names, aliases, defaults, namespace keys/order, bool normalization, canonical script paths, shell strings, `shell=True`, output names, stage suffixes, stage order, conditions, logging intent, and **per-call-site** failure propagation. A shared execution mechanism must not imply a shared non-zero policy.
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
* [ ] Observe baseline: capture the parser action table, train/test normalization, and forwarding output from the unmodified baseline using an inspection snippet or test harness; record the observations in the test expectations.
* [ ] Write characterization only: complete the expectations using `parser._actions` obtained by patching `argparse.ArgumentParser.parse_args` only if needed to inspect metadata; call the public parser for behavioral assertions. Do not change production source.
* [ ] Run baseline PASS: `python -m unittest tests.test_tcf_cli_contract`. Every assertion must describe and pass against baseline source; correct a mistaken observation in the test, never production behavior.
* [ ] Prove sensitivity: under test control, supply a synthetic parser/action table with one alias removed and one default changed, and a fake forwarding implementation that reorders or drops `False`/`0`/`None`; run the relevant assertions and record that they fail for each drift category. Restore the baseline dependencies immediately.
* [ ] Restore and PASS: `python -m unittest tests.test_tcf_cli_contract`. Expected: all tests pass without filesystem/model activation.
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
* [ ] Observe baseline: with lightweight recording fakes, capture root shell flags, exact commands, conditional branches, canonical call order, double visualization invocation, and root non-zero abort before writing fixed expectations.
* [ ] Write characterization only: use temporary paths for the dataset-file check and patch `exit_program`, timing, loggers, conformer, directory picker, and merger. Do not alter production behavior to make characterization pass.
* [ ] Run baseline PASS: `python -m unittest tests.test_tcf_main_characterization`. Expected call trace: DataConverter, RunClassfier, CombineTestResult, visualization base, visualization WeiTech; a non-zero root-stage fake raises before the next call.
* [ ] Prove sensitivity: inject, one case at a time, a fake orchestrated trace with swapped stages, a fake renderer with a changed command token, a zero-return runner where non-zero is expected, a non-zero runner that incorrectly permits the next stage, and changed visualization invocation count/options. Confirm the corresponding order, rendering, failure-propagation, and invocation assertions fail; then restore all fakes. No production mutation is permitted.
* [ ] Restore and PASS: `python -m unittest tests.test_tcf_main_characterization`.
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
* [ ] Observe baseline: in a disposable temporary tree, record work selection, suffix transitions, handoff names, output-pattern order, backup/cleanup conditions, and ownership calls. Never point an argument at repository or external WorkPool directories.
* [ ] Write characterization only: create fresh module loads for mutable-global assertions so test order does not hide repeated-extension behavior; make test/fixture changes only.
* [ ] Run baseline PASS: `python -m unittest tests.test_tcf_workpool_characterization`.
* [ ] Prove sensitivity: feed synthetic directory entries with a different newest eligible ID, substitute a fake picker returning a drifted suffix/name, reorder or remove a handoff/output pattern, and toggle backup/cleanup controls through fakes. Confirm the selection, naming, pattern-order, WorkPool move, and cleanup assertions fail, then restore the baseline fixtures/fakes. Do not mutate production source.
* [ ] Restore and PASS: `python -m unittest tests.test_tcf_workpool_characterization`.
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

## Task 6: Introduce policy-aware legacy shell process execution

**Goal**

Place command invocation behind a dependency-light interface while keeping failure policy at each owner call site; first adapt the root without changing its fail-fast contract.

**Files**

* **Inspect:** all `subprocess.run`/`os.system` occurrences in root and canonical stage scripts
* **Create:** `text_category_profiler/execution/__init__.py`, `text_category_profiler/execution/process.py`, `tests/test_process_runner.py`
* **Modify:** `TCFMain.py`
* **Test:** `tests/test_process_runner.py`, `tests/test_tcf_main_characterization.py`

**Existing behavior protected**

For the root adapter only: string commands, `shell=True`, `check=False`, returned completed object, non-zero `RuntimeError` message, logging callback, and immediate downstream abort. The runner mechanism itself does not raise merely because a result is non-zero.

**Interfaces**

* **Consumes:** command string and stage name
* **Produces:** `ProcessRunner` protocol whose execution method returns a result/status without imposing failure policy; `LegacyShellProcessRunner(run_process=subprocess.run)` for shell-compatible invocation; explicit `RootFailFastPolicy(failure_reporter=stage_failed)` (or equivalently named root adapter) applied by `TCFMain.run_stage_command()`. Stage-specific ignore/catch/validate-later policies remain their owners' responsibility.

**Steps**

* [ ] Write failing tests `test_protocol_accepts_string_command`, `test_legacy_runner_calls_subprocess_with_shell_true_check_false`, `test_runner_returns_nonzero_without_raising`, `test_root_policy_reports_and_raises_on_nonzero`, and `test_root_compatibility_function_delegates_to_default_runner`. Add a policy matrix test proving an ignore policy does not abort and a caught-exception adapter does not accidentally become return-code fail-fast.
* [ ] Run RED: `python -m unittest tests.test_process_runner`. Expected failure: `text_category_profiler.execution.process` does not exist.
* [ ] Implement minimal change: implement the mechanism protocol/adapter and separate root failure policy; make `TCFMain.run_stage_command(CMD, stage_name, runner=None)` delegate execution and then apply the root policy while preserving two-argument callers and its exact `RuntimeError`. Do not migrate Stage 2–4 call sites in this task.
* [ ] Run GREEN: `python -m unittest tests.test_process_runner tests.test_tcf_main_characterization`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall TCFMain.py text_category_profiler/execution`.
* [ ] Update documentation if required: record execution dependency direction in `.codex/architecture.md`; explicitly state argv-list is deferred.
* [ ] Commit checkpoint: `git add TCFMain.py text_category_profiler/execution tests/test_process_runner.py .codex/architecture.md && git commit -m "refactor: isolate legacy shell execution"`.

**Acceptance criteria:** Root has one replaceable execution seam and exact shell behavior/error contract remains; non-zero does not raise in the mechanism alone, and no argv list, quoting change, retry, async execution, or global failure policy is introduced.

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

* **Consumes:** Namespace, directory picker, filesystem adapter, ProcessRunner mechanism, explicit call-site policies/adapters, model/output adapters
* **Produces:** `ClassifierPlan(args, dataset_dir, output_dir, command)` before activation; `activate_classifier(plan, ...)`; `run_classifier_stage(context)`; compatibility `main(argv=None)`. The plan identifies the call-site policy (`ignore_nonzero`, `propagate_python_exception`, or `warn_on_python_exception`) separately from command rendering/execution.

**Steps**

* [ ] Write failing tests `test_plan_preserves_pytorch_command`, `test_plan_preserves_tf_template_flags`, `test_activation_renames_ready_to_running`, `test_windows_activation_nonzero_still_runs_batch`, `test_chmod_nonzero_still_runs_tf_batch`, `test_tf_batch_nonzero_reaches_artifact_wait`, `test_pytorch_nonzero_reaches_artifact_wait`, `test_pytorch_python_exception_warns_and_continues`, `test_tf_python_exception_propagates`, `test_test_success_handoffs_to_combine`, and `test_training_keeps_background_semantics`. Use fake DB counts, stable-file adapter, filesystem, and runner; separately simulate returned non-zero statuses and raised Python exceptions.
* [ ] Run RED: `python -m unittest tests.test_classifier_stage`. Expected failure: module/interfaces absent.
* [ ] Implement minimal change: extract only command/planning/activation seams. A shared `LegacyShellProcessRunner` may replace the invocation mechanism, but each former `os.system` site must apply the verified policy in the source map: ignore non-zero for Windows activation/chmod/TF batch/PyTorch command; propagate Python invocation exceptions at the first three; catch-and-warn Python exceptions only for the PyTorch command; retain later `WaitUntilFileIsStable`/handoff and training-background behavior. Leave ML imports/algorithms and canonical file path intact; `RunClassfier.py` delegates under its main guard.
* [ ] Run GREEN: `python -m unittest tests.test_classifier_stage tests.test_combine_test_result_model_types tests.test_model_directory_resolution`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall BertScript/RunClassfier.py BertScript/classifier_stage.py`.
* [ ] Update documentation if required: document internal stage API and retained script contract in architecture/contracts.
* [ ] Commit checkpoint: `git add BertScript/RunClassfier.py BertScript/classifier_stage.py tests/test_classifier_stage.py .codex/architecture.md .codex/contracts.md && git commit -m "refactor: isolate classifier stage lifecycle"`.

**Acceptance criteria:** No model/GPU runs in tests; exact command/suffix/artifact behavior and every classifier call-site policy in the verified map are covered; returned non-zero never becomes a new abort, and no TensorFlow, PyTorch, tokenizer, or model behavior is modernized.

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

* **Consumes:** Namespace, filesystem and policy-aware ProcessRunner adapters, the existing `CommandExecutor` semantics, lazily supplied visualization application factory
* **Produces:** `VisualizationPlan`; `activate_visualization(plan, ...)`; `run_visualization_stage(context)`; compatibility `main(argv=None)`

**Steps**

* [ ] Write failing tests `test_plan_preserves_host_and_weitech_options`, `test_activation_uses_canonical_suffix`, `test_nonhosted_path_does_not_start_server`, `test_hosted_path_preserves_kill_and_server_commands`, `test_command_executor_nonzero_is_caught_and_callback_continues`, `test_summary_nonzero_continues_to_artifact_processing`, `test_summary_python_exception_propagates`, `test_validation_failure_does_not_mark_stage_complete`, and `test_importing_stage_plan_does_not_import_dash`. Distinguish a returned non-zero status, a Python invocation exception, and later artifact/validation failure.
* [ ] Run RED: `python -m unittest tests.test_visualization_stage`. Expected missing module/interfaces.
* [ ] Implement minimal change: isolate only entrypoint plan/activation and shell calls; import Dash-heavy implementation lazily. Preserve `CommandExecutor`'s `check=True` plus internal catch/print/continue behavior and the summary `os.system` site's ignored return code plus subsequent artifact processing; do not apply the root fail-fast policy. Do not edit callbacks, layout, schema, visualization algorithms, or root invocation count.
* [ ] Run GREEN: `python -m unittest tests.test_visualization_stage tests.test_tcf_main_characterization tests.test_stage_commands`.
* [ ] Run regression tests: `python -m unittest discover -s tests && python -m compileall BertScript/Test_result_Vis.py BertScript/visualization_stage.py`.
* [ ] Update documentation if required: architecture/contracts record the internal seam and unchanged external entrypoint.
* [ ] Commit checkpoint: `git add BertScript/Test_result_Vis.py BertScript/visualization_stage.py tests/test_visualization_stage.py .codex/architecture.md .codex/contracts.md && git commit -m "refactor: isolate visualization stage lifecycle"`.

**Acceptance criteria:** Planning imports without Dash; fake-runner tests cover shell calls and their call-site-specific continuation/exception policies; UI behavior is untouched; the root still launches visualization twice as characterized.

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

- **Failure-semantics unification:** Any proposal to make legacy Stage 2–4 commands fail fast (or otherwise align their return-code/exception policies) is a behavior change requiring separate design evidence, characterization, and approval. It must not be bundled into this refactor.

These require separate design/review after the characterization program is stable:

1. Replace shell strings with argv-list execution and remove `shell=True`.
2. Decide, with product evidence, whether `TestResultVis()`'s second invocation is intentional or a defect.
3. Broader package relocation or deletion of compatibility entrypoints.
4. ML framework/model/tokenizer modernization, retry frameworks, output schema changes, CLI redesign, APIs, LangGraph, or async execution.

## Dependency ordering rationale

The safety net lands alone so reviews can validate observations independently of refactoring. Root configuration follows because import-time parsing/global mutation makes every later boundary harder to load safely. The policy-neutral legacy process mechanism and root fail-fast adapter precede command specifications and orchestration so fake execution can prove exact compatibility without imposing root policy on stage internals. Orchestration precedes WorkPool extraction because lifecycle ownership becomes explicit only after sequence ownership is isolated. Stage 2 and Stage 3 then reuse stable runner/filesystem patterns; visualization is last because its import graph and UI runtime are largest. Hygiene checks close the program rather than triggering an early repository move.

## Design/source reconciliation, assumptions, and blockers

- **No architecture blocker found** in inspected local source. The current source strengthens Design v1's premise: DatasetConverter has already advanced beyond the design baseline and must be preserved.
- **Baseline verification risk:** hosted GitHub could not be reached from this environment. Implementation must not proceed until a future session records the actual `origin/main` SHA. Local `work` is not named `main`, although its HEAD equals the supplied hosted SHA.
- **Minor source/design detail:** current root execution already uses `subprocess.run` with non-zero checking, while stage internals still use `os.system`. The plan first preserves root semantics, then permits stage-specific PRs to reuse only the execution mechanism while explicitly preserving each owner call site's return-code, exception, and validate-later policy.
- **Mutable-global risk:** repeated `setArguments()` calls can repeatedly extend `FinalOfferedOutputFNrePatList`; characterize fresh-process/current behavior, then make each `PipelinePlan` own fresh patterns without changing one-run output.
- **Heavy import risk:** Stage 2–4 modules can require unavailable ML/Dash/data dependencies. Tests must load extracted plan modules with fakes/lazy imports and must not claim a full stage run.
- **Command quoting risk:** current forwarding is unsafe-looking but observable. Preserve it exactly; modernization is deferred.

## Plan author self-review — completed for v1.1

- [x] Design v1 coverage remains mapped to Tasks 1–13; no Design v2 or design change was introduced.
- [x] Six phases and thirteen tasks remain; corrections are limited to process-policy preservation, characterization sensitivity, and plan clarity.
- [x] CLI/external compatibility, commands, ordering, handoffs, WorkPool isolation, and Stage 2–4 sequencing remain protected.
- [x] Root fail-fast and every active Stage 2–4 process call site were re-read and mapped without inferring semantics from desired architecture.
- [x] Characterization-only Tasks 1–3 now require baseline PASS plus controlled sensitivity evidence; missing modules are not treated as RED.
- [x] Tasks that change implementation still require genuine RED → minimal implementation → GREEN.
- [x] DatasetConverter `StagePlan → StageContext`, typed config, adapters, core modules, fixture, and dependency-light import gates remain intact.
- [x] No product source, Design v1, architecture scope, model/tokenizer/taxonomy behavior, CLI/schema/API, or implementation was changed by this correction.

## Future implementation/program completion checklist

The following remains intentionally unchecked until the six implementation PRs are executed; it is not evidence that Plan v1.1 author review is incomplete.

- [ ] Each PR began from a freshly verified hosted `main` baseline and remained independently reviewable.
- [ ] Tasks 1–3 recorded baseline observations, passed on baseline, demonstrated controlled sensitivity failure, restored controls, and passed again.
- [ ] Tasks 4–13 demonstrated genuine failing tests for intended implementation changes before minimal production edits, then GREEN and regression PASS.
- [ ] Root non-zero results still report and raise immediately, while Stage 2–4 returned statuses/exceptions/validation retain the verified per-call-site policies.
- [ ] No real model, GPU, service, database, or WorkPool was touched by tests; destructive tests used temporary directories/fakes only.
- [ ] CLI, forwarding, stage order/conditions, names, output patterns, backup/cleanup, exact commands, and visualization double invocation remained compatible.
- [ ] DatasetConverter architecture and dependency-light gates did not regress.
- [ ] Required targeted, regression, compile, documentation, and diff checks passed for every PR.
