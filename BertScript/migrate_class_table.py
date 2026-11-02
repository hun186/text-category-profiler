"""Reproduce/verify the historical Python-dict to CSV migration (one-time only)."""
from __future__ import annotations
import argparse
import ast
from datetime import date
from pathlib import Path

if __package__:
    from .class_table_metadata import MetadataError, atomic_write, check_round_trip, load_class_table, table_to_csv
else:
    from class_table_metadata import MetadataError, atomic_write, check_round_trip, load_class_table, table_to_csv


# Explicitly audited later edits to the authoritative 2,013-row CSV.
# In --allow-pending-additions mode ONLY, accept these exact five records:
# three agricultural semicolon synonyms split into CT / Explanation / Notes,
# and two historical book-section descriptions moved to Notes (minus a tab).
# No broad legacy CT/Explanation differences are allowed. New edits require
# updating this reviewable evidence rather than disabling the migration gate.
CURATED_METADATA_OVERRIDES = {
    "Agriculture": {"CT": "農業", "Explanation": "農藝", "Notes": "農學"},
    "Fishery": {"CT": "漁業", "Explanation": "水產業", "Notes": ""},
    "Forestry": {"CT": "林業", "Explanation": "林學", "Notes": ""},
    "BD-Acknowledgements": {
        "CT": "致謝詞", "Explanation": "",
        "Notes": "有時作為序言的一部分而不是單獨的部分。這部分有時被放在書後附屬資料中。它記錄了那些為本書的創作做出貢獻的人。",
    },
    "BD-Bibliography": {
        "CT": "參考書目", "Explanation": "",
        "Notes": "撰寫正文時參考的其他作品清單，在非小說類書籍或研究論文中最常見。",
    },
}


# Exact corresponding pre-migration source values for the five later
# human-readable metadata splits. An opt-in comparison applies these guarded
# corrections to the *expected* baseline, then still compares all records.
CURATED_SOURCE_FIELDS = {
    "Agriculture": {"CT": "農業;農藝;農學", "Explanation": ""},
    "Fishery": {"CT": "漁業;水產業", "Explanation": ""},
    "Forestry": {"CT": "林業;林學", "Explanation": ""},
    "BD-Acknowledgements": {
        "CT": "致謝詞",
        "Explanation": "\t有時作為序言的一部分而不是單獨的部分。這部分有時被放在書後附屬資料中。它記錄了那些為本書的創作做出貢獻的人。",
    },
    "BD-Bibliography": {
        "CT": "參考書目",
        "Explanation": "\t撰寫正文時參考的其他作品清單，在非小說類書籍或研究論文中最常見。",
    },
}


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


# Old Python-dict spelling/typographical forms that have already been
# normalized in the authoritative CSV. Apply ONLY to opt-in historical
# verification; never silently rename a current graph node or proposal.
HISTORICAL_LABEL_NORMALIZATIONS = {
    "Autonomous Car Industry,": (
        "Autonomous Car Industry", {"CT": "自駕車產業", "Explanation": ""}
    ),
    "Navigational Warning-Fishing In Unauthorized Zone": (
        "Navigational Warning-Fishing in Unauthorized Zone",
        {"CT": "未授權區域捕漁相關航行警告", "Explanation": ""},
    ),
    "TimeStamp": (
        "Timestamp", {"CT": "時間戳", "Explanation": ""}
    ),
}

# Existing 2026-11-02 AI notes were authored before dates became required.
# This exact historical provenance family is REVIEW-ONLY; new proposals
# must still pass the stricter class_table_ai_proposals gate.
HISTORICAL_AI_NOTES_PREFIX = (
    "AI新增｜來源=TopicTree.csv｜理由=ClassTable缺少對應類別｜"
    "狀態=待人工審核"
)


def _require_pending_ai_addition(label, entry):
    """Verify additions are marked as unapproved; never approve Notes here."""
    note = entry.get("Notes", "")
    if note == HISTORICAL_AI_NOTES_PREFIX or (
        note.startswith(HISTORICAL_AI_NOTES_PREFIX + "｜提醒=")
        and len(note.split("｜")) == 5
        and note.split("｜提醒=", 1)[1].strip()
    ):
        # The legacy, undated TopicTree-origin record has explicit
        # 待人工審核 status and must never be upgraded to approved.
        return
    parts = note.split("｜")
    if len(parts) not in (5, 6) or parts[0] != "AI新增":
        raise MetadataError(f"{label!r}: extra ClassTable row requires AI新增 Notes")
    fields = {}
    for item in parts[1:]:
        key, sep, value = item.partition("=")
        if not sep or not value.strip() or key in fields:
            raise MetadataError(f"{label!r}: invalid AI Notes field")
        fields[key] = value.strip()
    expected = {"日期", "來源", "理由", "狀態"}
    if set(fields) not in (expected, expected | {"目標類別"}):
        raise MetadataError(f"{label!r}: incomplete or unexpected AI Notes fields")
    try:
        parsed = date.fromisoformat(fields["日期"])
    except ValueError as exc:
        raise MetadataError(f"{label!r}: invalid AI Notes date") from exc
    if parsed.isoformat() != fields["日期"]:
        raise MetadataError(f"{label!r}: AI Notes date must be YYYY-MM-DD")
    if fields["狀態"] != "待人工審核" or parts[-1] != "狀態=待人工審核":
        raise MetadataError(f"{label!r}: AI addition must remain 待人工審核")


def verify(original, actual, *, allow_pending_additions=False):
    expected = {k: dict(v) for k, v in original.items()}
    correct_known(expected)
    if allow_pending_additions:
        for legacy_label, (canonical, source_fields) in (
            HISTORICAL_LABEL_NORMALIZATIONS.items()
        ):
            if legacy_label not in expected:
                continue  # synthetic/partial historical tests
            if expected[legacy_label] != source_fields:
                raise MetadataError(
                    f"{legacy_label!r}: unexpected historical rename source"
                )
            if canonical in expected:
                raise MetadataError(
                    f"{canonical!r}: already exists before historical rename"
                )
            expected[canonical] = expected.pop(legacy_label)
    missing = set(expected) - set(actual)
    extra = set(actual) - set(expected)
    if missing or (extra and not allow_pending_additions):
        raise MetadataError(
            f"row count or ClassLabel set differs: missing={sorted(missing)[:20]}, "
            f"extra={sorted(extra)[:20]}"
        )
    # Preserve all historical CT/Explanation values even when opt-in AI
    # additions extend the official CSV. New rows remain unapproved.
    if allow_pending_additions:
        # Reconcile only five exact, separately documented post-migration
        # field splits. Reject any unexpected historical source or current
        # target; this is an explicit correction, not a skipped comparison.
        for label, corrected in CURATED_METADATA_OVERRIDES.items():
            if label not in expected:
                continue  # Small synthetic legacy fixtures need not contain all five.
            if expected[label] != CURATED_SOURCE_FIELDS[label]:
                raise MetadataError(f"{label!r}: unexpected historical source for guarded correction")
            if actual[label] != corrected:
                raise MetadataError(f"{label!r}: guarded metadata correction differs")
            expected[label] = {
                "CT": corrected["CT"], "Explanation": corrected["Explanation"],
            }
    differences = [
        label for label, item in expected.items()
        if item != {"CT": actual[label]["CT"],
                    "Explanation": actual[label]["Explanation"]}
    ]
    if differences:
        raise MetadataError(f"CT/Explanation mismatch: {differences[:20]}")
    if extra:
        for label in sorted(extra):
            _require_pending_ai_addition(label, actual[label])
    check_round_trip(actual)


def main(argv=None):
    p = argparse.ArgumentParser(description="Reproduce/verify legacy metadata migration")
    p.add_argument("--source", required=True, type=Path)
    targets = p.add_mutually_exclusive_group(required=True)
    targets.add_argument("--output", type=Path)
    targets.add_argument("--verify", type=Path)
    p.add_argument("--allow-pending-additions", action="store_true",
                   help="Verify legacy rows unchanged while accepting only AI新增 Notes still marked 待人工審核")
    args = p.parse_args(argv)
    if args.allow_pending_additions and not args.verify:
        p.error("--allow-pending-additions requires --verify")
    try:
        old, duplicate_keys = read_legacy(args.source)
        migrated = {k: dict(v) for k, v in old.items()}
        correct_known(migrated)
        if args.output:
            check_round_trip(migrated)
            atomic_write(args.output, table_to_csv(migrated))
        actual = load_class_table(args.output or args.verify)
        verify(old, actual, allow_pending_additions=args.allow_pending_additions)
    except (MetadataError, OSError, SyntaxError, ValueError) as exc:
        p.exit(2, f"ERROR: {exc}\n")
    print(f"Migration PASS: source labels={len(old)}, CSV rows={len(actual)}, "
          f"duplicate source labels={duplicate_keys}; CT/Explanation/Unicode equivalence verified after documented corrections and CN renames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
