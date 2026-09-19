"""PATH-level Python dispatcher used only by the smoke-test harness."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return subprocess.call([os.environ["TCP_SMOKE_REAL_PYTHON"]])
    selected = Path(arguments[0])
    normalized = selected.as_posix().replace("\\", "/")
    if normalized.endswith("BertScript/TextClassification_transformers.py"):
        selected = Path(os.environ["TCP_SMOKE_CLASSIFIER_SCRIPT"])
    command = [os.environ["TCP_SMOKE_REAL_PYTHON"], str(selected), *arguments[1:]]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
