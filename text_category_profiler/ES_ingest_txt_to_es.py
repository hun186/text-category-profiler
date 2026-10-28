"""Legacy import/CLI compatibility for the standalone Elasticsearch ingestion script.

Actual implementation: scripts/ES_ingest_txt_to_es.py.
No optional Elasticsearch dependencies are loaded by importing this module.
"""
from pathlib import Path
import importlib
import runpy


_PUBLIC = frozenset({
    "iter_txt_paths", "read_text_best_effort",
    "make_uuid_from_file", "make_uuid_from_content",
    "build_doc_from_file", "build_doc_from_file_OLD",
    "bulk_insert_txt_dir", "chunked",
})


def __getattr__(name):
    if name not in _PUBLIC:
        raise AttributeError(name)
    module = importlib.import_module("scripts.ES_ingest_txt_to_es")
    return getattr(module, name)


def main():
    target = Path(__file__).resolve().parents[1] / "scripts" / "ES_ingest_txt_to_es.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
