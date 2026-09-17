from pathlib import Path
import tokenize
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOTS = (
    ROOT / "TCFMain.py",
    ROOT / "TCF_Params",
    ROOT / "DatasetConverter",
    ROOT / "BertScript",
    ROOT / "text_category_profiler",
)


def canonical_python_files():
    for root in PYTHON_ROOTS:
        if root.is_file():
            yield root
        else:
            yield from sorted(root.rglob("*.py"))


class RepositoryCompileGateTests(unittest.TestCase):
    def test_all_python_files_are_syntactically_valid(self):
        failures = []

        for path in canonical_python_files():
            try:
                with tokenize.open(path) as source_file:
                    source = source_file.read()
                compile(source, str(path.relative_to(ROOT)), "exec")
            except (SyntaxError, IndentationError) as error:
                location = f"line {error.lineno}"
                if error.offset is not None:
                    location += f", column {error.offset}"
                failures.append(
                    f"{path.relative_to(ROOT)}: {type(error).__name__}: "
                    f"{error.msg} ({location})"
                )

        self.assertEqual([], failures, "Syntax failures:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
