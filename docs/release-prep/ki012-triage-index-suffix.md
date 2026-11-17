# KI-012 候選表 pandas 索引命名一致性判讀

`bl001_stage_sqlite_candidate_triage` 原本只靠 `ix_<候選表名>_` 前綴、索引型態和欄位，判斷候選表索引是否符合 pandas 格式。可是手工索引 `ix_<候選表名>_manual_search` 即使實際只有 `index` 一個鍵，也可能被誤判成 pandas 索引。

現在除了既有的 non-UNIQUE、non-partial、BINARY、ASC 與真實欄位驗證外，**必須確保索引名稱的欄位後綴正好等於索引鍵欄位依序以底線組合**。否則列入 `invalid_pandas_index_count`，不宣告 `all_indexes_pandas_compatible`。私人 SQLite 負向測試及既有合法 pandas MultiIndex 正向測試持續涵蓋這種契約。

不論結構是否符合 pandas，候選表所有權仍屬 UNKNOWN，不能由此推定是否孤兒、可刪除或可復原。工具只對停止寫入的非 WorkPool 離線獨立複本讀取 schema metadata。