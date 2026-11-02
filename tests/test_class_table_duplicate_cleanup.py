"""Regression: deduplicate active metadata without losing pending AI suggestions."""
from __future__ import annotations

import contextlib
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from BertScript import class_table_metadata as metadata
from BertScript import migrate_class_table as legacy

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "ClassesTree" / "review" / "class-table-duplicate-ai-proposals-20261102.csv"
EXPECTED = {
    "Autonomous Car Industry": (2064, "自動駕駛汽車產業", 140, "自駕車產業"),
    "Navigational Warning-Fishing in Unauthorized Zone": (
        2459, "航行警告－未經許可區域漁撈作業", 1224,
        "未授權區域捕漁相關航行警告",
    ),
    "Timestamp": (2608, "時間戳記", 1739, "時間戳"),
    "Hepatology": (2712, "肝臟病學", 2335, "肝臟病學"),
}
AI_NOTES = "AI新增｜來源=TopicTree.csv｜理由=ClassTable缺少對應類別｜狀態=待人工審核"


class DuplicateClassTableCleanupTests(unittest.TestCase):
    def test_authoritative_file_is_unique_canonical_and_has_no_lost_rows(self):
        rows = metadata.read_rows(metadata.DEFAULT_CSV)
        self.assertEqual(len(rows), 2707)
        table = metadata.load_class_table()
        self.assertEqual(len(table), 2707)
        self.assertEqual(
            metadata.DEFAULT_CSV.read_text(encoding="utf-8-sig"),
            metadata.table_to_csv(table),
        )
        self.assertEqual(len({row["ClassLabel"] for row in rows}), len(rows))
        for key, (_, _, _, retained_ct) in EXPECTED.items():
            with self.subTest(key=key):
                self.assertEqual(table[key]["CT"], retained_ct)
                self.assertIn("Notes", table[key])
        # The earlier Hepatology record was itself an AI submission, not
        # a human-approved translation. Preserve that actual provenance.
        self.assertEqual(table["Hepatology"]["Notes"], AI_NOTES)

    def test_review_archive_keeps_exact_ai_payloads_and_source_line_provenance(self):
        with REVIEW.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            self.assertEqual(
                reader.fieldnames,
                ["OriginalLine", "ClassLabel", "CT", "Explanation", "Notes",
                 "RetainedLine", "RetainedCT", "ReviewStatus"],
            )
            entries = list(reader)
        self.assertEqual(len(entries), 4)
        self.assertEqual({row["ClassLabel"] for row in entries}, set(EXPECTED))
        retained = metadata.load_class_table()
        for row in entries:
            key = row["ClassLabel"]
            with self.subTest(key=key):
                old_line, ai_ct, kept_line, kept_ct = EXPECTED[key]
                self.assertEqual(int(row["OriginalLine"]), old_line)
                self.assertEqual(row["CT"], ai_ct)
                self.assertEqual(int(row["RetainedLine"]), kept_line)
                self.assertEqual(row["RetainedCT"], kept_ct)
                self.assertEqual(row["Explanation"], "")
                self.assertEqual(row["Notes"], AI_NOTES)
                self.assertEqual(row["ReviewStatus"], "待人工審核")
                self.assertEqual(retained[key]["CT"], kept_ct)
        self.assertNotEqual(
            retained["Autonomous Car Industry"]["CT"],
            next(x["CT"] for x in entries
                 if x["ClassLabel"] == "Autonomous Car Industry"),
        )

    def test_append_preflight_blocks_all_archived_duplicates_before_writes(self):
        table = metadata.load_class_table()
        with REVIEW.open(encoding="utf-8-sig", newline="") as handle:
            archive = list(csv.DictReader(handle))
        candidates = {
            item["ClassLabel"]: {
                "CT": item["CT"], "Explanation": item["Explanation"],
                "Notes": item["Notes"],
            } for item in archive
        }
        with self.assertRaisesRegex(
            metadata.MetadataError, "cannot append existing ClassLabel"
        ):
            metadata.check_append_candidates(table, candidates)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "proposals.csv"
            path.write_text(metadata.table_to_csv(candidates), encoding="utf-8")
            before = path.read_bytes()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    metadata.main([
                        "check-append", "--candidates", str(path), "--json"
                    ])
            self.assertEqual(caught.exception.code, 2)
            self.assertIn("cannot append existing ClassLabel", stderr.getvalue())
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(metadata.load_class_table()), 2707)

    def test_historical_allow_mode_is_exact_and_never_approves_old_ai_notes(self):
        original = {
            old: dict(fields)
            for old, (_new, fields)
            in legacy.HISTORICAL_LABEL_NORMALIZATIONS.items()
        }
        actual = {
            new: {**dict(fields), "Notes": ""}
            for _old, (new, fields)
            in legacy.HISTORICAL_LABEL_NORMALIZATIONS.items()
        }
        old_debt = legacy.HISTORICAL_CT_CORRECTIONS["Africa Debt"]
        original["Africa Debt"] = dict(old_debt["source"])
        actual["Africa Debt"] = {**old_debt["target"], "Notes": ""}
        actual["Additional Undated AI"] = {
            "CT": "未核准翻譯", "Explanation": "",
            "Notes": legacy.HISTORICAL_AI_NOTES_PREFIX,
        }
        actual["Additional With Reminder"] = {
            "CT": "提醒審核", "Explanation": "",
            "Notes": legacy.HISTORICAL_AI_NOTES_PREFIX + "｜提醒=請人工複核",
        }
        with mock.patch.object(legacy, "correct_known"):
            legacy.verify(original, actual, allow_pending_additions=True)
            with self.assertRaisesRegex(metadata.MetadataError, "row count"):
                legacy.verify(original, actual, allow_pending_additions=False)
            bad_original = {k: dict(v) for k, v in original.items()}
            bad_original["TimeStamp"]["CT"] = "不可偷偷改動來源"
            with self.assertRaisesRegex(
                metadata.MetadataError, "unexpected historical rename source"
            ):
                legacy.verify(
                    bad_original, actual, allow_pending_additions=True
                )
            tampered_translation = {
                k: dict(v) for k, v in actual.items()
            }
            tampered_translation["Africa Debt"]["CT"] = "未核對翻譯"
            with self.assertRaisesRegex(
                metadata.MetadataError, "guarded historical CT correction differs"
            ):
                legacy.verify(
                    original, tampered_translation, allow_pending_additions=True
                )
            for bad_note in (
                legacy.HISTORICAL_AI_NOTES_PREFIX.replace(
                    "待人工審核", "已核准"
                ),
                legacy.HISTORICAL_AI_NOTES_PREFIX + "｜額外=不可加入",
                "AI新增｜來源=其他｜理由=ClassTable缺少對應類別｜狀態=待人工審核",
            ):
                with self.subTest(note=bad_note):
                    tampered = {
                        k: dict(v) for k, v in actual.items()
                    }
                    tampered["Additional Undated AI"]["Notes"] = bad_note
                    with self.assertRaises(metadata.MetadataError):
                        legacy.verify(
                            original, tampered, allow_pending_additions=True
                        )

    def test_preflight_only_checks_unique_ids_not_human_approval(self):
        base = {"Existing": {"CT": "舊翻譯", "Explanation": "", "Notes": ""}}
        proposed = {"New": {"CT": "候選新翻譯", "Explanation": "",
                            "Notes": "AI新增｜狀態=待人工審核"}}
        result = metadata.check_append_candidates(base, proposed)
        self.assertEqual(result["NewRows"], 1)
        self.assertTrue(result["AppendHasNoIdConflict"])
        self.assertFalse(result["HumanApprovalGranted"])
        self.assertFalse(result["FilesModified"])
        self.assertEqual(set(base), {"Existing"})
        with self.assertRaises(metadata.MetadataError):
            metadata.check_append_candidates(
                base, {"Existing": proposed["New"]}
            )


if __name__ == "__main__":
    unittest.main()
