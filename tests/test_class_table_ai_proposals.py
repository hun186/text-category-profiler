"""Dependency-free tests for the read-only BL-002 proposal validation gate."""

import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from BertScript import class_table_ai_proposals as gate
from BertScript import class_table_metadata as metadata


def note(kind="AI新增", date="2026-10-31", source="新聞文本",
         reason="現有分類範圍不足", status="待人工審核"):
    return (
        f"{kind}｜日期={date}｜來源={source}｜理由={reason}｜狀態={status}"
    )


def row(ct, explanation="", notes=""):
    return {"CT": ct, "Explanation": explanation, "Notes": notes}


class CandidateGateTests(unittest.TestCase):
    def setUp(self):
        self.base = {"Existing": row("既有中文", "人工說明", "人工備註")}
        self.snapshot = {key: value.copy() for key, value in self.base.items()}

    def test_additions_and_supplements_are_pending_and_read_only(self):
        candidates = {
            "New": row("新增中文", "候選說明", note()),
            "Existing": row("既有中文", "AI建議的新說明",
                            note(kind="AI補充")),
        }
        original_candidates = {key: value.copy() for key, value in candidates.items()}
        result = gate.audit_proposals(self.base, candidates)
        self.assertEqual(result["AI新增"], ["New"])
        self.assertEqual(result["AI補充"], ["Existing"])
        self.assertEqual(result["CandidateCount"], 2)
        self.assertFalse(result["Approved"])
        self.assertFalse(result["AuthoritativeFilesModified"])
        self.assertEqual(result["Status"], "待人工審核")
        self.assertEqual(self.base, self.snapshot)
        self.assertEqual(candidates, original_candidates)

    def test_notes_support_url_query_equals_and_unicode(self):
        kind, fields = gate.parse_provenance(
            note(source="https://example.org/?a=1&b=2", reason="有中文,逗號和等號=a"),
            "New",
        )
        self.assertEqual(kind, "AI新增")
        self.assertEqual(fields["來源"], "https://example.org/?a=1&b=2")

    def test_rejects_missing_or_malformed_notes(self):
        for bad in (
            "", "人工備註", "AI新增｜日期=2026-10-31",
            "AI新增｜來源=檔案｜日期=2026-10-31｜理由=x｜狀態=待人工審核",
            note(reason=""), note(source=" "),
            note() + "｜審核=通過",
        ):
            with self.subTest(bad=bad), self.assertRaises(metadata.MetadataError):
                gate.audit_proposals(self.base, {"New": row("新增", notes=bad)})

    def test_rejects_forged_approval_even_for_valid_candidate(self):
        with self.assertRaisesRegex(metadata.MetadataError, "not an approval"):
            gate.audit_proposals(
                self.base, {"New": row("新增", notes=note(status="已核准"))}
            )

    def test_rejects_invalid_or_noncanonical_dates(self):
        for bad in ("2026-02-30", "2026-2-3", "yesterday"):
            with self.subTest(bad=bad), self.assertRaises(metadata.MetadataError):
                gate.audit_proposals(
                    self.base, {"New": row("新增", notes=note(date=bad))}
                )

    def test_new_proposal_cannot_replace_existing_label(self):
        with self.assertRaisesRegex(metadata.MetadataError, "conflicts"):
            gate.audit_proposals(
                self.base, {"Existing": row("改名", notes=note())}
            )

    def test_supplement_requires_existing_label_and_preserves_ct(self):
        with self.assertRaisesRegex(metadata.MetadataError, "requires an existing"):
            gate.audit_proposals(
                self.base, {"New": row("新", notes=note(kind="AI補充"))}
            )
        with self.assertRaisesRegex(metadata.MetadataError, "preserve the human CT"):
            gate.audit_proposals(
                self.base,
                {"Existing": row("擅自覆寫", notes=note(kind="AI補充"))},
            )
        self.assertEqual(self.base, self.snapshot)

    def test_cli_emits_audit_without_modifying_either_input(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "base.csv"
            candidates = Path(directory) / "candidates.csv"
            base.write_text(metadata.table_to_csv(self.base), encoding="utf-8")
            candidates.write_text(metadata.table_to_csv({
                "New": row("新增", notes=note())
            }), encoding="utf-8")
            before = (base.read_bytes(), candidates.read_bytes())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(
                    gate.main(["--base", str(base), "--candidates", str(candidates),
                               "--json"]), 0
                )
            report = json.loads(out.getvalue())
            self.assertFalse(report["Approved"])
            self.assertEqual(report["AI新增"], ["New"])
            self.assertEqual(before, (base.read_bytes(), candidates.read_bytes()))
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),
                             ["base.csv", "candidates.csv"])

    def test_csv_loader_rejects_duplicate_labels_before_audit(self):
        with TemporaryDirectory() as directory:
            candidate = Path(directory) / "duplicate.csv"
            candidate.write_text(
                "ClassLabel,CT,Explanation,Notes\n"
                "A,甲,,\nA,乙,,\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(metadata.MetadataError, "duplicate"):
                metadata.load_class_table(candidate)


if __name__ == "__main__":
    unittest.main()
