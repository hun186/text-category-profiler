# KI-012 離線候選表盤點完整名稱指紋

當候選表超過 20 筆，inventory 與 diff 雖然仍只顯示前 20 個名稱，但會用**完整**候選表清單與可疑前綴清單計算 SHA-256 名稱指紋。兩次 schema 讀取若名稱被更換，即使總數不變、變更發生在未顯示的第 21 筆之後，也會回報 `UNVERIFIABLE`／`snapshot_changed_or_inconsistent`，避免誤判候選表新增或消失。

指紋只對 SQLite schema **表名稱**計算，不讀取業務資料列，不代表檔案內容驗證或 cryptographic snapshot sealing。離線複本仍需停止所有 writer，且在非 WorkPool 路徑獨立保存；表的所有權永遠為 `UNKNOWN`，不能據此刪除或清理。