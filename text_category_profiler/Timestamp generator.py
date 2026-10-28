"""Legacy direct-script entrypoint for the timestamp generation experiment.

No data is generated on import. Execute this file directly to preserve the
historical command and cwd-relative output paths while the implementation lives
under experiments/. This wrapper can be removed after external callers are
verified to use experiments/timestamp_generator.py.
"""

from pathlib import Path
import runpy


def main():
    experiment = Path(__file__).resolve().parents[1] / "experiments" / "timestamp_generator.py"
    runpy.run_path(str(experiment), run_name="__main__")


if __name__ == "__main__":
    main()
