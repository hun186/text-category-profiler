import unittest

from DatasetConverter.source_metadata import (
    get_source_from_file_name,
    getSrcFromFileName,
)


class SourceMetadataPolicyTests(unittest.TestCase):
    def test_regular_posix_path_uses_two_directories_before_label(self):
        result = get_source_from_file_name(
            "/root/news wires/reuters/#T#[world politics]/article.txt",
            ["World Politics"],
        )

        self.assertEqual(result, ("News Wires", "Reuters"))

    def test_books_windows_path_uses_directories_around_label(self):
        result = get_source_from_file_name(
            r"C:\Books\Chinese articles\#T#[classics]\anthology\article.txt",
            ["Classics"],
        )

        self.assertEqual(result, ("Chinese Articles", "Anthology"))

    def test_comma_separated_label_marker_matches_requested_label(self):
        result = get_source_from_file_name(
            "/data/journals/science/#T#[biology, earth science]/article.txt",
            ["Earth Science"],
        )

        self.assertEqual(result, ("Journals", "Science"))

    def test_unknown_label_preserves_empty_legacy_metadata(self):
        result = get_source_from_file_name(
            "/data/journals/science/#T#[biology]/article.txt",
            ["Physics"],
        )

        self.assertEqual(result, (None, None))

    def test_legacy_public_name_and_keyword_arguments_are_preserved(self):
        result = getSrcFromFileName(
            FileName="/data/journals/science/#T#[biology]/article.txt",
            LabelList=["Biology"],
        )

        self.assertEqual(result, ("Journals", "Science"))


if __name__ == "__main__":
    unittest.main()
