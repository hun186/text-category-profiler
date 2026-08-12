import unittest
from dataclasses import FrozenInstanceError

from DatasetConverter.source_collection import discover_source_files
from DatasetConverter.source_collection import discover_source_spec
from DatasetConverter.source_collection import SourceRole
from DatasetConverter.source_collection import SourceSpec


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

    def test_source_spec_preserves_role_and_discovery_policy(self):
        calls = []

        def walker(root, **kwargs):
            calls.append((root, kwargs))
            return [f"{root}/z.txt", f"{root}/UnTagged/a.txt"]

        source = SourceSpec(
            role=SourceRole.REGULAR,
            root_paths=("root-b", "root-a"),
            filename_pattern=r".*#T#.*",
        )

        self.assertEqual(
            discover_source_spec(source, walker=walker),
            ["root-a/z.txt", "root-b/z.txt"],
        )
        self.assertEqual(source.role, SourceRole.REGULAR)
        with self.assertRaises(FrozenInstanceError):
            source.role = SourceRole.FIXED_TEST
        self.assertEqual(
            calls[0][1],
            {
                "Extension": ["txt", "AI2", "sql3"],
                "FullPathFNrePat": r".*#T#.*",
            },
        )

    def test_fixed_test_spec_can_preserve_unfiltered_legacy_discovery(self):
        calls = []

        def walker(root, **kwargs):
            calls.append((root, kwargs))
            return [f"{root}/z.txt", f"{root}/UnTagged/a.txt"]

        source = SourceSpec(
            role=SourceRole.FIXED_TEST,
            root_paths=("fixed",),
            excluded_path_parts=(),
        )

        self.assertEqual(
            discover_source_spec(source, walker=walker),
            ["fixed/UnTagged/a.txt", "fixed/z.txt"],
        )
        self.assertEqual(calls, [("fixed", {"Extension": ["txt", "AI2", "sql3"]})])

    def test_source_spec_empty_roots_do_not_call_walker(self):
        source = SourceSpec(role=SourceRole.FIXED_TEST, root_paths=())

        def walker(root, **kwargs):
            self.fail("walker must not run for an empty source")

        self.assertEqual(discover_source_spec(source, walker=walker), [])


if __name__ == "__main__":
    unittest.main()
