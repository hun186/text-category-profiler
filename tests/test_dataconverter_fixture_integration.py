import csv
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import tempfile
import unittest

from DatasetConverter.core.dataset_split import build_split_plan
from DatasetConverter.core.dataset_split import iter_split_bounds
from DatasetConverter.adapters.fixture_artifacts import write_classifier_tsv
from DatasetConverter.sources.source_collection import discover_source_files
from DatasetConverter.sources.source_collection import read_text_sources


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "dataconverter_small" / "input"
)


def fixture_walker(root, *, Extension, FullPathFNrePat):
    extensions = {f".{extension.lower()}" for extension in Extension}
    return [
        str(path)
        for path in Path(root).rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    ]


class DataConverterFixtureIntegrationTests(unittest.TestCase):
    def test_small_fixture_runs_workers_split_and_tsv_output(self):
        paths = discover_source_files(
            [str(FIXTURE_ROOT)], r".*", walker=fixture_walker
        )
        self.assertEqual(len(paths), 3)

        with ProcessPoolExecutor(max_workers=2) as executor:
            sources = read_text_sources(paths, executor=executor)

        plan = build_split_plan(len(sources), train_ratio=1 / 3, test_ratio=1 / 3)
        bounds = list(iter_split_bounds(plan, len(sources)))
        self.assertEqual(bounds, [("train", 0, 1), ("validation", 1, 2), ("test", 2, 3)])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir)
            for name, start, stop in bounds:
                filename = "dev.tsv" if name == "validation" else f"{name}.tsv"
                write_classifier_tsv(output_root / filename, sources[start:stop])

            artifacts = sorted(path.name for path in output_root.iterdir())
            self.assertEqual(artifacts, ["dev.tsv", "test.tsv", "train.tsv"])
            rows = []
            for artifact in artifacts:
                with (output_root / artifact).open(encoding="utf-8", newline="") as stream:
                    rows.extend(csv.DictReader(stream, delimiter="\t"))

            self.assertEqual(len(rows), 3)
            self.assertEqual({row["OutLabel"] for row in rows}, {"alpha", "beta"})
            self.assertEqual(len({(row["OutLabel"], row["text"]) for row in rows}), 3)


if __name__ == "__main__":
    unittest.main()
