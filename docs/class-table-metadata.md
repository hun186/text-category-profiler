# ClassTable metadata: CSV-first contract

The authoritative metadata file is BertScript/ClassTable.csv (UTF-8 with BOM). Its fixed schema is ClassLabel,CT,Explanation. Rows are sorted deterministically by exact English ClassLabel, with required unique ClassLabel and nonempty CT; Explanation may be empty. Duplicate CT values are warnings rather than errors.

BertScript/ClassTable.py retains the public ClassTable dict-of-dicts Python API. Direct BertScript entrypoints and package imports remain supported, with no machine-specific paths or cwd mutation. New active consumers use Explanation only. The historical misspelling Explaination is permitted only inside the one-time migration reader, not in active ClassTable data or Dash UI.

Graph authority remains ClassesTree/data/TopicTree.csv. The prompt file TextClassificationDatasetOptimization/ChatGPT提問模板/2-1.TopicTree_old.csv is currently identical. TopicTree edges remain separate from metadata and both parent AND child endpoints form the node set, including non-hierarchical relations.

Validation (stdlib-only):

    python -m BertScript.class_table_metadata validate --json

By default duplicate CT, graph nodes missing metadata, and orphan metadata are warnings (no mass auto-fill). --strict-tree turns set differences into failures. Duplicate/blank ClassLabels, blank CT, malformed CSV, or round-trip failures are errors.

For ChatGPT-proposed new edges, supply ClassTable_新增條目.csv with the canonical metadata schema and run:

    python -m BertScript.class_table_metadata merge --base-tree original-TopicTree.csv --edges 新增邊.csv --candidates ClassTable_新增條目.csv --output review-ClassTable.csv

Candidate ClassLabels MUST equal (all parent/child nodes in 新增邊.csv) minus (original TopicTree parent/child nodes); collisions with existing ClassTable keys fail. The output is not the official ClassTable until reviewed and explicitly deployed.

Reproduce and verify the migration against Hosted GitHub's pre-refactor source:

    git show ec212fd17835dd939b010a680955f95f12593598:BertScript/ClassTable.py > legacy-ClassTable.py
    python -m BertScript.migrate_class_table --source legacy-ClassTable.py --verify BertScript/ClassTable.csv

Snapshot: 1,994 unique legacy labels, 434 nonempty legacy explanations, 3,128 TopicTree edges, and 2,670 graph nodes. Python's last-key-wins behavior preserves the effective historical definition of the duplicated SASF-Accessory-Glasses-Sunglasses label and duplicated Maritime Industry-Ports And Logistics explanation. All unique keys and all other CT/Explanation text are preserved. The four confirmed copy/paste corruptions are corrected: Commerce's unrelated Nice attack explanation is transferred to 2016 Nice Truck Attack, that event's CT is fixed, and ASUS/Samsung CTs no longer say Apple. Other possible semantic issues are not rewritten.

BertScript/ClassTable - 複製.py is historical backup and deliberately unchanged. Legacy deployment snapshots remain isolated, not silently reworked. The active Dash table column now uses Explanation.

Tests:

    python -m unittest -v tests.test_class_table_metadata

Hosted workflow checks migration equivalence, metadata, compile, and regression tests, not full ML/GPU integration.
