# KI-012 離線候選表索引語意判讀

`run-bl001-sqlite-candidate-triage.bat --db "D:\private\offline.sqlite3"` 僅檢查已停止 writer、位於獨立非 WorkPool 目錄的 SQLite 複本。

`has_pandas_index` 只代表至少一個符合 pandas 形式的索引。另提供 `invalid_pandas_index_count`、`unexpected_index_count`、`all_indexes_pandas_compatible`，讓 UNIQUE、partial、DESC、NOCASE、expression 或非 pandas 名稱的索引不會被忽略。索引名稱最多呈現 8 筆，但完整計數不截斷。

這只檢查表結構，**不能判定建立者、是否有人仍在寫入、或能否刪除**。候選表仍維持 `owner_status=UNKNOWN`、`safe_to_delete=false`，不提供任何清理功能。