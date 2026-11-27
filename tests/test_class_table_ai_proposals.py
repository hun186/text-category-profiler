"""Dependency-free tests for the read-only BL-002 proposal validation gate."""

import contextlib
import io
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
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


    @staticmethod
    def write_edges(path, edges):
        import csv
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["#母類別", "子類別", "日期", "關係", "備註"])
            for edge in edges:
                parent, child = edge[:2]
                relation = edge[2] if len(edge) > 2 else "contains"
                writer.writerow([parent, child, "20261031", relation, ""])

    def test_proposed_edges_match_exact_ai_addition_nodes(self):
        with TemporaryDirectory() as directory:
            base_tree = Path(directory) / "tree.csv"
            proposed = Path(directory) / "new-edges.csv"
            self.write_edges(base_tree, [("Root", "Existing")])
            self.write_edges(proposed, [("Root", "New"), ("New", "Another")])
            result = gate.audit_proposed_graph_nodes(
                ["New", "Another"], base_tree=base_tree, proposed_edges=proposed
            )
            self.assertEqual(result["GraphNodeAlignment"], "matched")
            self.assertEqual(result["ProposedEdgesStructurallyChecked"], 2)
            self.assertEqual(result["NewGraphNodes"], ["Another", "New"])
            self.assertFalse(result["GraphRelationshipsApproved"])

    def test_proposed_edges_reject_unproposed_graph_nodes(self):
        with TemporaryDirectory() as directory:
            base_tree = Path(directory) / "tree.csv"
            proposed = Path(directory) / "edges.csv"
            self.write_edges(base_tree, [("Root", "Old")])
            self.write_edges(proposed, [("Root", "New"), ("New", "Unexpected")])
            with self.assertRaisesRegex(metadata.MetadataError,
                                        "missing_in_candidates=.*Unexpected"):
                gate.audit_proposed_graph_nodes(
                    ["New"], base_tree=base_tree, proposed_edges=proposed
                )

    def test_proposed_edges_reject_unconnected_ai_additions(self):
        with TemporaryDirectory() as directory:
            base_tree = Path(directory) / "tree.csv"
            proposed = Path(directory) / "edges.csv"
            self.write_edges(base_tree, [("Root", "Old")])
            self.write_edges(proposed, [("Root", "New")])
            with self.assertRaisesRegex(metadata.MetadataError,
                                        "missing_in_edges=.*Absent"):
                gate.audit_proposed_graph_nodes(
                    ["New", "Absent"], base_tree=base_tree,
                    proposed_edges=proposed,
                )


    def test_proposed_edges_reject_self_references(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "base.csv"
            proposed = Path(directory) / "proposed.csv"
            self.write_edges(base, [("Root", "Existing")])
            self.write_edges(proposed, [("New", "New"), ("Root", "New")])
            with self.assertRaisesRegex(metadata.MetadataError, "self-edge"):
                gate.audit_proposed_graph_nodes(
                    ["New"], base_tree=base, proposed_edges=proposed
                )

    def test_proposed_edges_reject_exact_duplicate_relations(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "base.csv"
            proposed = Path(directory) / "proposed.csv"
            self.write_edges(base, [("Root", "Existing")])
            for rows in (
                [("Root", "New"), ("Root", "New")],
                [("Root", "Existing"), ("Root", "New")],
            ):
                with self.subTest(rows=rows):
                    self.write_edges(proposed, rows)
                    with self.assertRaisesRegex(metadata.MetadataError, "duplicate"):
                        gate.audit_proposed_graph_nodes(
                            ["New"], base_tree=base, proposed_edges=proposed
                        )

    def test_proposed_contains_cycle_is_rejected_without_updating_graph(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "base.csv"
            proposed = Path(directory) / "proposed.csv"
            self.write_edges(base, [("Root", "Existing")])
            self.write_edges(proposed, [("Existing", "New"), ("New", "Root")])
            original = (base.read_bytes(), proposed.read_bytes())
            with self.assertRaisesRegex(metadata.MetadataError, "contains.*cycle"):
                gate.audit_proposed_graph_nodes(
                    ["New"], base_tree=base, proposed_edges=proposed
                )
            self.assertEqual((base.read_bytes(), proposed.read_bytes()), original)

    def test_nonhierarchical_reciprocal_relation_is_not_called_a_contains_cycle(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "base.csv"
            proposed = Path(directory) / "proposed.csv"
            self.write_edges(base, [("Root", "Existing")])
            self.write_edges(proposed, [
                ("Root", "New", "contains"),
                ("New", "Root", "can be improved with"),
            ])
            report = gate.audit_proposed_graph_nodes(
                ["New"], base_tree=base, proposed_edges=proposed
            )
            self.assertEqual(report["ProposedEdgesStructurallyChecked"], 2)
            self.assertFalse(report["GraphRelationshipsApproved"])


    def test_local_article_manifest_links_exact_notes_and_stays_read_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / "article.txt"
            article.write_text("中文新聞正文和來源證據", encoding="utf-8")
            source = "https://example.org/news/1"
            manifest = root / "evidence.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "articles": [{
                    "source": source, "file": "article.txt",
                    "sha256": hashlib.sha256(article.read_bytes()).hexdigest(),
                }],
            }), encoding="utf-8")
            candidates = {"New": row("新增", notes=note(source=source))}
            baseline = {p.name: p.read_bytes() for p in root.iterdir()}
            result = gate.audit_local_article_evidence(candidates, manifest)
            self.assertEqual(result["EvidenceArticlesChecked"], 1)
            self.assertEqual(result["CandidateSourcesMatched"], 1)
            self.assertTrue(result["EvidenceByteHashesVerified"])
            self.assertFalse(result["SourceAuthenticityVerified"])
            self.assertFalse(result["EvidenceSemanticRelevanceVerified"])
            self.assertFalse(result["Approved"])
            self.assertEqual(baseline, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_local_evidence_rejects_duplicate_json_keys_at_all_depths(self):
        # JSON's default last-key-wins behavior previously let an apparent
        # empty articles list or forged source be shadowed by a valid one.
        # The manifest audit must reject ambiguity before trusting hashes.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / "article.txt"
            article.write_text("中文來源證據", encoding="utf-8")
            digest = hashlib.sha256(article.read_bytes()).hexdigest()
            entry = {
                "source": "doc", "file": "article.txt", "sha256": digest,
            }
            manifest = root / "manifest.json"
            candidate = {"New": row("新增", notes=note(source="doc"))}
            ambiguous_root = (
                '{"schema_version":1,"articles":[],"articles":['
                + json.dumps(entry) + ']}'
            )
            ambiguous_article = (
                '{"schema_version":1,"articles":[{"source":"forged",'
                '"source":"doc","file":"article.txt","sha256":'
                + json.dumps(digest) + '}]}'
            )
            for payload in (ambiguous_root, ambiguous_article):
                with self.subTest(payload=payload[:45]):
                    manifest.write_text(payload, encoding="utf-8")
                    original = (manifest.read_bytes(), article.read_bytes())
                    with self.assertRaisesRegex(
                        metadata.MetadataError, "duplicate JSON key"
                    ):
                        gate.audit_local_article_evidence(candidate, manifest)
                    self.assertEqual(
                        (manifest.read_bytes(), article.read_bytes()),
                        original,
                    )

    def test_local_evidence_rejects_missing_source_and_duplicate_content(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / "article.txt"
            article.write_text("sample", encoding="utf-8")
            digest = hashlib.sha256(article.read_bytes()).hexdigest()
            manifest = root / "evidence.json"
            def write(items):
                manifest.write_text(
                    json.dumps({"schema_version": 1, "articles": items}),
                    encoding="utf-8",
                )
            one = {"source": "doc-1", "file": "article.txt", "sha256": digest}
            write([one])
            with self.assertRaisesRegex(metadata.MetadataError, "not found"):
                gate.audit_local_article_evidence(
                    {"New": row("新增", notes=note(source="not-in-manifest"))}, manifest)
            write([one, {"source": "doc-2", "file": "article.txt", "sha256": digest}])
            with self.assertRaisesRegex(metadata.MetadataError, "duplicate article content"):
                gate.audit_local_article_evidence(
                    {"New": row("新增", notes=note(source="doc-1"))}, manifest)
            write([one, one])
            with self.assertRaisesRegex(metadata.MetadataError, "duplicate evidence source"):
                gate.audit_local_article_evidence(
                    {"New": row("新增", notes=note(source="doc-1"))}, manifest)

    def test_local_evidence_rejects_tampering_and_escape(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / "article.txt"
            article.write_text("unaltered", encoding="utf-8")
            manifest = root / "evidence.json"
            candidates = {"New": row("新增", notes=note(source="doc"))}
            def check(rel, digest):
                manifest.write_text(json.dumps({
                    "schema_version": 1,
                    "articles": [{"source": "doc", "file": rel, "sha256": digest}],
                }), encoding="utf-8")
                return gate.audit_local_article_evidence(candidates, manifest)
            digest = hashlib.sha256(article.read_bytes()).hexdigest()
            with self.assertRaisesRegex(metadata.MetadataError, "unsafe relative"):
                check("../article.txt", digest)
            with self.assertRaisesRegex(metadata.MetadataError, "unsafe relative"):
                check(".." + chr(92) + "article.txt", digest)
            with self.assertRaisesRegex(metadata.MetadataError, "sha256 mismatch"):
                check("article.txt", "0" * 64)
            if hasattr(Path, "symlink_to"):
                outside = root.parent / (root.name + "-outside.txt")
                outside.write_text("outside", encoding="utf-8")
                link = root / "link.txt"
                try:
                    link.symlink_to(outside)
                    with self.assertRaisesRegex(metadata.MetadataError, "escapes"):
                        check("link.txt", hashlib.sha256(outside.read_bytes()).hexdigest())
                except (NotImplementedError, OSError):
                    pass
                finally:
                    outside.unlink(missing_ok=True)

    def test_local_evidence_cli_keeps_official_files_untouched(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.csv"
            candidates = root / "candidates.csv"
            article = root / "a.txt"
            manifest = root / "manifest.json"
            base.write_text(metadata.table_to_csv(self.base), encoding="utf-8")
            candidates.write_text(metadata.table_to_csv({
                "New": row("新增", notes=note(source="local-a")),
            }), encoding="utf-8")
            article.write_text("正文", encoding="utf-8")
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "articles": [{"source": "local-a", "file": "a.txt",
                              "sha256": hashlib.sha256(article.read_bytes()).hexdigest()}],
            }), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(gate.main([
                    "--base", str(base), "--candidates", str(candidates),
                    "--evidence-manifest", str(manifest), "--json",
                ]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["EvidenceArticlesChecked"], 1)
            self.assertFalse(result["Approved"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_optional_text_review_reports_formatting_duplicates_read_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for i, body in enumerate([
                "中文 Café\n第二段".encode(),
                "\ufeff中文 Cafe\u0301\r\n  第二段 ".encode(),
                "中文 Café 第二段。".encode(),
            ]):
                filename = f"a{i}.txt"
                (root / filename).write_bytes(body)
                records.append({"source": f"doc-{i}", "file": filename,
                                "sha256": hashlib.sha256(body).hexdigest()})
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 1, "articles": records}),
                                encoding="utf-8")
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            default = gate.audit_local_article_evidence(candidates, manifest)
            self.assertNotIn("TextReviewStatus", default)
            report = gate.audit_local_article_evidence(candidates, manifest, review_text=True)
            self.assertEqual(report["TextReviewStatus"], "REVIEW_REQUIRED")
            self.assertEqual(report["NormalizedDuplicateSourceGroups"], [["doc-0", "doc-1"]])
            self.assertEqual(report["TextReviewArticlesChecked"], 3)
            self.assertFalse(report["NearDuplicateSearchPerformed"])
            self.assertFalse(report["Approved"])
            self.assertFalse(report["SourceAuthenticityVerified"])
            self.assertFalse(report["EvidenceSemanticRelevanceVerified"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_optional_text_review_rejects_invalid_utf8_blank_and_nul(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / "a.txt"
            manifest = root / "manifest.json"
            candidates = {"New": row("新增", notes=note(source="doc"))}
            for body, error in [(bytes([255]), "UTF-8"), (bytes([32, 13, 10]), "blank"),
                                (bytes([120, 0, 121]), "NUL")]:
                with self.subTest(error=error):
                    article.write_bytes(body)
                    manifest.write_text(json.dumps({"schema_version": 1, "articles": [
                        {"source": "doc", "file": "a.txt",
                         "sha256": hashlib.sha256(body).hexdigest()}
                    ]}), encoding="utf-8")
                    self.assertTrue(gate.audit_local_article_evidence(
                        candidates, manifest)["EvidenceByteHashesVerified"])
                    with self.assertRaisesRegex(metadata.MetadataError, error):
                        gate.audit_local_article_evidence(candidates, manifest, review_text=True)

    def test_text_review_cli_requires_manifest(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                gate.main(["--candidates", "not-read.csv", "--review-text"])
        self.assertEqual(raised.exception.code, 2)

    def test_text_review_cli_unique_result_and_no_writes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.csv"
            candidates = root / "candidates.csv"
            article = root / "a.txt"
            manifest = root / "manifest.json"
            base.write_text(metadata.table_to_csv(self.base), encoding="utf-8")
            candidates.write_text(metadata.table_to_csv({
                "New": row("新增", notes=note(source="doc")),
            }), encoding="utf-8")
            article.write_text("新聞正文", encoding="utf-8")
            manifest.write_text(json.dumps({"schema_version": 1, "articles": [
                {"source": "doc", "file": "a.txt",
                 "sha256": hashlib.sha256(article.read_bytes()).hexdigest()}
            ]}), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(gate.main([
                    "--base", str(base), "--candidates", str(candidates),
                    "--evidence-manifest", str(manifest), "--review-text", "--json",
                ]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["TextReviewStatus"], "NO_NORMALIZED_DUPLICATES_FOUND")
            self.assertEqual(report["NormalizedDuplicateSourceGroups"], [])
            self.assertFalse(report["Approved"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def _write_near_review_manifest(self, root, bodies):
        records = []
        for index, body in enumerate(bodies):
            filename = f"near{index}.txt"
            raw = body.encode("utf-8")
            (root / filename).write_bytes(raw)
            records.append({"source": f"doc-{index}", "file": filename,
                            "sha256": hashlib.sha256(raw).hexdigest()})
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "articles": records}),
                            encoding="utf-8")
        return manifest

    def test_near_duplicate_review_chinese_edits_and_excluded_sources(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = "".join(chr(0x4e00 + i) for i in range(180))
            changed = original[:90] + "新聞" + original[90:]
            unrelated = "".join(chr(0x6000 + i) for i in range(180))
            manifest = self._write_near_review_manifest(
                root, [original, changed, unrelated, "短文", "字" * 120])
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            default = gate.audit_local_article_evidence(candidates, manifest, review_text=True)
            self.assertFalse(default["NearDuplicateSearchPerformed"])
            report = gate.audit_local_article_evidence(
                candidates, manifest, review_text=True, review_near_duplicates=True)
            self.assertTrue(report["NearDuplicateSearchPerformed"])
            self.assertEqual(report["TextReviewStatus"], "REVIEW_REQUIRED")
            self.assertEqual(report["NearDuplicateReviewStatus"], "REVIEW_REQUIRED")
            self.assertEqual(report["NearDuplicateEligibleArticles"], 3)
            self.assertEqual(report["NearDuplicateExcludedSources"], ["doc-3", "doc-4"])
            self.assertFalse(report["NearDuplicateCoverageComplete"])
            self.assertEqual(len(report["NearDuplicatePairs"]), 1)
            pair = report["NearDuplicatePairs"][0]
            self.assertEqual(pair["Sources"], ["doc-0", "doc-1"])
            self.assertGreaterEqual(pair["Jaccard"], 0.8)
            self.assertFalse(report["SemanticSimilarityVerified"])
            self.assertFalse(report["Approved"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_near_duplicate_exact_groups_not_repeated_as_pairs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = "".join(chr(0x4e00 + i) for i in range(120))
            manifest = self._write_near_review_manifest(root, [original, " " + original])
            report = gate.audit_local_article_evidence(
                {"New": row("新增", notes=note(source="doc-0"))}, manifest,
                review_text=True, review_near_duplicates=True)
            self.assertEqual(report["NormalizedDuplicateSourceGroups"], [["doc-0", "doc-1"]])
            self.assertEqual(report["NearDuplicatePairs"], [])
            self.assertEqual(report["TextReviewStatus"], "REVIEW_REQUIRED")
            self.assertTrue(report["NearDuplicateCoverageComplete"])

    def test_near_duplicate_budget_and_opt_in_are_enforced(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = "".join(chr(0x4e00 + i) for i in range(120))
            manifest = self._write_near_review_manifest(root, [original, original + "新聞"])
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            with self.assertRaisesRegex(metadata.MetadataError, "requires text review"):
                gate.audit_local_article_evidence(
                    candidates, manifest, review_near_duplicates=True)
            for name, value, message in [
                ("MAX_NEAR_ARTICLES", 1, "article count budget"),
                ("MAX_NEAR_TOTAL_CHARS", 150, "total normalized character budget"),
            ]:
                with self.subTest(name=name), mock.patch.object(gate, name, value):
                    with self.assertRaisesRegex(metadata.MetadataError, message):
                        gate.audit_local_article_evidence(
                            candidates, manifest, review_text=True, review_near_duplicates=True)
            with mock.patch("BertScript.article_text_review.MAX_NEAR_ARTICLE_CHARS", 100):
                with self.assertRaisesRegex(metadata.MetadataError, "article exceeds"):
                    gate.audit_local_article_evidence(
                        candidates, manifest, review_text=True, review_near_duplicates=True)

    def test_near_duplicate_incomplete_no_pair_and_cli_requirement(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, ["短文", "另一篇短文"])
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            report = gate.audit_local_article_evidence(
                candidates, manifest, review_text=True, review_near_duplicates=True)
            self.assertEqual(report["NearDuplicateReviewStatus"], "INCOMPLETE_SHORT_OR_REPETITIVE")
            self.assertFalse(report["NearDuplicateCoverageComplete"])
            self.assertEqual(report["NearDuplicatePairs"], [])
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                gate.main(["--candidates", "not-read.csv", "--review-near-duplicates"])
        self.assertEqual(raised.exception.code, 2)

    def test_near_duplicate_jaccard_threshold_is_inclusive(self):
        from BertScript.article_text_review import near_duplicate_pairs
        fingerprints = {"a": "1", "b": "2", "c": "3"}
        shingles = {"a": {"a", "b", "c", "d", "e"},
                    "b": {"a", "b", "c", "d"},
                    "c": {"a", "b", "c"}}
        self.assertEqual(near_duplicate_pairs(fingerprints, shingles), [{
            "Sources": ["a", "b"], "Jaccard": 0.8,
            "SharedShingles": 4, "UnionShingles": 5,
        }])

    def test_candidate_relevance_groups_are_bound_to_own_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, [
                "國際能源政策。太陽能發電與電網儲能。" * 10,
                "太陽能發電與其他產業。未涉及電力儲存。" * 10,
                "儲能。電網。其他來源不應補足第二篇的命中。" * 10,
            ])
            candidates = {
                "Energy": row("能源", notes=note(source="doc-0")),
                "Storage": row("儲能", notes=note(source="doc-1")),
            }
            rules = root / "rules.json"
            spec = {"schema_version": 1, "rules": {
                label: {"groups": [["太陽能", "Solar"], ["儲能", "battery storage"]],
                        "min_groups": 2} for label in candidates
            }}
            rules.write_text(json.dumps(spec), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            report = gate.audit_local_article_evidence(
                candidates, manifest, review_text=True, relevance_rules_path=rules)
            self.assertEqual(report["RelevanceReviewStatus"], "REVIEW_REQUIRED")
            self.assertEqual(report["RelevanceCandidatesNeedingReview"], ["Storage"])
            self.assertEqual(report["RelevanceCandidatesChecked"], 2)
            a, b = report["RelevanceCandidateResults"]
            self.assertEqual((a["ClassLabel"], a["MatchedGroups"]), ("Energy", 2))
            self.assertEqual((b["ClassLabel"], b["MatchedGroups"]), ("Storage", 1))
            self.assertFalse(report["EvidenceSemanticRelevanceVerified"])
            self.assertFalse(report["Approved"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_relevance_rules_reject_uncovered_labels_and_repeated_aliases(self):
        from BertScript.article_relevance_review import validate_relevance_rules
        good = {"groups": [["Solar", "太陽能"], ["電網"]], "min_groups": 2}
        for rules in ({}, {"Other": good},
                      {"New": {"groups": [["Solar"], [" SOLAR "]], "min_groups": 2}},
                      {"New": {"groups": [["a"]], "min_groups": True}},
                      {"New": {"groups": [[""]], "min_groups": 1}}):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                validate_relevance_rules({"schema_version": 1, "rules": rules}, {"New"})

    def test_relevance_literal_aliases_casefold_and_short_article_review(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, ["SOLAR Café a+b"])
            rules = root / "rules.json"
            rules.write_text(json.dumps({"schema_version": 1, "rules": {
                "New": {"groups": [["solar", "光電"], ["Cafe\u0301"], ["a+b"]],
                        "min_groups": 3},
            }}), encoding="utf-8")
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            report = gate.audit_local_article_evidence(
                candidates, manifest, review_text=True, relevance_rules_path=rules)
            result = report["RelevanceCandidateResults"][0]
            self.assertEqual(result["MatchedGroups"], 3)
            self.assertTrue(result["ShortArticle"])
            self.assertEqual(report["RelevanceCandidatesNeedingReview"], ["New"])
            self.assertEqual(report["RelevanceReviewStatus"], "REVIEW_REQUIRED")

    def test_relevance_rules_budget_and_duplicate_json_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, ["太陽能發電" * 30])
            rules = root / "rules.json"
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            rules.write_text('{"schema_version":1,"rules":{},"rules":{}}', encoding="utf-8")
            with self.assertRaisesRegex(metadata.MetadataError, "duplicate JSON key"):
                gate.audit_local_article_evidence(
                    candidates, manifest, review_text=True, relevance_rules_path=rules)
            rules.write_text(json.dumps({"schema_version": 1, "rules": {
                "New": {"groups": [["太陽能"]], "min_groups": 1},
            }}), encoding="utf-8")
            with mock.patch.object(gate, "MAX_EVALUATED_CHARS", 10):
                with self.assertRaisesRegex(metadata.MetadataError, "evaluated character budget"):
                    gate.audit_local_article_evidence(
                        candidates, manifest, review_text=True, relevance_rules_path=rules)
            with self.assertRaisesRegex(metadata.MetadataError, "requires text review"):
                gate.audit_local_article_evidence(
                    candidates, manifest, relevance_rules_path=rules)

    def test_relevance_cli_requires_text_review(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                gate.main(["--candidates", "not-read.csv", "--relevance-rules", "rules.json"])
        self.assertEqual(raised.exception.code, 2)

    def _semantic_response(self, request, verdict="RELEVANT"):
        quote = request.normalized_text[:6]
        return {
            "request_id": request.request_id, "model": "fixture-model",
            "verdict": verdict, "rationale": "fixture advisory",
            "spans": [{"start": 0, "end": len(quote), "text": quote}],
        }

    def test_semantic_provider_targets_only_lexical_review_candidates(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, [
                "太陽能發電與電網儲能政策。" * 12,
                "太陽能與其他產業。" * 15,
                "另一篇無關證據。" * 15,
            ])
            rules = root / "rules.json"
            candidates = {
                "Good": row("能源", notes=note(source="doc-0")),
                "Review": row("儲能", "候選定義", note(source="doc-1")),
            }
            rules.write_text(json.dumps({"schema_version": 1, "rules": {
                label: {"groups": [["太陽能"], ["儲能"]], "min_groups": 2}
                for label in candidates
            }}), encoding="utf-8")
            seen = []
            def reviewer(request):
                seen.append(request)
                return self._semantic_response(request)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            report = gate.audit_local_article_evidence(
                candidates, manifest, review_text=True, relevance_rules_path=rules,
                semantic_reviewer=reviewer, semantic_review_mode="lexical_review_required")
            self.assertEqual(len(seen), 1)
            request = seen[0]
            self.assertEqual((request.class_label, request.source), ("Review", "doc-1"))
            self.assertEqual(request.explanation, "候選定義")
            self.assertEqual(request.article_sha256,
                             hashlib.sha256((root / "near1.txt").read_bytes()).hexdigest())
            self.assertNotIn("儲能", request.normalized_text)
            self.assertEqual(report["SemanticReviewNotSelected"], ["Good"])
            self.assertEqual(report["SemanticReviewAttempted"], 1)
            result = report["SemanticReviewResults"][0]
            self.assertTrue(result["EvidenceSpanTextMatches"])
            self.assertTrue(result["HumanReviewRequired"])
            self.assertEqual(result["Verdict"], "RELEVANT")
            self.assertFalse(report["EvidenceSemanticRelevanceVerified"])
            self.assertFalse(report["Approved"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_semantic_provider_never_called_before_full_evidence_preflight(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, ["正文甲", "正文乙"])
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            reviewer = mock.Mock()
            (root / "near1.txt").write_text("已遭竄改", encoding="utf-8")
            with self.assertRaisesRegex(metadata.MetadataError, "sha256 mismatch"):
                gate.audit_local_article_evidence(
                    candidates, manifest, review_text=True, semantic_reviewer=reviewer)
            reviewer.assert_not_called()
            manifest = self._write_near_review_manifest(root, ["正文甲", "正文乙"])
            candidates["Missing"] = row("缺少", notes=note(source="absent"))
            with self.assertRaisesRegex(metadata.MetadataError, "not found"):
                gate.audit_local_article_evidence(
                    candidates, manifest, review_text=True, semantic_reviewer=reviewer)
            reviewer.assert_not_called()

    def test_semantic_provider_invalid_responses_and_failure_are_advisory(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, ["文章正文與能源證據"])
            candidates = {"New": row("新增", notes=note(source="doc-0"))}
            for change in (
                {"request_id": "wrong"}, {"verdict": "APPROVED"},
                {"spans": [{"start": 0, "end": 3, "text": "偽造字"}]},
                {"spans": []}, {"approved": True},
            ):
                with self.subTest(change=change):
                    report = gate.audit_local_article_evidence(
                        candidates, manifest, review_text=True,
                        semantic_reviewer=lambda req: {**self._semantic_response(req), **change})
                    result = report["SemanticReviewResults"][0]
                    self.assertEqual(result["ReviewStatus"], "INVALID_RESPONSE")
                    self.assertIsNone(result["Verdict"])
                    self.assertTrue(result["HumanReviewRequired"])
            reviewer = mock.Mock(side_effect=TimeoutError("private provider detail"))
            report = gate.audit_local_article_evidence(
                candidates, manifest, review_text=True, semantic_reviewer=reviewer)
            reviewer.assert_called_once()
            self.assertEqual(report["SemanticReviewResults"][0]["ReviewStatus"], "PROVIDER_ERROR")
            self.assertNotIn("private provider detail", json.dumps(report))
            uncertain = gate.audit_local_article_evidence(
                candidates, manifest, review_text=True,
                semantic_reviewer=lambda req: {
                    **self._semantic_response(req, "UNCERTAIN"), "spans": []})
            self.assertEqual(uncertain["SemanticReviewResults"][0]["ReviewStatus"], "MODEL_UNCERTAIN")
            self.assertFalse(uncertain["Approved"])

    def test_semantic_review_budgets_and_explicit_modes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._write_near_review_manifest(root, ["文章一", "文章二"])
            candidates = {
                "A": row("甲", notes=note(source="doc-0")),
                "B": row("乙", notes=note(source="doc-1")),
            }
            reviewer = mock.Mock()
            for name, value, message in [
                ("MAX_SEMANTIC_REQUESTS", 1, "request count budget"),
                ("MAX_SEMANTIC_TOTAL_CHARS", 4, "total character budget"),
            ]:
                with self.subTest(name=name), mock.patch.object(gate, name, value):
                    with self.assertRaisesRegex(metadata.MetadataError, message):
                        gate.audit_local_article_evidence(
                            candidates, manifest, review_text=True, semantic_reviewer=reviewer)
                reviewer.assert_not_called()
            with self.assertRaisesRegex(metadata.MetadataError, "requires relevance rules"):
                gate.audit_local_article_evidence(
                    candidates, manifest, review_text=True, semantic_reviewer=reviewer,
                    semantic_review_mode="lexical_review_required")
            with self.assertRaisesRegex(metadata.MetadataError, "requires an explicit callable"):
                gate.audit_local_article_evidence(
                    candidates, manifest, semantic_reviewer=reviewer)
            self.assertNotIn("SemanticReviewResults",
                             gate.audit_local_article_evidence(candidates, manifest, review_text=True))
            reviewer.assert_not_called()

    def test_semantic_request_identity_changes_with_candidate_or_article(self):
        from BertScript.article_semantic_review import build_semantic_request
        first = row("甲", "原定義", note(source="source"))
        original = build_semantic_request("New", first, "source", "a" * 64, "文章")
        for candidate, digest, body in (
            ({**first, "Explanation": "新定義"}, "a" * 64, "文章"),
            (first, "b" * 64, "文章"),
            (first, "a" * 64, "不同正文"),
        ):
            self.assertNotEqual(original.request_id, build_semantic_request(
                "New", candidate, "source", digest, body).request_id)
        self.assertEqual(original.request_id, build_semantic_request(
            "New", first, "source", "a" * 64, "文章").request_id)

    def test_graph_cli_requires_pair_of_graph_arguments(self):
        with TemporaryDirectory() as directory:
            for flag in ("--base-tree", "--edges"):
                with self.subTest(flag=flag):
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as raised:
                            gate.main(["--candidates", str(Path(directory) / "not-read.csv"),
                                       flag, "one.csv"])
                    self.assertEqual(raised.exception.code, 2)

    def test_graph_cli_reports_aligned_labels_without_file_writes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.csv"
            candidate = root / "candidate.csv"
            base_tree = root / "tree.csv"
            edges = root / "edges.csv"
            base.write_text(metadata.table_to_csv(self.base), encoding="utf-8")
            candidate.write_text(metadata.table_to_csv({
                "New": row("新增", notes=note())
            }), encoding="utf-8")
            self.write_edges(base_tree, [("Root", "Existing")])
            self.write_edges(edges, [("Root", "New")])
            paths = (base, candidate, base_tree, edges)
            original = tuple(p.read_bytes() for p in paths)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = gate.main([
                    "--base", str(base), "--candidates", str(candidate),
                    "--base-tree", str(base_tree), "--edges", str(edges),
                    "--json",
                ])
            self.assertEqual(result, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["GraphNodeAlignment"], "matched")
            self.assertFalse(report["GraphRelationshipsApproved"])
            self.assertFalse(report["Approved"])
            self.assertEqual(tuple(p.read_bytes() for p in paths), original)
            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             sorted(p.name for p in paths))


if __name__ == "__main__":
    unittest.main()
