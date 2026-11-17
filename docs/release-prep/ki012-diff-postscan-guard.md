# KI-012 離線雙複本 Diff 最後安全複核

`compare_offline_copies` 會先獨立執行來源盤點、再讀取兩份 SQLite schema；過去僅比對兩次讀取期間檔案身分與候選名稱，若 `-wal/-shm/-journal` sidecar 在第二次讀取期間才出現，SQLite `immutable=1` 可能忽略其內容而錯誤宣告 `PASS_NO_CANDIDATES`。

現在 Diff 在第二次 schema 讀取後，也再次檢查兩份來源的 WorkPool 路徑、符號／硬連結、sidecar，並將 `st_nlink` 納入前後檔案身分比較。只要觀察到不一致，回報 `UNVERIFIABLE`／`offline_copy_changed_during_diff`；不輸出已確認新增或刪除候選表的結論。私人 SQLite 測試刻意在第二次掃描後新增 WAL sidecar 或硬連結。

注意：依然只是對獨立離線複本做結構防護，不能證明檔案在所有時間都完全靜止；任何候選表仍屬所有權未知，禁止自動清除，正式 WorkPool 未經測試。