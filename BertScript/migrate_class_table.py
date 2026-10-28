"""Reproduce/verify the historical Python-dict to CSV migration (one-time only)."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path

if __package__:
    from .class_table_metadata import MetadataError, atomic_write, check_round_trip, load_class_table, table_to_csv
else:
    from class_table_metadata import MetadataError, atomic_write, check_round_trip, load_class_table, table_to_csv


def read_legacy(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
    found = [n.value for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "ClassTable" for t in n.targets)]
    if len(found) != 1 or not isinstance(found[0], ast.Dict):
        raise MetadataError("expected one legacy ClassTable dictionary assignment")
    seen, duplicate_keys = set(), []
    for key_node in found[0].keys:
        key = ast.literal_eval(key_node)
        if key in seen:
            duplicate_keys.append(key)
        seen.add(key)
    # ast.literal_eval reproduces Python's last-key-wins dictionary semantics.
    original = ast.literal_eval(found[0])
    result = {}
    for label, entry in original.items():
        if not isinstance(label, str) or not isinstance(entry, dict) or not isinstance(entry.get("CT"), str):
            raise MetadataError(f"invalid legacy entry: {label!r}")
        if set(entry) - {"CT", "Explaination", "Explanation"}:
            raise MetadataError(f"unknown legacy metadata field: {label!r}")
        if "Explanation" in entry and "Explaination" in entry:
            raise MetadataError(f"ambiguous explanation fields: {label!r}")
        value = entry.get("Explanation", entry.get("Explaination", ""))
        if not isinstance(value, str):
            raise MetadataError(f"invalid legacy explanation: {label!r}")
        result[label] = {"CT": entry["CT"], "Explanation": value}
    return result, duplicate_keys


def correct_known(table):
    commerce, nice = table["Commerce"], table["2016 Nice Truck Attack"]
    if not commerce["Explanation"].startswith("2016年尼斯襲擊"):
        raise MetadataError("unexpected Commerce source, refusing automatic correction")
    if nice != {"CT": "學術", "Explanation": "學術界、學術研究"}:
        raise MetadataError("unexpected Nice event source, refusing automatic correction")
    nice["CT"], nice["Explanation"] = "2016尼斯卡車襲擊事件", commerce["Explanation"]
    commerce["Explanation"] = ""
    for label, ct in (("3C Product News-Asus Product News", "ASUS產品新聞"),
                      ("3C Product News-Samsung Product News", "Samsung產品新聞")):
        if table[label]["CT"] != "Apple產品新聞":
            raise MetadataError(f"unexpected {label} source; refusing correction")
        table[label]["CT"] = ct

    # The active TopicTree already uses CN-scoped labels; migrate exactly two
    # old metadata keys without creating aliases or silently changing others.
    real_estate_renames = (
        ("Government Real Estate Policy", "CN Government Real Estate Policy",
         {"CT": "政府房地產政策", "Explanation": ""},
         {"CT": "中國政府房地產政策", "Explanation": ""}),
        ("Real Estate Industry", "CN Real Estate Industry",
         {"CT": "中國房地產業", "Explanation":
          "中國房地產、房價、建築業，產業資訊；另房地產物件資訊屬Real Estate Object。"},
         {"CT": "中國房地產業", "Explanation":
          "中國房地產、房價、建築業，產業資訊；另房地產物件資訊屬Real Estate Object。"}),
    )
    for old_label, new_label, expected, replacement in real_estate_renames:
        if table.get(old_label) != expected or new_label in table:
            raise MetadataError(f"unexpected {old_label!r} source; refusing rename")
        del table[old_label]
        table[new_label] = replacement


def verify(original, actual):
    expected = {k: dict(v) for k, v in original.items()}
    correct_known(expected)
    if len(expected) != len(actual) or set(expected) != set(actual):
        raise MetadataError("row count or ClassLabel set differs")
    if expected != actual:
        diff = [k for k in expected if expected[k] != actual[k]]
        raise MetadataError(f"CT/Explanation mismatch: {diff[:20]}")
    check_round_trip(actual)


def main(argv=None):
    p = argparse.ArgumentParser(description="Reproduce/verify legacy metadata migration")
    p.add_argument("--source", required=True, type=Path)
    targets = p.add_mutually_exclusive_group(required=True)
    targets.add_argument("--output", type=Path)
    targets.add_argument("--verify", type=Path)
    args = p.parse_args(argv)
    try:
        old, duplicate_keys = read_legacy(args.source)
        migrated = {k: dict(v) for k, v in old.items()}
        correct_known(migrated)
        if args.output:
            check_round_trip(migrated)
            atomic_write(args.output, table_to_csv(migrated))
        actual = load_class_table(args.output or args.verify)
        verify(old, actual)
    except (MetadataError, OSError, SyntaxError, ValueError) as exc:
        p.exit(2, f"ERROR: {exc}\n")
    print(f"Migration PASS: source labels={len(old)}, CSV rows={len(actual)}, "
          f"duplicate source labels={duplicate_keys}; CT/Explanation/Unicode equivalence verified after documented corrections and CN renames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
