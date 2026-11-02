# ClassTable pending duplicate AI proposals — 2026-11-02

These rows were **removed only from the authoritative**
`ClassesTree/data/ClassTable.csv` because their exact `ClassLabel` already
existed. They have **not been rejected semantically, approved, or merged**.

The preserved evidence is
`class-table-duplicate-ai-proposals-20261102.csv`, with:

- `OriginalLine`: physical source CSV row in `main@5ab405ec87e5dfc4724befa139de6d83af68b431`.
- `ClassLabel, CT, Explanation, Notes`: the original duplicate AI row's four
  fields, copied without changing its Notes.
- `RetainedLine, RetainedCT`: original row number and Chinese name kept in
  the active authoritative file.
- `ReviewStatus`: **待人工審核**. No automatic endorsement or translation
  replacement is implied.

The retained `Hepatology` row also bears `AI新增` Notes, because **both**
original occurrences were AI-sourced; the earliest instance was retained
solely to preserve first-seen behavior, not to infer human approval.

The formal file was then reserialized into its existing canonical
alphabetical `ClassLabel` order. **All other unique ClassLabels and their
CT/Explanation/Notes values are unchanged**, and TopicTree.csv was not edited.

To examine a future set of *new* proposed rows before adding to the canonical
file, supply a separate four-column CSV and run the read-only guard:

```sh
python -m BertScript.class_table_metadata check-append \
  --candidates proposed_class_table.csv --json
```

If an ID already exists in `ClassTable.csv`, the guard fails (exit 2). A
successful check **does not approve** translations or write files. Proposed
translation changes to existing IDs require a separate manual review; they
must not be appended as duplicate IDs. The AI proposal provenance preflight
has its own additional source/date/approval requirements.

This directory is a historical review record, **not** an importable ClassTable
candidate file or a second authoritative metadata source.
