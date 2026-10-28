"""Import-safe legacy RAND entrypoint (implementation lives in experiments/).

Old operator scripts can still invoke this file directly. Legacy helper names
are resolved lazily to avoid importing optional data dependencies.
"""
from pathlib import Path
import runpy


def main():
    target = Path(__file__).resolve().parents[1] / "experiments" / "rand_corpus_labeling.py"
    runpy.run_path(str(target), run_name="__main__")


def __getattr__(name):
    if name not in {"LoadTree", "GetSubNodes", "RANDLoader"}:
        raise AttributeError(name)
    from experiments import rand_corpus_labeling
    return getattr(rand_corpus_labeling, name)


if __name__ == "__main__":
    main()
