"""Isolated process harness for the real root pipeline."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

from text_category_profiler.pipeline.defaults import DEFAULT_MODEL_TYPE


@dataclass(frozen=True)
class SelfTestCheck:
    status: str
    title: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmokeConfig:
    repository_root: Path
    fixed_test_dir: Path | None
    topic_tree_dir: Path | None
    topic_tree_files: str | None
    model_dir: Path
    fixed_test_dirs: tuple[Path, ...] = ()
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


class RealRuntimeConfigurationError(ValueError):
    """Raised when the opt-in real runtime profile is incompletely configured."""


class SelfTestExecutionError(RuntimeError):
    """Expected setup/launch failure after disposable runtime allocation."""

    def __init__(self, boundary: str, cause: BaseException, runtime_root: Path,
                 workpool_root: Path, command: tuple[str, ...] = ()):
        super().__init__(str(cause))
        self.boundary = boundary
        self.cause = cause
        self.runtime_root = runtime_root
        self.workpool_root = workpool_root
        self.command = command


def _discover_model_dir(repository_root: Path, model_type: str, port: int) -> Path:
    """Perform one production-compatible model selection from the repository root."""
    from text_category_profiler.pipeline.TCF_utils import (
        ClassfierOptionParser,
        datasetDirOutputDirPickers,
    )

    args = ClassfierOptionParser(
        ["-mdlType", model_type, "-p", str(port)]
    )
    original_cwd = Path.cwd()
    try:
        os.chdir(repository_root)
        try:
            _dataset_dir, model_dir = datasetDirOutputDirPickers(args=args).proc()
            resolved_model_dir = Path(model_dir).resolve() if model_dir else None
        except Exception as error:
            raise RealRuntimeConfigurationError(
                f"production model resolver failed for {model_type}: {error}"
            ) from error
    finally:
        os.chdir(original_cwd)
    if resolved_model_dir is None:
        raise RealRuntimeConfigurationError(
            f"production model resolver found no usable model for {model_type}"
        )
    return resolved_model_dir


def _discover_fixed_test_dirs(repository_root: Path, port: int) -> tuple[Path, ...]:
    """Resolve every FixedTest source through the production adapter."""
    from argparse import Namespace
    from DatasetConverter.adapters.pipeline_source import fixed_test_paths

    original_cwd = Path.cwd()
    try:
        os.chdir(repository_root)
        try:
            paths = fixed_test_paths(Namespace(TRVPort=port))
            return tuple(Path(path).resolve() for path in paths)
        except Exception as error:
            raise RealRuntimeConfigurationError(
                f"production FixedTest resolver failed for TRVPort {port}: {error}"
            ) from error
    finally:
        os.chdir(original_cwd)


def config_from_real_runtime_environment(
    repository_root: Path, environment: dict[str, str] | os._Environ[str]
) -> SmokeConfig:
    def directory(name: str) -> Path:
        path = Path(environment[name]).expanduser().resolve()
        if not path.is_dir():
            raise RealRuntimeConfigurationError(f"{name} is not a directory: {path}")
        return path

    repository_root = repository_root.resolve()
    model_type = environment.get("TCP_REAL_MODEL_TYPE", DEFAULT_MODEL_TYPE)
    try:
        port = int(environment.get("TCP_REAL_PORT", "8050"))
    except ValueError as error:
        raise RealRuntimeConfigurationError("TCP_REAL_PORT must be an integer") from error
    if port <= 0:
        raise RealRuntimeConfigurationError("TCP_REAL_PORT must be greater than zero")

    model_override = environment.get("TCP_REAL_MODEL_DIR")
    model_dir = directory("TCP_REAL_MODEL_DIR") if model_override else Path(
        _discover_model_dir(repository_root, model_type, port)
    ).resolve()
    if not model_dir.is_dir():
        raise RealRuntimeConfigurationError(
            f"production model resolver returned a non-directory: {model_dir}"
        )

    fixed_test_override = environment.get("TCP_REAL_FIXED_TEST_DIR")
    fixed_test_dir = directory("TCP_REAL_FIXED_TEST_DIR") if fixed_test_override else None
    fixed_test_dirs = ((fixed_test_dir,) if fixed_test_dir else tuple(
        Path(path).resolve() for path in _discover_fixed_test_dirs(repository_root, port)
    ))
    if not fixed_test_dirs or any(not path.is_dir() for path in fixed_test_dirs):
        raise RealRuntimeConfigurationError(
            f"production FixedTest resolver found no usable directories for TRVPort {port}"
        )

    topic_tree_dir = (directory("TCP_REAL_TOPIC_TREE_DIR")
                      if environment.get("TCP_REAL_TOPIC_TREE_DIR") else None)
    topic_tree_files = environment.get("TCP_REAL_TOPIC_TREE_FILES") or None
    if topic_tree_files is not None:
        filenames = tuple(item.strip() for item in topic_tree_files.split(","))
        if not filenames or any(not filename for filename in filenames):
            raise RealRuntimeConfigurationError(
                "TCP_REAL_TOPIC_TREE_FILES must contain comma-separated filenames"
            )
        if topic_tree_dir is not None:
            for filename in filenames:
                if not (topic_tree_dir / filename).is_file():
                    raise RealRuntimeConfigurationError(
                        f"TCP_REAL_TOPIC_TREE_FILES entry does not exist: {filename!r}"
                    )
    try:
        timeout_seconds = int(environment.get("TCP_REAL_PIPELINE_TIMEOUT_SECONDS", "1800"))
    except ValueError as error:
        raise RealRuntimeConfigurationError(
            "TCP_REAL_PIPELINE_TIMEOUT_SECONDS must be an integer"
        ) from error
    if timeout_seconds <= 0:
        raise RealRuntimeConfigurationError(
            "TCP_REAL_PIPELINE_TIMEOUT_SECONDS must be greater than zero"
        )
    return SmokeConfig(
        repository_root=repository_root, fixed_test_dir=fixed_test_dir,
        fixed_test_dirs=fixed_test_dirs,
        topic_tree_dir=topic_tree_dir, topic_tree_files=topic_tree_files,
        model_dir=model_dir,
        model_type=model_type, port=port,
        timeout_seconds=timeout_seconds, intercept_classifier=False,
    )


def snapshot_regular_files(root: Path) -> tuple[tuple[Path, int, int], ...]:
    """Capture cheap source-mutation evidence without hashing model weights."""
    entries = []
    for path in root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            entries.append((path.relative_to(root), stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(entries, key=lambda entry: entry[0].as_posix()))


def snapshot_directories(
    roots: tuple[Path, ...],
) -> dict[Path, tuple[tuple[Path, int, int], ...]]:
    """Snapshot every resolved source directory for later mutation checks."""
    return {root: snapshot_regular_files(root) for root in roots}


def build_root_command(config: SmokeConfig, workpool_root: Path) -> list[str]:
    command = [
        sys.executable, str((config.repository_root / "TCFMain.py").resolve()),
        "-p", str(config.port), "-ts", "y", "-TRVHost", "False",
        "-WPRoot", str(workpool_root),
        "-mdlDir", str(config.model_dir), "-mdlType", config.model_type,
        "-nProc", "1", "-nProcSPC", "1", "-RMBertData", "False",
        "-exectime", config.execution_time,
    ]
    if config.fixed_test_dir is not None:
        command.extend(("-FTPath", str(config.fixed_test_dir)))
    if config.topic_tree_dir is not None:
        command.extend(("-TopicTreeDir", str(config.topic_tree_dir)))
    if config.topic_tree_files is not None:
        command.extend(("-TopicTreeFiles", config.topic_tree_files))
    return command


def create_python_wrapper(config: SmokeConfig, runtime_root: Path) -> Path:
    wrapper_dir = runtime_root / "python-wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        wrapper = wrapper_dir / "python.cmd"
        wrapper.write_text(
            '@echo off\r\n"%TCP_SMOKE_REAL_PYTHON%" "%TCP_SMOKE_DISPATCH_SCRIPT%" %*\r\n'
            "exit /b %ERRORLEVEL%\r\n", encoding="utf-8")
    else:
        wrapper = wrapper_dir / "python"
        wrapper.write_text(
            '#!/bin/sh\nexec "${TCP_SMOKE_REAL_PYTHON}" "${TCP_SMOKE_DISPATCH_SCRIPT}" "$@"\n',
            encoding="utf-8")
        wrapper.chmod(0o755)
    return wrapper


def build_isolated_environment(config: SmokeConfig, runtime_root: Path,
                               classifier_marker: Path | None) -> dict[str, str]:
    environment = os.environ.copy()
    locations = {
        "TEMP": runtime_root / "tmp", "TMP": runtime_root / "tmp",
        "TMPDIR": runtime_root / "tmp", "HOME": runtime_root / "home",
        "HF_HOME": runtime_root / "hf-home",
        "TRANSFORMERS_CACHE": runtime_root / "transformers-cache",
    }
    for name, location in locations.items():
        location.mkdir(parents=True, exist_ok=True)
        environment[name] = str(location)
    if config.intercept_classifier:
        wrapper = create_python_wrapper(config, runtime_root)
        environment["PATH"] = str(wrapper.parent) + os.pathsep + environment.get("PATH", "")
        environment["TCP_SMOKE_REAL_PYTHON"] = sys.executable
        environment["TCP_SMOKE_DISPATCH_SCRIPT"] = str(
            (config.repository_root / "text_category_profiler/diagnostics/python_dispatch.py").resolve())
        environment["TCP_SMOKE_CLASSIFIER_SCRIPT"] = str(
            (config.repository_root / "text_category_profiler/diagnostics/smoke_classifier.py").resolve())
        if classifier_marker is not None:
            environment["TCP_SMOKE_CLASSIFIER_MARKER"] = str(classifier_marker)
    return environment


def discover_workspaces(workpool_root: Path) -> tuple[Path, ...]:
    if not workpool_root.is_dir():
        return ()
    return tuple(sorted((path for path in workpool_root.iterdir() if path.is_dir()),
                        key=lambda path: path.name))


def _runtime_root(config: SmokeConfig) -> Path:
    temporary_parent = Path(tempfile.gettempdir())
    if any(character.isspace() for character in str(temporary_parent)):
        parent = config.repository_root / ".smoke-runtime"
        parent.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="ki003-", dir=parent))
    return Path(tempfile.mkdtemp(prefix="tcp-smoke-", dir=temporary_parent))


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, check=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)


def run_full_pipeline(config: SmokeConfig, *, use_model_facade: bool = False) -> SmokeResult:
    runtime_root = _runtime_root(config)
    workpool_root = runtime_root / "WorkPool"
    command: tuple[str, ...] = ()
    try:
        workpool_root.mkdir(parents=True)
    except OSError as error:
        cleanup_runtime_root(runtime_root, config.repository_root)
        raise SelfTestExecutionError(
            "Runtime setup", error, runtime_root, workpool_root
        ) from error
    if config.intercept_classifier:
        try:
            config = replace(
                config,
                model_dir=create_intercepted_model_copy(config.model_dir, runtime_root),
            )
        except OSError as error:
            cleanup_runtime_root(runtime_root, config.repository_root)
            raise SelfTestExecutionError(
                "Runtime setup", error, runtime_root, workpool_root
            ) from error
    elif use_model_facade:
        try:
            config = replace(
                config, model_dir=create_model_facade(config.model_dir, runtime_root)
            )
        except (OSError, ValueError) as error:
            cleanup_runtime_root(runtime_root, config.repository_root)
            raise SelfTestExecutionError(
                "Model facade", error, runtime_root, workpool_root
            ) from error
    marker = (runtime_root / "classifier-invocations.jsonl"
              if config.intercept_classifier else None)
    try:
        command = tuple(build_root_command(config, workpool_root))
        environment = build_isolated_environment(config, runtime_root, marker)
    except OSError as error:
        cleanup_runtime_root(runtime_root, config.repository_root)
        raise SelfTestExecutionError(
            "Runtime setup", error, runtime_root, workpool_root, command
        ) from error
    popen_options: dict[str, object] = {}
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    try:
        process = subprocess.Popen(command, cwd=config.repository_root, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, **popen_options)
    except (OSError, subprocess.SubprocessError) as error:
        cleanup_runtime_root(runtime_root, config.repository_root)
        raise SelfTestExecutionError(
            "Process launch", error, runtime_root, workpool_root, command
        ) from error
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=config.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
    return SmokeResult(command, process.returncode, stdout, stderr, runtime_root,
                       workpool_root, discover_workspaces(workpool_root), marker, timed_out)


def _tail(value: str, lines: int) -> str:
    return "\n".join(value.splitlines()[-lines:])


def format_failure(result: SmokeResult, *, tail_lines: int = 120) -> str:
    return "\n".join((
        "Command: " + " ".join(result.command),
        f"returncode={result.returncode} timed_out={result.timed_out}",
        f"WorkPool: {result.workpool_root}",
        "Workspaces: " + ", ".join(path.name for path in result.workspaces),
        "stdout (tail):\n" + _tail(result.stdout, tail_lines),
        "stderr (tail):\n" + _tail(result.stderr, tail_lines),
    ))


def create_intercepted_model_copy(source_model_dir: Path, runtime_root: Path) -> Path:
    """Copy Layer A model metadata into writable, disposable runtime state."""
    destination = runtime_root / "model-fixture"
    shutil.copytree(source_model_dir, destination)
    return destination


def cleanup_runtime_root(runtime_root: Path, repository_root: Path) -> None:
    """Remove one smoke runtime and an empty repository fallback parent."""
    shutil.rmtree(runtime_root, ignore_errors=True)
    fallback_parent = repository_root / ".smoke-runtime"
    if fallback_parent.is_dir():
        try:
            fallback_parent.rmdir()
        except OSError:
            pass


def create_model_facade(source_model_dir: Path, runtime_root: Path) -> Path:
    source_model_dir = source_model_dir.resolve()
    checkpoints = sorted(path for path in source_model_dir.glob("checkpoint-*") if path.is_dir())
    if not checkpoints:
        raise ValueError(f"no checkpoint-* directory in source model: {source_model_dir}")
    facade = runtime_root / "model-facade"
    facade.mkdir(parents=True, exist_ok=False)
    for source in source_model_dir.iterdir():
        if source.is_file():
            shutil.copy2(source, facade / source.name)
    for checkpoint in checkpoints:
        target = facade / checkpoint.name
        try:
            target.symlink_to(checkpoint, target_is_directory=True)
        except OSError as error:
            if os.name != "nt":
                raise RuntimeError(f"cannot link model checkpoint {checkpoint}: {error}") from error
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(checkpoint)],
                                    capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(
                    f"cannot safely link model checkpoint {checkpoint}: {result.stderr.strip()}")
    return facade


def parse_classifier_device(evidence: str) -> tuple[str | None, bool | None, str | None]:
    """Parse only the stable evidence emitted by the production classifier."""
    device = None
    available = None
    gpu_name = None
    for line in evidence.splitlines():
        if line.startswith("TCF_CLASSIFIER_DEVICE "):
            fields = dict(item.split("=", 1) for item in line.split()[1:] if "=" in item)
            device = fields.get("device")
            value = fields.get("torch_cuda_available")
            available = value == "True" if value in {"True", "False"} else None
        elif line.startswith("TCF_CLASSIFIER_GPU name="):
            gpu_name = line.split("=", 1)[1].strip() or None
    return device, available, gpu_name


def _check(status: str, title: str, *details: str) -> SelfTestCheck:
    return SelfTestCheck(status, title, tuple(details))


def evaluate_isolated(result: SmokeResult, *, source_rows: int | None,
                      result_rows: int | None, source_unchanged: bool,
                      default_workpool_unchanged: bool) -> list[SelfTestCheck]:
    finals = [p for p in result.workspaces if p.name.endswith("_rdy_for_Spike")]
    running = [p for p in result.workspaces if "_is_running_" in p.name]
    marker_count = 0
    if result.classifier_marker and result.classifier_marker.is_file():
        marker_count = len(result.classifier_marker.read_text(encoding="utf-8").splitlines())
    required = ("test.tsv", "test.sql3", "test_results.tsv",
                "test_results_verification.sql3")
    final = finals[0] if len(finals) == 1 else None
    missing = [name for name in required if final is None or not (final / name).is_file()]
    checks = [
        _check("PASS", "Runtime isolation", "WorkPool: temporary",
               "Model: temporary fixture copy"),
        _check("FAIL" if result.timed_out or result.returncode else "PASS", "Root pipeline",
               f"return code: {result.returncode}", f"timed out: {result.timed_out}"),
        _check("PASS" if final and (final / "test.tsv").is_file() and
               (final / "test.sql3").is_file() else "FAIL", "DataConverter"),
        _check("PASS" if marker_count == 1 else "FAIL", "RunClassfier",
               f"classifier interception count: {marker_count}"),
        _check("PASS" if final and (final / "test_results.tsv").is_file() else "FAIL",
               "CombineTestResult"),
        _check("PASS" if final and
               ((final / "test_results_verification.sql3").is_file() or
                (final / "logs" / "Test_result_Vis.log").is_file()) else "FAIL",
               "Test_result_Vis"),
        _check("PASS" if not missing else "FAIL", "Required artifacts",
               *(required if not missing else ("missing: " + ", ".join(missing),))),
        _check("PASS" if source_rows is not None and source_rows == result_rows else "FAIL",
               "Result consistency", f"source rows: {source_rows}", f"result rows: {result_rows}"),
        _check("PASS" if len(finals) == 1 and not running else "FAIL", "Final handoff",
               f"*_rdy_for_Spike: {len(finals)}", f"*_is_running_*: {len(running)}"),
        _check("PASS" if source_unchanged and default_workpool_unchanged else "FAIL",
               "Source mutation guard", f"fixture unchanged: {source_unchanged}",
               f"default WorkPool unchanged: {default_workpool_unchanged}"),
    ]
    return checks


def evaluate_real(result: SmokeResult, *, model_unchanged: bool,
                  fixed_tests_unchanged: bool, classifier_executed: bool,
                  require_cuda: bool = False) -> list[SelfTestCheck]:
    evidence = result.stdout + "\n" + result.stderr
    for workspace in result.workspaces:
        log = workspace / "logs" / "RunClassfier.log"
        if log.is_file():
            evidence += "\n" + log.read_text(encoding="utf-8", errors="replace")
    device, cuda_available, gpu_name = parse_classifier_device(evidence)
    finals = [p for p in result.workspaces if p.name.endswith("_rdy_for_Spike")]
    if device and device.startswith("cuda:") and cuda_available is True:
        device_status = "PASS"
    elif require_cuda:
        device_status = "FAIL"
    elif device == "cpu":
        device_status = "WARN"
    else:
        device_status = "FAIL"
    return [
        _check("FAIL" if result.timed_out or result.returncode else "PASS", "Root pipeline",
               f"return code: {result.returncode}", f"timed out: {result.timed_out}"),
        _check("PASS" if classifier_executed else "FAIL", "Production classifier",
               "BertScript/TextClassification_transformers.py"),
        _check(device_status, "Classifier device", f"device: {device or 'not reported'}",
               f"PyTorch CUDA available: {cuda_available}", f"GPU: {gpu_name or 'not reported'}"),
        _check("PASS" if len(finals) == 1 else "FAIL", "Final handoff",
               f"*_rdy_for_Spike: {len(finals)}"),
        _check("PASS" if model_unchanged and fixed_tests_unchanged else "FAIL",
               "Source mutation guard", f"model unchanged: {model_unchanged}",
               f"FixedTest unchanged: {fixed_tests_unchanged}"),
    ]


def render_self_test(profile: str, checks: list[SelfTestCheck],
                     result: SmokeResult | None = None) -> int:
    print(f"TCF Full-Pipeline Self-Test — {profile}")
    print("─" * 40)
    for check in checks:
        print(f"\n[{check.status}] {check.title}")
        for detail in check.details:
            print(f"       {detail}")
    counts = {status: sum(c.status == status for c in checks)
              for status in ("PASS", "WARN", "FAIL")}
    print(f"\nSummary: {counts['PASS']} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL")
    failed = counts["FAIL"] > 0
    if failed and result is not None:
        print("\nFailure evidence:\n" + format_failure(result))
    print("FINAL: " + ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


def config_from_cli(repository_root: Path, args) -> SmokeConfig:
    """Resolve a real profile from normal production CLI selections."""
    environment = {
        "TCP_REAL_PORT": str(args.TRVPort),
        "TCP_REAL_MODEL_TYPE": args.ModelType,
    }
    if args.modelDir:
        environment["TCP_REAL_MODEL_DIR"] = args.modelDir
    if args.FixedTestPATH:
        environment["TCP_REAL_FIXED_TEST_DIR"] = args.FixedTestPATH
    if args.TopicTreeDir:
        environment["TCP_REAL_TOPIC_TREE_DIR"] = args.TopicTreeDir
    if args.TopicTreeFiles:
        environment["TCP_REAL_TOPIC_TREE_FILES"] = args.TopicTreeFiles
    return config_from_real_runtime_environment(repository_root, environment)


def _render_execution_error(profile: str, error: SelfTestExecutionError) -> int:
    details = [f"error: {error.cause}", f"temporary WorkPool: {error.workpool_root}"]
    if error.command:
        details.append("command: " + " ".join(error.command))
    return render_self_test(profile, [_check("FAIL", error.boundary, *details)])


def run_self_test(args, repository_root: Path | None = None) -> int:
    """Run and report a disposable child root pipeline."""
    import sqlite3
    repository_root = (repository_root or Path(__file__).resolve().parents[2]).resolve()
    default_workpool = repository_root / "WorkPool"
    before_workpool = tuple(sorted(p.name for p in default_workpool.iterdir())) if default_workpool.is_dir() else ()
    if args.self_test == "isolated":
        fixtures = repository_root / "tests" / "fixtures" / "full_pipeline_smoke"
        source_model = fixtures / "model"
        source_before = snapshot_regular_files(source_model)
        config = SmokeConfig(repository_root, fixtures / "fixed_test" / "Using",
                             fixtures / "taxonomy", "TopicTree_smoke.csv", source_model)
        try:
            result = run_full_pipeline(config)
        except SelfTestExecutionError as error:
            return _render_execution_error("isolated", error)
        try:
            finals = [p for p in result.workspaces if p.name.endswith("_rdy_for_Spike")]
            source_rows = result_rows = None
            if len(finals) == 1:
                try:
                    with sqlite3.connect(finals[0] / "test.sql3") as db:
                        source_rows = db.execute("SELECT COUNT(*) FROM sampleSrc").fetchone()[0]
                    with sqlite3.connect(finals[0] / "test_results_verification.sql3") as db:
                        table = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchone()[0]
                        result_rows = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                except Exception:
                    pass
            after_workpool = tuple(sorted(p.name for p in default_workpool.iterdir())) if default_workpool.is_dir() else ()
            checks = evaluate_isolated(result, source_rows=source_rows, result_rows=result_rows,
                                       source_unchanged=snapshot_regular_files(source_model) == source_before,
                                       default_workpool_unchanged=before_workpool == after_workpool)
            return render_self_test("isolated", checks, result)
        finally:
            cleanup_runtime_root(result.runtime_root, repository_root)
    try:
        config = config_from_cli(repository_root, args)
    except (RealRuntimeConfigurationError, OSError) as error:
        return render_self_test("real", [_check("FAIL", "Configuration", str(error))])
    try:
        model_before = snapshot_regular_files(config.model_dir)
        fixed_before = snapshot_directories(config.fixed_test_dirs)
    except OSError as error:
        return render_self_test("real", [_check("FAIL", "Source snapshot", str(error))])
    try:
        result = run_full_pipeline(config, use_model_facade=True)
    except SelfTestExecutionError as error:
        return _render_execution_error("real", error)
    try:
        evidence = result.stdout + result.stderr
        for workspace in result.workspaces:
            log = workspace / "logs" / "RunClassfier.log"
            if log.is_file():
                evidence += log.read_text(encoding="utf-8", errors="replace")
        checks = [
            _check("PASS", "Configuration", f"TRVPort: {config.port}",
                   f"ModelType: {config.model_type}"),
            _check("PASS", "Model", f"source: {config.model_dir}", "facade: temporary"),
            _check("PASS", "FixedTest", *(f"source: {p}" for p in config.fixed_test_dirs)),
        ] + evaluate_real(
            result, model_unchanged=snapshot_regular_files(config.model_dir) == model_before,
            fixed_tests_unchanged=snapshot_directories(config.fixed_test_dirs) == fixed_before,
            classifier_executed="TextClassification_transformers.py" in evidence,
            require_cuda=args.require_cuda,
        )
        return render_self_test("real", checks, result)
    finally:
        cleanup_runtime_root(result.runtime_root, repository_root)
