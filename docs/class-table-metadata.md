# ClassTable metadata: CSV-first contract

The authoritative metadata file is ClassesTree/data/ClassTable.csv (UTF-8 with BOM). Its fixed schema is ClassLabel,CT,Explanation,Notes. Rows are sorted deterministically by exact English ClassLabel, with required unique ClassLabel and nonempty CT; Explanation and Notes may be empty. Existing 1,994 entries have blank Notes after the additive schema migration; their ClassLabel, CT, and Explanation are unchanged. Duplicate CT values are warnings rather than errors.

BertScript/ClassTable.py has been removed to avoid confusion with the authoritative CSV. All maintained callers now use the stdlib-only loader `BertScript.class_table_metadata.load_class_table()`, returning the same ClassLabel → {CT, Explanation, Notes} dictionary. Both direct-run scripts and package imports resolve the repository-owned `ClassesTree/data/ClassTable.csv` by using the loader's `__file__` to find the repository root, without machine-specific paths or cwd mutation. The CSV and `ClassesTree/data/TopicTree.csv` are colocated but have separate metadata and graph ownership. The historical misspelling Explaination is permitted only inside the one-time migration reader, not in active metadata or Dash UI.

External Python callers must migrate as follows:

```python
from BertScript.class_table_metadata import load_class_table
ClassTable = load_class_table()
```

The old `from ClassTable import ClassTable` and `from BertScript.ClassTable import ClassTable` interfaces no longer work. This remains an intentional Python import compatibility change. Moving the authoritative ClassTable CSV changes its filesystem path but **not its bytes**, schema, or TopicTree graph. External scripts using the former `BertScript/ClassTable.csv` file path must update it.

Notes（備註）可記錄類別來源、修訂理由及 AI 提議，與表示類別定義的 Explanation 分開，不應用 Notes 覆寫分類說明。建議 AI 自動生成紀錄格式：

    AI新增｜日期=2026-10-31｜來源=https://example.org/article｜理由=經多篇文本識別為現有類別缺口｜狀態=待人工審核
    AI補充｜日期=2026-10-31｜來源=https://example.org/article｜理由=補強現有類別的辨別條件｜狀態=待人工審核

- `AI新增` 指 AI **提議**新增類別，`AI補充` 指 AI **提議**補強既有欄位；只表示來源，不等於品質合格或已獲批准。人工可在 Notes 自由編寫備註。
- AI 應保留來源 URL/來源識別、日期、理由與 `待人工審核` 狀態；若無可靠證據不可杜撰來源。多次修訂請保留原紀錄或於 PR 留下變更歷程，不得直接覆寫人工作出的說明。
- 未來自動蒐集文本代理人應先產生 **候選 CSV 與 PR/diff**，確認類別去重、TopicTree 節點關係及人工審核後，才合併到正式 ClassTable；**Notes 文字不具備授權或自動核准功能**。避免尚未審核的類別直接進入分類資料集與視覺化。
- `BertScript.class_table_metadata.load_class_table()` 回傳的 dict-of-dicts 保留 `CT`、`Explanation`、`Notes` 鍵；CSV 讀寫、候選合併與 Unicode/逗號/換行必須保全備註內容。舊版三欄輸入須先轉成四欄再交給正式 validator。

Graph authority remains ClassesTree/data/TopicTree.csv, next to the new ClassTable CSV location. The historical prompt file TextClassificationDatasetOptimization/ChatGPT提問模板/2-1.TopicTree_old.csv is not the active graph authority and may differ from current TopicTree. TopicTree edges remain separate from metadata and both parent AND child endpoints form the node set, including non-hierarchical relations.

The October 2026 metadata alignment renames `Government Real Estate Policy` → `CN Government Real Estate Policy` (CT: 中國政府房地產政策) and `Real Estate Industry` → `CN Real Estate Industry` (CT: 中國房地產業). The full existing explanation of the industry label is preserved. Both CN-scoped names already appear in the active TopicTree; the two generic old keys are removed, not kept as duplicate aliases. Legacy migration verification includes these two explicit, guarded corrections, while strictly preserving every other label and metadata value.

Validation (stdlib-only):

    python -m BertScript.class_table_metadata validate --json

By default duplicate CT, graph nodes missing metadata, and orphan metadata are warnings (no mass auto-fill). --strict-tree turns set differences into failures. Duplicate/blank ClassLabels, blank CT, malformed CSV, or round-trip failures are errors.

For ChatGPT-proposed new edges, supply ClassTable_新增條目.csv with the canonical metadata schema and run:

    python -m BertScript.class_table_metadata merge --base-tree original-TopicTree.csv --edges 新增邊.csv --candidates ClassTable_新增條目.csv --output review-ClassTable.csv

Candidate ClassLabels MUST equal (all parent/child nodes in 新增邊.csv) minus (original TopicTree parent/child nodes); collisions with existing ClassTable keys fail. The output is not the official ClassTable until reviewed and explicitly deployed.

Reproduce and verify the migration against Hosted GitHub's pre-refactor source:

    git show ec212fd17835dd939b010a680955f95f12593598:BertScript/ClassTable.py > legacy-ClassTable.py
    python -m BertScript.migrate_class_table --source legacy-ClassTable.py --verify ClassesTree/data/ClassTable.csv

Snapshot: 1,994 unique legacy labels, 434 nonempty legacy explanations, 3,128 TopicTree edges, and 2,670 graph nodes. Python's last-key-wins behavior preserves the effective historical definition of the duplicated SASF-Accessory-Glasses-Sunglasses label and duplicated Maritime Industry-Ports And Logistics explanation. Except for the explicitly documented label renames, all other unique keys and CT/Explanation text are preserved. The four confirmed copy/paste corruptions are corrected: Commerce's unrelated Nice attack explanation is transferred to 2016 Nice Truck Attack, that event's CT is fixed, and ASUS/Samsung CTs no longer say Apple. Other possible semantic issues are not rewritten.

BertScript/ClassTable - 複製.py remains a historical backup only; it is not an active loader or metadata authority. Legacy deployment snapshots remain isolated, not silently reworked. The active Dash table column now uses Explanation.

Tests:

    python -m unittest -v tests.test_class_table_metadata tests.test_class_table_csv_only

Hosted workflow checks migration equivalence, metadata, compile, and regression tests, not full ML/GPU integration.
