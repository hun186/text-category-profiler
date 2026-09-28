import os
import sys
from pathlib import Path


if __name__ == "__main__":
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))

from text_category_profiler.data.DB_utils import sqlite3Query


def resolve_legacy_base_directory(caller_cwd):
    caller_cwd = Path(caller_cwd)
    if caller_cwd.name in {"DatasetConverter", "BertScript"}:
        return caller_cwd.parent
    return caller_cwd


def main():
    legacy_base = resolve_legacy_base_directory(Path.cwd())
    dataset_directory = legacy_base / "DatasetConverter" / "dataset"
    sql3File = dataset_directory / "top-1m_CZJ_SamplesFile.sql3"
    print(os.path.isfile(sql3File))
    table = "sampleSrc"
    OutLabel = "Benign Web Link"
    col = "text"
    query = f'SELECT {col} FROM {table} WHERE OutLabel = "{OutLabel}";'
    TextPools = set(
        x[0] for x in list(sqlite3Query(str(sql3File), query=query))
    )

    iterText = iter(TextPools)
    print("=" * 50)
    for x in range(10):
        print(next(iterText))
    print("=" * 50)

    CheckSrcFN = dataset_directory / "CheckSrc.csv"
    contsSet = set()
    CheckSrcCnt = 0
    with open(CheckSrcFN, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            conts = line in TextPools
            if conts is True:
                contsSet.add(line)
            CheckSrcCnt += 1
    print("contsSet", contsSet)
    print("-" * 50)
    print(f"{len(contsSet)} of {CheckSrcCnt} are in TextPools.")


if __name__ == "__main__":
    main()
