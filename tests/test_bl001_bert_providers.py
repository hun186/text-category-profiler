"""No-service characterizations of explicit BertScript legacy providers (BL-001)."""
import ast
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
DATAFRAME = ROOT / "BertScript" / "df_utils.py"
MP = ROOT / "BertScript" / "MP_utils.py"
UTILITIES = ROOT / "BertScript" / "utilities.py"


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def find_definition(path, kind, name):
    definitions = [
        node for node in parsed(path).body
        if isinstance(node, kind) and node.name == name
    ]
    if len(definitions) != 1:
        raise AssertionError("Expected exactly one %s in %s" % (name, path))
    return definitions[0]


class BertLegacyProviderTests(unittest.TestCase):
    def test_stage_helpers_use_explicit_package_sources(self):
        df_imports = [
            node for node in parsed(DATAFRAME).body
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertIn(
            ("BertScript.MP_utils", {"MPlogger", "multicoreJob"}),
            [(n.module, {a.name for a in n.names}) for n in df_imports],
        )
        self.assertIn(
            ("BertScript.utilities", {"hash", "ShowElapsedTime"}),
            [(n.module, {a.name for a in n.names}) for n in df_imports],
        )
        mp_imports = [
            node for node in parsed(MP).body
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertEqual(
            [(n.module, [a.name for a in n.names]) for n in mp_imports],
            [("BertScript.utilities", ["timeNow"])],
        )
        for path in (DATAFRAME, MP):
            self.assertFalse(any(
                isinstance(node, ast.ImportFrom)
                and node.module in {"MP_utils", "utilities"}
                for node in ast.walk(parsed(path))
            ))

    def test_original_legacy_logger_still_uses_static_output(self):
        clazz = find_definition(MP, ast.ClassDef, "MPlogger")
        clock = lambda FMT: "2000-01-01 00:00:00"
        scope = {"os": os, "timeNow": clock}
        exec(compile(ast.Module(body=[clazz], type_ignores=[]), str(MP), "exec"), scope)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mp.log"
            scope["MPlogger"].logW("stage-probe", logFile=str(path))
            log = path.read_text(encoding="utf-8")
        self.assertEqual(
            log, "2000-01-01 00:00:00,PID %s: stage-probe\n" % os.getpid()
        )

    def test_legacy_hash_behaviour_unchanged(self):
        method = find_definition(UTILITIES, ast.FunctionDef, "hash")
        scope = {"hashlib": hashlib}
        exec(
            compile(ast.Module(body=[method], type_ignores=[]), str(UTILITIES), "exec"),
            scope,
        )
        self.assertEqual(
            scope["hash"]("sample"), hashlib.sha512(b"sample").hexdigest()
        )
        self.assertEqual(
            scope["hash"](b"sample", "sha1"),
            hashlib.sha1(b"sample").hexdigest(),
        )
        self.assertIsNone(scope["hash"](None))

    def test_import_failure_is_not_masked_with_a_fallback(self):
        statement = next(
            n for n in parsed(MP).body if isinstance(n, ast.ImportFrom)
            and n.module == "BertScript.utilities"
        )
        calls = []

        def broken_import(name, *args, **kwargs):
            calls.append(name)
            raise RuntimeError("stage provider import failed")

        with patch("builtins.__import__", side_effect=broken_import):
            with self.assertRaisesRegex(RuntimeError, "stage provider import failed"):
                exec(
                    compile(ast.Module(body=[statement], type_ignores=[]), str(MP), "exec"),
                    {},
                )
        self.assertEqual(calls, ["BertScript.utilities"])


if __name__ == "__main__":
    unittest.main()
