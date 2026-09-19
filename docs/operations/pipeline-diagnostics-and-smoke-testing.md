# Pipeline diagnostics and smoke testing

## Production pipeline and configuration

The production root runs these stages in order:

```text
DataConverter
→ RunClassfier
→ CombineTestResult
→ Test_result_Vis
→ *_rdy_for_Spike
```

The canonical production `ModelType` default is `PytorchMMBERT`. An operator can
still select another supported implementation explicitly, for example:

```bash
python TCFMain.py -mdlType PytorchXLM
```

An omitted model directory triggers the production model picker. From the
repository root it selects the newest unused `output_*` directory matching the
selected `ModelType`, then requires a `checkpoint-*` directory containing
`model.safetensors` or `pytorch_model.bin`. Selection also receives the selected
`TRVPort`; an explicit `-mdlDir`/`--modelDir` bypasses discovery.

An omitted `FixedTestPATH` triggers the production FixedTest adapter. It checks
the selected port under both supported relative roots, with the effective shape
`FixedTest/FixedTest_<TRVPort>/Using`. An explicit `-FTPath`/`--FixedTestPATH`
bypasses that search.

Topic trees use `--TopicTreeFiles` (default
`TopicTree.csv,TopicTree_AK4.csv`) and optional `--TopicTreeDir`. The production
taxonomy resolver first honors explicit paths and the explicit directory, then
checks project `ClassesTree/data` locations and finally the legacy TACA
locations. An explicit directory is authoritative: missing files fail rather
than silently falling back elsewhere.

## Read-only Doctor preflight

Run:

```bash
python TCFMain.py --doctor
```

Doctor builds the normal production plan but exits before runtime activation.
It does **not** invoke `HybridConformer`, a pipeline stage, `PipelineOrchestrator`,
subprocess stage execution, WorkPool rename/delivery, or WeiTech acquisition.
It performs read-only checks for:

- Python version and platform;
- selected `TRVPort` and `ModelType`;
- explicit or auto-discovered model source and usable checkpoint weights;
- explicit or port-derived FixedTest sources;
- every effective TopicTree source through the production taxonomy resolver;
- PyTorch import/version and CUDA availability, device count, and device names.

Use the normal CLI overrides with Doctor when diagnosing a particular
configuration:

```bash
python TCFMain.py --doctor -p 8059 -mdlType PytorchXLM
python TCFMain.py --doctor -mdlDir /path/to/model -FTPath /path/to/fixed-test
```

`--require-cuda` strengthens only the CUDA result:

```bash
python TCFMain.py --doctor --require-cuda
```

## Production full-pipeline self-tests

The production CLI exposes the same reusable runner used by the unittest profiles:

```bash
python TCFMain.py --self-test isolated
python TCFMain.py --self-test real -p 8059
python TCFMain.py --self-test real -p 8059 --require-cuda
```

Doctor is availability/preflight only. Isolated validates architecture and lifecycle
with the committed `PytorchXLM` fixture and classifier interception. Real uses the
production model, classifier, FixedTest, and taxonomy while keeping WorkPool and a
writable model facade temporary; it defaults to `PytorchMMBERT`. Real plus
`--require-cuda` accepts only explicit `TCF_CLASSIFIER_DEVICE device=cuda:<n>`
evidence emitted by the actual classifier, never generic third-party CUDA logs.
Normal `-mdlDir`, `-FTPath`, `-TopicTreeDir`, `-TopicTreeFiles`, `-p`, and
`-mdlType` overrides are honored. Environment-based unittest commands remain the
CI/developer alternatives.

Each check is reported as:

- `PASS`: the resource or runtime fact was resolved and validated;
- `WARN`: no required check failed, but an operational limitation exists (for
  example CUDA is unavailable while CPU execution remains possible);
- `FAIL`: a required resource could not be located or initialized.

Doctor exits `0` when there are no `FAIL` results, including warning-only
reports, and non-zero when one or more checks fail. A normal missing-resource
result is concise and includes the selected port/model/path and the next location
to inspect rather than a traceback.

## Layer A: isolated real-root smoke

Layer A runs the real root and all four stage entrypoints in a temporary
WorkPool. It copies committed model metadata into disposable writable state and
intercepts only the classifier inference child:

```bash
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
```

Its committed fixture intentionally retains `PytorchXLM`; changing the
production default does not migrate or invalidate that fixture contract. Layer A
requires root exit `0`, one classifier marker, stage artifacts, the visualization
log, and a final `*_rdy_for_Spike` workspace. It does not prove real model or GPU
execution.

## Layer B: real-runtime smoke

Layer B removes classifier interception, discovers production resources, creates
a temporary writable model facade, and runs against a temporary WorkPool:

```bash
TCP_RUN_REAL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_real_runtime
```

Optional overrides are `TCP_REAL_PORT`, `TCP_REAL_MODEL_TYPE`,
`TCP_REAL_MODEL_DIR`, `TCP_REAL_FIXED_TEST_DIR`,
`TCP_REAL_TOPIC_TREE_DIR`, `TCP_REAL_TOPIC_TREE_FILES`, and
`TCP_REAL_PIPELINE_TIMEOUT_SECONDS`. Without a model-type override Layer B uses
the canonical `PytorchMMBERT` default. Model auto-discovery receives both the
effective model type and effective port. An explicit model or FixedTest path
bypasses the corresponding discovery step.

Both smoke profiles snapshot external inputs and confine mutable runtime state to
temporary directories. Layer B copies model metadata and links checkpoints into
its model facade so runtime markers cannot be written into the source model. It
also verifies that every resolved FixedTest source and the source model remain
unchanged. These safeguards do not exercise production WeiTech queue acquisition
or delivery, which remains the separate `KI-002` boundary.

## CUDA evidence and acceptance

Doctor proves only what PyTorch reports about device **availability**. A log line
containing the word `CUDA` is not evidence of GPU selection; in particular,
messages that fall back to `libbitsandbytes_cpu.so` are CPU evidence, not CUDA
execution evidence. Layer B acceptance requires classifier-runtime evidence that
the intended CUDA device was actually selected and used, in addition to Doctor's
availability facts.

`KI-003` acceptance therefore requires the reviewed Layer A pass plus Layer B
real-model completion, temporary-state/source-mutation guarantees, final
`*_rdy_for_Spike` handoff, and the planned H100 CUDA available-and-selected
evidence. A successful Windows real-runtime execution alone does not satisfy the
pending H100 criterion. Current status remains: Layer A **PASS**, Layer B **NOT
YET ACCEPTED**, and `KI-003` **Open**.

`KI-002` is independent. Neither Layer A nor Layer B proves the production
WeiTech acquisition/delivery lifecycle, so `KI-002` remains **Open**.

## Common failures and next checks

| Boundary | Typical failure | Next check |
| --- | --- | --- |
| Model discovery | No matching `output_*` or no usable checkpoint | Verify `ModelType`, `TRVPort`, `-mdlDir`, and checkpoint weight filename. |
| FixedTest | No `Using` directory for the selected port | Verify `-p`, `-FTPath`, and `FixedTest/FixedTest_<port>/Using`. |
| TopicTree | One effective CSV cannot be resolved | Verify `--TopicTreeDir`, the comma-separated filenames, and file readability. |
| PyTorch | Import fails | Install the production runtime dependencies for the target host. |
| CUDA warning/failure | PyTorch reports no available devices | Check the installed PyTorch build, driver visibility, and device allocation; then obtain classifier execution evidence. |
| Layer A | Missing opt-in flag | Set `TCP_RUN_FULL_PIPELINE_SMOKE=1`; otherwise a skip is expected. |
| Layer B | Resource override/discovery failure | Run Doctor with the same port/model/path configuration before opting in to Layer B. |
