"""Compatibility adapter for the vendored, MIT-licensed Dijkstra example.

The unmodified upstream implementation and bundled examples live under
vendor/dijkstra_algorithm_master/. Keep the legacy import and direct-run path
until external operator references have been checked.
"""
from importlib import import_module
from pathlib import Path
import runpy

__all__ = ("Graph", "INFINITY", "verify_algorithm", "main")


def __getattr__(name):
    if name not in {"Graph", "INFINITY", "verify_algorithm"}:
        raise AttributeError(name)
    upstream = import_module("vendor.dijkstra_algorithm_master.dijkstra_algorithm")
    return getattr(upstream, name)


def main():
    script = (
        Path(__file__).resolve().parents[2]
        / "vendor"
        / "dijkstra_algorithm_master"
        / "dijkstra_algorithm.py"
    )
    # run_name keeps the original script's __main__ example behavior; it
    # still resolves graph fixture filenames relative to caller cwd.
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
