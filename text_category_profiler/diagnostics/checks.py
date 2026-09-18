"""Read-only checks used by the production ``--doctor`` command."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import sys
from typing import Callable, Iterable


@dataclass(frozen=True)
class Diagnostic:
    status: str
    title: str
    details: tuple[str, ...]


def _result(status: str, title: str, *details: object) -> Diagnostic:
    return Diagnostic(status, title, tuple(str(detail) for detail in details))


def _within_repository(repository_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repository_root / path
    return path.resolve()


def discover_model_dir(repository_root: Path, model_type: str, port: int) -> Path:
    """Run the production model picker once, restoring cwd in every outcome."""
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
        _dataset_dir, model_dir = datasetDirOutputDirPickers(args=args).proc()
        if not model_dir:
            raise FileNotFoundError(
                f"no production model resolved for {model_type} at TRVPort {port}"
            )
        return Path(model_dir).resolve()
    finally:
        os.chdir(original_cwd)


def _model_checkpoints(model_dir: Path) -> tuple[Path, ...]:
    weights = ("model.safetensors", "pytorch_model.bin")
    return tuple(
        checkpoint for checkpoint in sorted(model_dir.glob("checkpoint-*"))
        if checkpoint.is_dir()
        and any((checkpoint / filename).is_file() for filename in weights)
    )


def check_model(args, repository_root: Path) -> list[Diagnostic]:
    explicit = bool(args.modelDir)
    try:
        model_dir = (
            _within_repository(repository_root, args.modelDir)
            if explicit else discover_model_dir(
                repository_root, args.ModelType, args.TRVPort
            )
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        return [_result(
            "FAIL", "Model discovery",
            f"ModelType: {args.ModelType}", f"TRVPort: {args.TRVPort}",
            f"No usable production model source resolved: {error}",
            "Check --modelDir or the production BertScript/output_* directories.",
        )]
    source = "explicit --modelDir" if explicit else "production auto-discovery"
    if not model_dir.is_dir():
        return [_result(
            "FAIL", "Model discovery", f"Source: {source}",
            f"Resolved path is not a directory: {model_dir}",
        )]
    discovery = _result(
        "PASS", "Model discovery", f"Source: {source}", f"Path: {model_dir}"
    )
    checkpoints = _model_checkpoints(model_dir)
    if not checkpoints:
        checkpoint = _result(
            "FAIL", "Model checkpoint", f"Model path: {model_dir}",
            "Expected checkpoint-* containing model.safetensors or pytorch_model.bin.",
        )
    else:
        checkpoint = _result(
            "PASS", "Model checkpoint",
            *(f"Checkpoint: {path}" for path in checkpoints),
        )
    return [discovery, checkpoint]


def _auto_fixed_test_paths(args, repository_root: Path) -> tuple[Path, ...]:
    from DatasetConverter.adapters.pipeline_source import fixed_test_paths

    original_cwd = Path.cwd()
    try:
        os.chdir(repository_root)
        return tuple(Path(path).resolve() for path in fixed_test_paths(args))
    finally:
        os.chdir(original_cwd)


def check_fixed_test(args, repository_root: Path) -> Diagnostic:
    explicit = bool(args.FixedTestPATH)
    try:
        paths = (
            (_within_repository(repository_root, args.FixedTestPATH),)
            if explicit else _auto_fixed_test_paths(args, repository_root)
        )
    except (OSError, RuntimeError, ValueError) as error:
        paths = ()
        resolution_error = str(error)
    else:
        resolution_error = ""
    usable = tuple(path for path in paths if path.is_dir())
    if usable and len(usable) == len(paths):
        return _result(
            "PASS", "FixedTest", f"Port: {args.TRVPort}",
            *(f"Source: {path}" for path in usable),
        )
    detail = resolution_error or (
        "No production FixedTest source resolved." if not paths
        else "One or more resolved paths are not directories: "
             + ", ".join(str(path) for path in paths if not path.is_dir())
    )
    return _result(
        "FAIL", "FixedTest", f"Port: {args.TRVPort}", detail,
        f"Expected pattern: FixedTest/FixedTest_{args.TRVPort}/Using",
    )


def _topic_tree_path(filename: str, *, tree_source_dir: str) -> str:
    from ClassesTree.ClassesTree_utils import GetTreeFilePath
    return GetTreeFilePath(TreeBaseFN=filename, TreeSourceDir=tree_source_dir)


def check_topic_trees(
    args,
    repository_root: Path,
    *,
    resolver: Callable[..., str] = _topic_tree_path,
) -> Diagnostic:
    filenames = tuple(
        filename.strip() for filename in args.TopicTreeFiles.split(",")
        if filename.strip()
    )
    original_cwd = Path.cwd()
    resolved = []
    try:
        os.chdir(repository_root)
        for filename in filenames:
            resolved.append(Path(resolver(
                filename, tree_source_dir=args.TopicTreeDir
            )).resolve())
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        return _result(
            "FAIL", "TopicTree", f"TopicTreeDir: {args.TopicTreeDir or '(default)'}",
            f"Files: {args.TopicTreeFiles}", str(error),
            "Check --TopicTreeDir and --TopicTreeFiles.",
        )
    finally:
        os.chdir(original_cwd)
    if not filenames:
        return _result("FAIL", "TopicTree", "No effective TopicTreeFiles were supplied.")
    return _result(
        "PASS", "TopicTree", *(f"Source: {path}" for path in resolved)
    )


def check_cuda(*, torch_module=None, require_cuda: bool = False):
    if torch_module is None:
        try:
            import torch as torch_module
        except ImportError as error:
            return (
                _result("FAIL", "PyTorch", f"Import failed: {error}"),
                _result("FAIL" if require_cuda else "WARN", "CUDA",
                        "CUDA could not be queried because PyTorch is unavailable."),
            )
    pytorch = _result("PASS", "PyTorch", f"version: {torch_module.__version__}")
    available = bool(torch_module.cuda.is_available())
    count = int(torch_module.cuda.device_count())
    details = [
        f"torch.cuda.is_available(): {available}",
        f"torch.cuda.device_count(): {count}",
    ]
    if available:
        for index in range(count):
            details.append(
                f"torch.cuda.get_device_name({index}): "
                f"{torch_module.cuda.get_device_name(index)}"
            )
    status = "PASS" if available else ("FAIL" if require_cuda else "WARN")
    if not available:
        details.append("CUDA is unavailable; this is availability evidence only.")
    return pytorch, _result(status, "CUDA", *details)


def collect_diagnostics(args, repository_root: Path | None = None):
    root = (repository_root or Path.cwd()).resolve()
    results = [
        _result("PASS", "Python runtime", f"Python: {platform.python_version()}",
                f"Platform: {platform.platform()}"),
        _result("PASS", "Configuration", f"TRVPort: {args.TRVPort}",
                f"ModelType: {args.ModelType}"),
    ]
    results.extend(check_model(args, root))
    results.append(check_fixed_test(args, root))
    results.append(check_topic_trees(args, root))
    results.extend(check_cuda(require_cuda=args.require_cuda))
    return results


def render_diagnostics(results: Iterable[Diagnostic], stream=None) -> int:
    stream = stream or sys.stdout
    results = list(results)
    print("TCF System Diagnostics", file=stream)
    print("─" * 36, file=stream)
    for result in results:
        print(f"\n[{result.status}] {result.title}", file=stream)
        for detail in result.details:
            print(f"       {detail}", file=stream)
    counts = {
        status: sum(result.status == status for result in results)
        for status in ("PASS", "WARN", "FAIL")
    }
    print(
        f"\nSummary: {counts['PASS']} PASS / {counts['WARN']} WARN / "
        f"{counts['FAIL']} FAIL",
        file=stream,
    )
    return 1 if counts["FAIL"] else 0


def run_doctor(args, repository_root: Path | None = None) -> int:
    """Run read-only preflight diagnostics and return a process exit code."""
    return render_diagnostics(collect_diagnostics(args, repository_root))
