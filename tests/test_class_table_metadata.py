"""Stdlib-only ClassTable CSV compatibility and TopicTree merge tests."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from BertScript import class_table_metadata as m
from BertScript import migrate_class_table as legacy
from BertScript.ClassTable import ClassTable


class ClassTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def csv_file(self, name, values):
        p = self.root / name
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(m.HEADERS)
            w.writerows([list(row) + ([""] if len(row) == 3 else [])
                         for row in values])
        return p

    def graph(self, name, edges):
        p = self.root / name
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["#母類別", "子類別", "日期", "關係", "備註"])
            for a, b in edges:
                w.writerow([a, b, "20261028", "contains", ""])
        return p

    def test_real_api_and_unicode_roundtrip(self):
        actual = m.load_class_table()
        self.assertEqual(actual, ClassTable)
        self.assertEqual(len(actual), 1994)
        self.assertEqual(actual["Academia"], {"CT": "學術", "Explanation": "學術界、學術研究", "Notes": ""})
        self.assertNotIn("Explaination", actual["Academia"])
        self.assertEqual(actual["CN Government Real Estate Policy"],
                         {"CT": "中國政府房地產政策", "Explanation": "", "Notes": ""})
        self.assertEqual(actual["CN Real Estate Industry"],
                         {"CT": "中國房地產業", "Explanation":
                          "中國房地產、房價、建築業，產業資訊；另房地產物件資訊屬Real Estate Object。",
                          "Notes": ""})
        self.assertNotIn("Government Real Estate Policy", actual)
        self.assertNotIn("Real Estate Industry", actual)
        m.check_round_trip(actual)
        # The committed file itself must stay in canonical ClassLabel order.
        self.assertEqual(m.DEFAULT_CSV.read_text(encoding="utf-8-sig"),
                         m.table_to_csv(actual))

    def test_unicode_quoting_and_optional_explanation(self):
        p = self.csv_file("chinese.csv", [
            ["Test", "中文、資料", '逗號,引號"和\n換行'],
            ["NoExplain", "沒有說明", ""],
        ])
        table = m.load_class_table(p)
        self.assertEqual(table["Test"]["Explanation"], '逗號,引號"和\n換行')
        self.assertEqual(table["NoExplain"]["Explanation"], "")
        self.assertEqual(table["NoExplain"]["Notes"], "")
        m.check_round_trip(table)

    def test_ai_notes_roundtrip_and_preserve_original_explanation(self):
        note = ('AI新增｜日期=2026-10-31｜來源=https://example.org/doc?a=1,b=2'
                '｜理由=從新聞抽取的「測試, 新類別」\\n仍待核對'
                '｜狀態=待人工審核')
        p = self.csv_file("annotated.csv", [
            ["AI Label", "測試標籤", "既有說明", note],
            ["Existing", "現有類別", "保留原本資料", "人工備註：原有類別"],
        ])
        table = m.load_class_table(p)
        self.assertEqual(table["AI Label"]["Notes"], note)
        self.assertEqual(table["AI Label"]["Explanation"], "既有說明")
        self.assertEqual(table["Existing"]["Notes"], "人工備註：原有類別")
        m.check_round_trip(table)
        self.assertEqual(m.rows_to_table(m.read_rows(p)), table)
        self.assertEqual(
            m.rows_to_table(list(csv.DictReader(m.table_to_csv(table).splitlines(keepends=True)))),
            table,
        )

    def test_notes_are_optional_but_schema_is_required(self):
        result = {"One": {"CT": "一", "Explanation": "說明"}}
        self.assertIn("One,一,說明,\\n", m.table_to_csv(result))
        self.assertEqual(
            m.rows_to_table(list(csv.DictReader(m.table_to_csv(result).splitlines(keepends=True))))["One"]["Notes"],
            "",
        )
        p = self.root / "old.csv"
        p.write_text("ClassLabel,CT,Explanation\\nOne,一,說明\\n", encoding="utf-8")
        with self.assertRaisesRegex(m.MetadataError, "expected CSV columns"):
            m.load_class_table(p)

    def test_duplicate_label_rejected(self):
        p = self.csv_file("dup.csv", [["A", "甲", ""], ["A", "乙", ""]])
        with self.assertRaisesRegex(m.MetadataError, "duplicate ClassLabel"):
            m.load_class_table(p)

    def test_invalid_rows_rejected(self):
        for i, rows in enumerate(([["A", "", ""]], [["", "中", ""]],
                                  [[" A ", "中", ""]])):
            with self.subTest(i=i):
                with self.assertRaises(m.MetadataError):
                    m.load_class_table(self.csv_file(f"{i}.csv", rows))

    def test_wrong_schema_and_unterminated_quote_rejected(self):
        p = self.root / "bad.csv"
        p.write_text("ClassLabel,CT,Explaination\nA,中,\n", encoding="utf-8")
        with self.assertRaises(m.MetadataError):
            m.load_class_table(p)
        p.write_text('ClassLabel,CT,Explanation,Notes\n"oops,中,,\n', encoding="utf-8")
        with self.assertRaises(m.MetadataError):
            m.load_class_table(p)

    def test_sorted_csv(self):
        data = {"Z": {"CT": "末"}, "A": {"CT": "首"}}
        self.assertEqual(m.table_to_csv(data).splitlines()[1:], ["A,首,,", "Z,末,,"])
        m.check_round_trip(data)

    def test_graph_endpoint_union_and_duplicate_ct_warning(self):
        tree = self.graph("tree.csv", [("A", "B"), ("B", "C")])
        table = {"B": {"CT": "同"}, "Orphan": {"CT": "同"}}
        report = m.audit(table, tree)
        self.assertEqual(report["TopicTreeNodes"], 3)
        self.assertEqual(report["MissingInClassTable"], ["A", "C"])
        self.assertEqual(report["OrphanInClassTable"], ["Orphan"])
        self.assertEqual(report["DuplicateCT"]["同"], ["B", "Orphan"])

    def test_merge_checks_exact_candidate_set(self):
        before = self.graph("before.csv", [("Root", "Old")])
        edges = self.graph("edges.csv", [("Root", "NewA"), ("NewA", "NewB")])
        candidates = self.csv_file("candidates.csv", [
            ["NewB", "乙", ""], ["NewA", "甲", "說明"]
        ])
        merged, nodes = m.merge_candidates({"Root": {"CT": "根"}}, before, edges, candidates)
        self.assertEqual(nodes, {"NewA", "NewB"})
        self.assertEqual(set(merged), {"Root", "NewA", "NewB"})
        bad = self.csv_file("missing.csv", [["NewA", "甲", ""]])
        with self.assertRaisesRegex(m.MetadataError, "candidate mismatch"):
            m.merge_candidates({}, before, edges, bad)
        extra = self.csv_file("extra.csv", [
            ["NewA", "甲", ""], ["NewB", "乙", ""], ["Old", "舊", ""]
        ])
        with self.assertRaises(m.MetadataError):
            m.merge_candidates({}, before, edges, extra)
        with self.assertRaisesRegex(m.MetadataError, "already in ClassTable"):
            m.merge_candidates({"NewB": {"CT": "舊"}}, before, edges, candidates)

    def test_import_does_not_change_cwd_and_uses_adjacent_resource(self):
        cwd = Path.cwd()
        self.assertEqual(m.DEFAULT_CSV, Path(m.__file__).with_name("ClassTable.csv"))
        self.assertEqual(m.load_class_table(), ClassTable)
        self.assertEqual(Path.cwd(), cwd)

    def test_known_four_corrections(self):
        self.assertEqual(ClassTable["Commerce"], {"CT": "商務", "Explanation": "", "Notes": ""})
        self.assertEqual(ClassTable["2016 Nice Truck Attack"]["CT"], "2016尼斯卡車襲擊事件")
        self.assertIn("尼斯襲擊", ClassTable["2016 Nice Truck Attack"]["Explanation"])
        self.assertEqual(ClassTable["3C Product News-Asus Product News"]["CT"], "ASUS產品新聞")
        self.assertEqual(ClassTable["3C Product News-Samsung Product News"]["CT"], "Samsung產品新聞")

    def test_legacy_migration_and_duplicate_last_key(self):
        path = self.root / "legacy.py"
        path.write_text(
            'ClassTable = {"Commerce":{"CT":"商務","Explaination":"2016年尼斯襲擊事件"},'
            '"2016 Nice Truck Attack":{"CT":"學術","Explaination":"學術界、學術研究"},'
            '"3C Product News-Asus Product News":{"CT":"Apple產品新聞"},'
            '"3C Product News-Samsung Product News":{"CT":"Apple產品新聞"},'
            '"Government Real Estate Policy":{"CT":"政府房地產政策"},'
            '"Real Estate Industry":{"CT":"中國房地產業","Explaination":'
            '"中國房地產、房價、建築業，產業資訊；另房地產物件資訊屬Real Estate Object。"},'
            '"Example":{"CT":"舊"},"Example":{"CT":"新"}}\n', encoding="utf-8"
        )
        data, duplicates = legacy.read_legacy(path)
        self.assertEqual(duplicates, ["Example"])
        self.assertEqual(data["Example"]["CT"], "新")
        transformed = {k: dict(v) for k, v in data.items()}
        legacy.correct_known(transformed)
        legacy.verify(data, transformed)
        self.assertNotIn("Government Real Estate Policy", transformed)
        self.assertNotIn("Real Estate Industry", transformed)
        # Notes is not part of the historic source contract; annotations are
        # retained and do not fail the CT/Explanation migration comparison.
        transformed["CN Government Real Estate Policy"]["Notes"] = (
            "AI補充｜日期=2026-10-31｜來源=文字樣本｜理由=補齊描述｜狀態=待人工審核"
        )
        legacy.verify(data, transformed)
        self.assertEqual(transformed["CN Government Real Estate Policy"]["CT"],
                         "中國政府房地產政策")
        self.assertEqual(transformed["CN Real Estate Industry"]["Explanation"],
                         data["Real Estate Industry"]["Explanation"])
        wrong = {k: dict(v) for k, v in data.items()}
        wrong["Real Estate Industry"]["CT"] = "錯誤原文"
        with self.assertRaisesRegex(m.MetadataError, "refusing rename"):
            legacy.correct_known(wrong)

    def test_retired_spelling_fails_active_consumer_guard(self):
        current = self.root / "current.py"
        current.write_text("name = 'Explanation'\n", encoding="utf-8")
        m.check_active_consumers((current,))
        current.write_text("name = 'Explaination'\n", encoding="utf-8")
        with self.assertRaisesRegex(m.MetadataError, "retired metadata key"):
            m.check_active_consumers((current,))

    def test_dash_ui_field_and_column_format_are_consistent(self):
        repo = Path(__file__).resolve().parents[1]
        for name in ("Test_result_Vis.py", "Test_result_Vis_layout.py",
                     "VisParameters_Format.py"):
            source = (repo / "BertScript" / name).read_text(encoding="utf-8")
            self.assertNotIn("Explain" + "ation", source)
        m.check_active_consumers()

    def test_actual_tree_audit_reports_not_auto_fills(self):
        report = m.audit(ClassTable, m.DEFAULT_TREE)
        self.assertEqual(report["ClassTableRows"], 1994)
        # The active TopicTree grows independently of ClassTable metadata.
        # Guard against accidental large graph truncation, not legitimate new nodes.
        self.assertGreaterEqual(report["TopicTreeNodes"], 2670)
        self.assertTrue(report["MissingInClassTable"])
        # Both labels already exist in the current authoritative TopicTree.
        for label in ("CN Government Real Estate Policy", "CN Real Estate Industry"):
            self.assertIn(label, m.topic_nodes(m.DEFAULT_TREE))
            self.assertNotIn(label, report["MissingInClassTable"])
        for retired in ("Government Real Estate Policy", "Real Estate Industry"):
            self.assertNotIn(retired, report["OrphanInClassTable"])


if __name__ == "__main__":
    unittest.main()
