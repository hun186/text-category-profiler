import unittest

from DatasetConverter.sample_pipeline import collect_reader_results


class CollectReaderResultsTests(unittest.TestCase):
    def test_collects_rows_in_worker_result_order(self):
        first = {"file": "a.txt", "OutLabel": "alpha", "text": "one"}
        second = {"file": "b.txt", "OutLabel": "beta", "text": "two"}

        collected = collect_reader_results(
            [([first], ({"alpha"}, 1)), ([second], None)]
        )

        self.assertEqual(collected.rows, (first, second))
        self.assertEqual(
            collected.multi_label_counts, (({"alpha"}, 1), None)
        )

    def test_empty_results_keep_the_sample_boundary_empty(self):
        collected = collect_reader_results([])

        self.assertEqual(collected.rows, ())
        self.assertEqual(collected.multi_label_counts, ())

    def test_rejects_reader_result_with_missing_contract_member(self):
        with self.assertRaisesRegex(ValueError, "index 0.*rows.*multi-label"):
            collect_reader_results([([], )])

    def test_rejects_non_sequence_rows(self):
        with self.assertRaisesRegex(TypeError, "reader rows at index 0"):
            collect_reader_results([({"file": "a.txt"}, None)])


if __name__ == "__main__":
    unittest.main()
