"""History preview must be read-only and safe for interrupted Stage 4 jobs."""
from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from BertScript import stage4_history_data as history

ROOT = Path(__file__).resolve().parents[1]


class Stage4HistoryDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name, "WorkPool")
        self.root.mkdir()
        self.finished = self.workspace("20261102233330", "rdy_for_Spike")
        self.interrupted = self.workspace("20261102234138", "is_running_TestResultVis")
        self.write_database(self.finished)
        self.write_database(self.interrupted)
        self.snapshot = {
            p: (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes())
            for folder in (self.finished, self.interrupted)
            for p in folder.iterdir()
        }

    def workspace(self, date, status):
        item = self.root / ("dataset_" + date + "_PytorchXLM_pt8059_" + status)
        item.mkdir()
        return item

    def write_database(self, folder):
        for name in history.DATABASES:
            with sqlite3.connect(folder / name) as db:
                db.execute('CREATE TABLE "sampleSrc" ("index" INTEGER, "text" TEXT, "Label" TEXT)')
                db.executemany(
                    'INSERT INTO "sampleSrc" VALUES (?, ?, ?)',
                    [(i, "測試文本" + str(i), "TW Affairs") for i in range(60)],
                )
                db.execute('CREATE TABLE "odd""name" ("payload" TEXT)')
                db.execute('INSERT INTO "odd""name" VALUES (?)', ("a" * 800,))
                db.commit()

    def assert_unchanged(self):
        for path, initial in self.snapshot.items():
            self.assertTrue(path.is_file(), str(path))
            self.assertEqual(
                (path.stat().st_size, path.stat().st_mtime_ns, path.read_bytes()),
                initial,
            )

    def test_discovers_complete_vs_interrupted_and_cannot_infer_success(self):
        values = history.list_workspaces(self.root)
        self.assertEqual(len(values), 2)
        self.assertEqual(values[0].name, self.interrupted.name)
        self.assertFalse(values[0].complete)
        self.assertTrue(values[1].complete)
        self.assertEqual(values[1].missing, ())

    def test_paginated_immutable_read_and_column_truncation(self):
        columns = history.list_tables(
            self.root, self.finished.name, history.DATABASES[0]
        )
        self.assertEqual(columns, ('odd"name', "sampleSrc"))
        first = history.read_page(
            self.root, self.finished.name, history.DATABASES[0], "sampleSrc", 1
        )
        self.assertEqual(len(first["rows"]), 50)
        self.assertTrue(first["has_next"])
        self.assertEqual(first["rows"][0]["index"], "0")
        second = history.read_page(
            self.root, self.finished.name, history.DATABASES[0], "sampleSrc", 2
        )
        self.assertEqual(len(second["rows"]), 10)
        self.assertFalse(second["has_next"])
        weird = history.read_page(
            self.root, self.finished.name, history.DATABASES[0], 'odd"name', 1
        )
        self.assertEqual(len(weird["rows"][0]["payload"]), history.MAX_TEXT)
        self.assert_unchanged()
        for folder in (self.finished, self.interrupted):
            self.assertFalse(any(
                (folder / (name + "-shm")).exists() for name in history.DATABASES
            ))

    def test_histogram_reads_only_saved_sqlite_and_keeps_provenance(self):
        database = history.DATABASES[0]
        columns = history.list_columns(
            self.root, self.finished.name, database, "sampleSrc"
        )
        self.assertEqual(columns, ("index", "text", "Label"))
        sample = history.read_distribution(
            self.root, self.finished.name, database, "sampleSrc", "Label"
        )
        self.assertEqual(sample["sampled_rows"], 60)
        self.assertFalse(sample["has_more_rows"])
        self.assertEqual(sample["distinct_prefixes"], 1)
        self.assertEqual(sample["truncated_values"], 0)
        self.assertEqual(sample["categories"],
                         [{"label": "TW Affairs", "count": 60}])
        odd = history.read_distribution(
            self.root, self.finished.name, database, 'odd"name', "payload"
        )
        self.assertEqual(len(odd["categories"][0]["label"]),
                         history.DISTRIBUTION_LABEL_CHARS)
        self.assert_unchanged()

    def test_long_value_prefix_collision_is_explicit_not_claimed_as_distinct(self):
        # Distinct full values sharing their first 120 characters must never
        # be presented as an exact ClassLabel/value distinct-count.
        prefix = "a" * history.DISTRIBUTION_LABEL_CHARS
        with sqlite3.connect(self.finished / history.DATABASES[0]) as db:
            db.execute('CREATE TABLE "long labels" ("label" TEXT)')
            db.executemany(
                'INSERT INTO "long labels" VALUES (?)',
                [(prefix + "X",), (prefix + "Y",)],
            )
            db.commit()
        p = self.finished / history.DATABASES[0]
        initial = (p.read_bytes(), p.stat().st_mtime_ns)
        payload = history.read_distribution(
            self.root, self.finished.name, history.DATABASES[0],
            "long labels", "label",
        )
        self.assertEqual(payload["categories"], [
            {"label": prefix, "count": 2},
        ])
        self.assertEqual(payload["distinct_prefixes"], 1)
        self.assertEqual(payload["truncated_values"], 2)
        self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), initial)
        # This test intentionally modifies a new table, so not using the
        # fixture's initial snapshot; only the read operation is immutable.

    def test_distribution_bounds_large_database_and_reports_sampling_not_full_population(self):
        workspace = self.workspace("20261101120000", "rdy_for_Spike")
        self.write_database(workspace)
        path = workspace / history.DATABASES[0]
        with sqlite3.connect(path) as connection:
            connection.executemany(
                'INSERT INTO "sampleSrc" ("index", "text", "Label") '
                'VALUES (?, ?, ?)',
                ((i + 60, "body", "Topic" + str(i % 30))
                 for i in range(history.DISTRIBUTION_SAMPLE_ROWS + 50)),
            )
            connection.commit()
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        payload = history.read_distribution(
            self.root, workspace.name, history.DATABASES[0],
            "sampleSrc", "Label",
        )
        self.assertEqual(payload["sampled_rows"],
                         history.DISTRIBUTION_SAMPLE_ROWS)
        self.assertTrue(payload["has_more_rows"])
        self.assertLessEqual(len(payload["categories"]),
                             history.DISTRIBUTION_TOP_GROUPS)
        self.assertGreater(payload["distinct_prefixes"],
                           payload["displayed_groups"])
        self.assertEqual(
            sum(entry["count"] for entry in payload["categories"]),
            sum(sorted([60] + [
                sum(1 for i in range(history.DISTRIBUTION_SAMPLE_ROWS - 60)
                    if i % 30 == x)
                for x in range(30)
            ], reverse=True)[:history.DISTRIBUTION_TOP_GROUPS]),
        )
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        for suffix in ("-wal", "-shm", "-journal"):
            self.assertFalse(Path(str(path) + suffix).exists())

    def test_distribution_rejects_unknown_identifiers_and_unacknowledged_running(self):
        database = history.DATABASES[1]
        for column in ('Label";DROP TABLE sampleSrc;--', None, "", "fake"):
            with self.subTest(column=column), self.assertRaises(
                    history.HistoryPreviewError):
                history.read_distribution(
                    self.root, self.finished.name, database, "sampleSrc", column
                )
        with self.assertRaises(history.HistoryPreviewError):
            history.read_distribution(
                self.root, self.finished.name, database, "sampleSrc;DROP TABLE x",
                "Label",
            )
        with self.assertRaisesRegex(history.HistoryPreviewError, "confirm"):
            history.read_distribution(
                self.root, self.interrupted.name, database, "sampleSrc", "Label"
            )
        self.assertEqual(
            history.read_distribution(
                self.root, self.interrupted.name, database, "sampleSrc", "Label",
                confirm_running=True,
            )["sampled_rows"], 60,
        )
        self.assert_unchanged()

    def test_sqlite_uri_encodes_unc_as_path_with_empty_authority(self):
        from urllib.parse import urlsplit
        fake = mock.Mock()
        fake.resolve.return_value.as_posix.return_value = (
            "//file-server/share name/資料/results.sql3"
        )
        uri = history._immutable_sqlite_uri(fake)
        parsed = urlsplit(uri)
        self.assertEqual(parsed.scheme, "file")
        self.assertEqual(parsed.netloc, "")
        self.assertTrue(parsed.path.startswith("//file-server/share%20name/"))
        self.assertIn("%E8%B3%87%E6%96%99", parsed.path)
        self.assertEqual(parsed.query, "mode=ro&immutable=1")
        # Local paths retain their correct, authority-less SQLite URI format.
        local = history._immutable_sqlite_uri(self.finished / history.DATABASES[0])
        self.assertEqual(urlsplit(local).netloc, "")

    def test_running_requires_explicit_acknowledgment(self):
        with self.assertRaisesRegex(history.HistoryPreviewError, "confirm"):
            history.list_tables(self.root, self.interrupted.name, history.DATABASES[1])
        self.assertIn(
            "sampleSrc",
            history.list_tables(
                self.root, self.interrupted.name, history.DATABASES[1],
                confirm_running=True,
            ),
        )
        self.assertFalse(history.select_workspace(
            self.root, self.interrupted.name
        ).complete)
        self.assert_unchanged()

    def test_missing_sidecar_and_invalid_names_fail_closed(self):
        missing = self.workspace("20261028004415", "is_running_TestResultVis")
        for suffix in ("../other", "DFPreambleCols_df_ALL.sql3?mode=rw"):
            with self.subTest(suffix=suffix), self.assertRaises(history.HistoryPreviewError):
                history.database_path(self.root, self.finished.name, suffix)
        with self.assertRaises(history.HistoryPreviewError):
            history.select_workspace(self.root, "../" + self.finished.name)
        with self.assertRaises(history.HistoryPreviewError):
            history.list_tables(self.root, missing.name, history.DATABASES[0],
                                confirm_running=True)
        with self.assertRaises(history.HistoryPreviewError):
            history.read_page(self.root, self.finished.name,
                              history.DATABASES[0], 'sampleSrc; DROP TABLE sampleSrc')
        for page in (0, -2, 20001, "abc"):
            with self.subTest(page=page), self.assertRaises(history.HistoryPreviewError):
                history.read_page(self.root, self.finished.name, history.DATABASES[0],
                                  "sampleSrc", page)
        db = self.finished / history.DATABASES[0]
        for suffix in ("-wal", "-journal", "-shm"):
            sidecar = Path(str(db) + suffix)
            sidecar.touch()
            try:
                with self.assertRaisesRegex(history.HistoryPreviewError, "sidecar"):
                    history.list_tables(self.root, self.finished.name, history.DATABASES[0])
            finally:
                sidecar.unlink()
        self.assert_unchanged()

    def test_symlink_workspace_and_db_cannot_escape_selected_root(self):
        fake = self.root / "dataset_20261101010101_PytorchXLM_pt8059_rdy_for_Spike"
        try:
            fake.symlink_to(self.finished, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not authorized")
        self.assertNotIn(fake.name, [w.name for w in history.list_workspaces(self.root)])
        with self.assertRaises(history.HistoryPreviewError):
            history.select_workspace(self.root, fake.name)
        fake.unlink()

    def test_only_persisted_sqlite_is_accepted(self):
        bogus = self.workspace("20261101020202", "rdy_for_Spike")
        for name in history.DATABASES:
            (bogus / name).write_text("not sqlite", encoding="utf-8")
        with self.assertRaisesRegex(history.HistoryPreviewError, "SQLite"):
            history.list_tables(self.root, bogus.name, history.DATABASES[0])


class Stage4HistoryLauncherTests(unittest.TestCase):
    def test_fast_dispatch_is_before_large_analytics_import(self):
        source = (ROOT / "BertScript" / "Test_result_Vis.py").read_text(
            encoding="utf-8"
        )
        root = ast.parse(source)
        early = next(
            node for node in root.body
            if isinstance(node, ast.If) and "history-preview" in ast.unparse(node.test)
        )
        numpy = next(
            node for node in root.body
            if isinstance(node, ast.Import)
            and any(alias.name == "numpy" for alias in node.names)
        )
        self.assertLess(early.lineno, numpy.lineno)
        self.assertIn("history_preview_main(sys.argv[1:])",
                      ast.get_source_segment(source, early))

    def test_history_help_works_from_external_working_directory(self):
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [sys.executable, str(ROOT / "BertScript/Test_result_Vis.py"),
                 "--history-preview", "--help"],
                cwd=cwd, capture_output=True, text=True, timeout=25,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--workpool", result.stdout)
        self.assertIn("--history-preview", result.stdout)

    def test_interrupt_consent_requires_new_acknowledgment_per_selection(self):
        from BertScript.stage4_history_preview import _consent_transition
        a, b = "dataset_A", "dataset_B"
        fresh, values = _consent_transition(a, [], None, None)
        self.assertFalse(fresh["confirmed"])
        granted, values = _consent_transition(
            a, [a], fresh, "HistoryConfirmRunning",
        )
        self.assertTrue(granted["confirmed"])
        self.assertEqual(values, [a])
        switched, values = _consent_transition(
            b, [a], granted, "HistoryWorkspace",
        )
        self.assertEqual(switched, {"workspace": b, "confirmed": False})
        self.assertEqual(values, [])
        # Stale confirmation for A cannot grant permission to B even if
        # the browser emits the checklist input before the selection reset.
        stale, values = _consent_transition(
            b, [a], switched, "HistoryConfirmRunning",
        )
        self.assertFalse(stale["confirmed"])
        accepted, values = _consent_transition(
            b, [b], stale, "HistoryConfirmRunning",
        )
        self.assertTrue(accepted["confirmed"])
        back, values = _consent_transition(a, [b], accepted, "HistoryWorkspace")
        self.assertFalse(back["confirmed"])
        self.assertEqual(values, [])

    def test_launcher_rejects_invalid_port_and_never_advances_workpool(self):
        from BertScript import stage4_history_preview as viewer
        for argv in (["-p", "8060"], ["--history-preview", "-p", "0"],
                     ["--history-preview", "-p", "65536"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                viewer.parse_args(argv)
        fake = mock.Mock()
        fake.run = mock.Mock()
        with mock.patch.object(viewer, "build_app", return_value=fake), \
             mock.patch("os.rename", side_effect=AssertionError("rename forbidden")), \
             mock.patch("os.replace", side_effect=AssertionError("replace forbidden")):
            result = viewer.main(["--history-preview", "--workpool", "WorkPool",
                                  "-p", "8060"])
        self.assertEqual(result, 0)
        fake.run.assert_called_once_with(
            host="127.0.0.1", port=8060, debug=False, use_reloader=False
        )

    def test_analysis_column_preference_and_readonly_chart_contract(self):
        from BertScript.stage4_history_preview import (
            _preferred_distribution_column, _distribution_chart,
        )
        self.assertEqual(
            _preferred_distribution_column(("index", "text", "ClassLabel")),
            "ClassLabel",
        )
        self.assertEqual(_preferred_distribution_column(()), None)
        self.assertEqual(_preferred_distribution_column(("index", "url", "Score")),
                         "Score")
        chart = _distribution_chart({"categories": [
            {"label": "A", "count": 2},
            {"label": "B", "count": 7},
        ]})
        self.assertEqual(chart["data"][0]["type"], "bar")
        self.assertEqual(chart["data"][0]["x"], [7, 2])
        self.assertEqual(chart["data"][0]["y"], ["B", "A"])
        self.assertEqual(chart["layout"]["showlegend"], False)

    def test_real_dash_app_has_results_and_embedded_jaal(self):
        try:
            import dash
            import dash_cytoscape
            import jaal
            import dash_bootstrap_components
        except ImportError as exc:
            self.skipTest(f"Dash/Jaal optional runtime: {exc}")
        from BertScript.stage4_history_preview import build_app
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "WorkPool")
            root.mkdir()
            app = build_app(root)
            response = app.server.test_client().get("/_dash-layout")
            self.assertEqual(response.status_code, 200, response.data[:300])
            data = response.get_json()
            import json
            serialized = json.dumps(data, ensure_ascii=False)
            self.assertIn("HistoryDataTable", serialized)
            self.assertIn("HistoryDistributionColumn", serialized)
            self.assertIn("HistoryDistributionPlot", serialized)
            self.assertIn("HistoryDistributionInfo", serialized)
            self.assertIn("JaalOriginalRoot", serialized)
            self.assertIn("JaalGraph", serialized)
            self.assertEqual(app.server.test_client().get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
