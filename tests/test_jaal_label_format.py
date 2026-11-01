"""BL-001-independent, dependency-free newline formatting contract."""
import unittest

from ClassesTree.Visualization.jaal.label_format import (
    MAX_LABEL_LINES, MAX_LABEL_LINE_CHARS, wrapped_classlabel,
)


class EmbeddedJaalLabelFormatTests(unittest.TestCase):
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

    def test_ellipsized_name_does_not_modify_source_or_identity(self):
        name = "TW-" + "LongClassificationLabel" * 8
        label = wrapped_classlabel(name)
        self.assertTrue(label.endswith("…"))
        self.assertEqual(name, "TW-" + "LongClassificationLabel" * 8)
        self.assertRaises(TypeError, wrapped_classlabel, None)


if __name__ == "__main__":
    unittest.main()
