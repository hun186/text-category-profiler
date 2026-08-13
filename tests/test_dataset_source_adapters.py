import unittest

from DatasetConverter.source_adapters import adapt_czj_sample_records


class AdaptCzjSampleRecordsTests(unittest.TestCase):
    def test_removes_persisted_index_and_preserves_sample_values(self):
        source = {
            "index": 7,
            "file": "source.txt",
            "InLabel": "alpha",
            "OutLabel": "alpha",
            "text": "sample",
            "PartNO": 2,
        }

        adapted = adapt_czj_sample_records([source])

        self.assertEqual(
            adapted,
            (
                {
                    "file": "source.txt",
                    "InLabel": "alpha",
                    "OutLabel": "alpha",
                    "text": "sample",
                    "PartNO": 2,
                },
            ),
        )
        self.assertEqual(source["index"], 7)

    def test_preserves_record_order_and_extra_provenance_columns(self):
        adapted = adapt_czj_sample_records(
            [
                {"index": 0, "file": "first.txt", "Src": "one"},
                {"index": 1, "file": "second.txt", "SrcType": "archive"},
            ]
        )

        self.assertEqual([row["file"] for row in adapted], ["first.txt", "second.txt"])
        self.assertEqual(adapted[0]["Src"], "one")
        self.assertEqual(adapted[1]["SrcType"], "archive")

    def test_rejects_missing_persisted_index_with_row_diagnostic(self):
        with self.assertRaisesRegex(ValueError, "row at index 0.*persisted index"):
            adapt_czj_sample_records([{"file": "source.txt"}])

    def test_rejects_non_mapping_records_with_row_diagnostic(self):
        with self.assertRaisesRegex(TypeError, "row at index 0.*mapping"):
            adapt_czj_sample_records([["not", "a", "record"]])


if __name__ == "__main__":
    unittest.main()
