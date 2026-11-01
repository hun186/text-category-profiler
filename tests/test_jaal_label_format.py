"""BL-001-independent, dependency-free newline formatting contract."""
import unittest

from ClassesTree.Visualization.jaal.label_format import (
    MAX_LABEL_LINES, MAX_LABEL_LINE_CHARS, wrapped_classlabel,
    search_full_classlabel, LABEL_RENDERER_REVISION, prepare_embedded_jaal_nodes,
)


class EmbeddedJaalLabelFormatTests(unittest.TestCase):
    def test_production_label_adapter_preserves_id_and_input_dataframe(self):
        try:
            import pandas as pd
        except ImportError as exc:
            self.skipTest(f"Optional pandas integration dependency absent: {exc}")
        full = "CN Intelligence And Espionage Against TW"
        frame = pd.DataFrame([{"id": full, "depth": 2},
                              {"id": "TW Affairs", "depth": 0}])
        formatted = prepare_embedded_jaal_nodes(frame)
        self.assertNotIn("label", frame.columns)
        self.assertEqual(formatted.loc[0, "id"], full)
        self.assertEqual(formatted.loc[0, "title"], full)
        self.assertIn(chr(10), formatted.loc[0, "label"])
        self.assertEqual(formatted.loc[1, "label"], "TW Affairs")
        self.assertEqual(formatted["depth"].tolist(), [2, 0])
        self.assertEqual(LABEL_RENDERER_REVISION, "multiline-labels-v2")
        with self.assertRaisesRegex(ValueError, "id column"):
            prepare_embedded_jaal_nodes(pd.DataFrame({"label": ["hi"]}))

    def test_short_label_stays_unchanged(self):
        self.assertEqual(wrapped_classlabel("TW Affairs"), "TW Affairs")

    def test_long_label_explicitly_wraps_instead_of_relying_on_vis_options(self):
        original = "CN Intelligence And Espionage Against TW"
        label = wrapped_classlabel(original)
        self.assertIn("\n", label)
        self.assertEqual(label, "CN Intelligence\nAnd Espionage\nAgainst TW")
        self.assertTrue(all(len(line) <= MAX_LABEL_LINE_CHARS
                            for line in label.splitlines()))

    def test_long_unbroken_word_and_hyphenated_classlabels_are_bounded(self):
        for name in (
            "TW Election-CPC Election Interference",
            "Cross-Strait Semiconductor Trade Restrictions",
            "A" * 130,
        ):
            with self.subTest(name=name):
                rendered = wrapped_classlabel(name)
                lines = rendered.splitlines()
                self.assertLessEqual(len(lines), MAX_LABEL_LINES)
                self.assertTrue(all(len(line) <= MAX_LABEL_LINE_CHARS
                                    for line in lines))
                self.assertIn("\n", rendered)
                self.assertNotEqual(rendered, name)

    def test_search_matches_full_identifier_across_newlines_and_ellipses(self):
        full = "TW-" + "LongClassificationLabel" * 8
        display = wrapped_classlabel(full)
        nodes = [
            {"id": full, "label": display},
            {"id": "TW Affairs", "label": "TW Affairs"},
        ]
        data = {"nodes": nodes, "edges": []}
        for query in (full, "LongClassificationLabel" * 3, full[-16:]):
            result = search_full_classlabel(data, query)
            self.assertIs(result, data)
            self.assertFalse(nodes[0]["hidden"])
            self.assertTrue(nodes[1]["hidden"])
            self.assertEqual(nodes[0]["label"], display)
        search_full_classlabel(data, "")
        self.assertFalse(any(n["hidden"] for n in nodes))

    def test_ellipsized_name_does_not_modify_source_or_identity(self):
        name = "TW-" + "LongClassificationLabel" * 8
        label = wrapped_classlabel(name)
        self.assertTrue(label.endswith("…"))
        self.assertEqual(name, "TW-" + "LongClassificationLabel" * 8)
        self.assertRaises(TypeError, wrapped_classlabel, None)


if __name__ == "__main__":
    unittest.main()
