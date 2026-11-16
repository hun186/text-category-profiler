# KI-012 離線候選表判讀跨次 schema 指紋

當 `run-bl001-sqlite-candidate-triage.bat` 先做 inventory，再打開離線複本檢查候選表欄位／索引時，現在會先對**完整表名集合**重新計數及 SHA-256 指紋驗證。即使原本 `PASS_NO_CANDIDATES`、之後才新增候選表，或原本 1 張候選表被等量改名，工具也會以 `UNVERIFIABLE`／`candidate_schema_changed_since_inventory` 拒絕輸出似是而非的詳細判讀。

表名變化的比對不能證明資料庫在檢查全程完全靜止，也不能識別候選表的建立者。此工具仍只接受已停止 writer、另存於非 WorkPool 路徑的獨立 SQLite 複本；不讀取業務資料列，不清理任何資料表。