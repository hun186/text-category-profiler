import unittest

from DatasetConverter.source_collection import discover_source_files


class DatasetSourceCollectionTests(unittest.TestCase):
    def test_discovery_filters_excluded_paths_and_sorts_results(self):
        calls = []
        results = {
            "root-b": ["root-b/z.txt", "root-b/UnTagged/ignored.txt"],
            "root-a": ["root-a/c.AI2", "root-a/UnSpec/ignored.sql3"],
        }

        def walker(root, **kwargs):
            calls.append((root, kwargs))
            return results[root]

        paths = discover_source_files(
            ["root-b", "root-a"],
            r".*",
            walker=walker,
        )

        self.assertEqual(paths, ["root-a/c.AI2", "root-b/z.txt"])
        self.assertEqual([call[0] for call in calls], ["root-b", "root-a"])
        self.assertEqual(
            calls[0][1],
            {
                "Extension": ["txt", "AI2", "sql3"],
                "FullPathFNrePat": r".*",
            },
        )

    def test_discovery_does_not_share_results_between_calls(self):
        def walker(root, **kwargs):
            return [f"{root}/sample.txt"]

        first = discover_source_files(["first"], ".*", walker=walker)
        second = discover_source_files(["second"], ".*", walker=walker)

        self.assertEqual(first, ["first/sample.txt"])
        self.assertEqual(second, ["second/sample.txt"])


if __name__ == "__main__":
    unittest.main()
