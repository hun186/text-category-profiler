# KI-012 防止 Stage 替換破壞其他 SQLite 資料

原子式 Stage writer 先建立私人候選表，再在 `BEGIN IMMEDIATE` 中 DROP 舊 `sampleSrc`、重建表與索引。SQLite 的 `DROP TABLE` 在啟用外鍵的連線中，可能對參照該表的子表觸發 `ON DELETE CASCADE`；而建立在舊 `sampleSrc` 上的 Trigger 也會隨表一起消失。這兩種情況即使整筆替換交易最後提交成功，也可能讓其他資料或業務規則遺失。

現在 writer 在取得 `BEGIN IMMEDIATE` 寫入鎖後、實際 DROP 前，從 `sqlite_master` 及各表的 `PRAGMA foreign_key_list` **只讀取結構資訊**，發現「其他表參照 sampleSrc」或「Trigger 建立在 sampleSrc 上」就拋出 `ValueError`，回滾交易、清理由本次寫入者自身建立的候選表，**保留原始 sampleSrc、子表資料與 Trigger**。

這是保守的拒絕替換機制，**不是自動外鍵遷移或 Trigger 複製**。正常沒有這兩種依賴的 Stage SQLite 寫入照舊；不會掃描正式 WorkPool 或自動調整既有資料庫。已使用私人 SQLite 的 `ON DELETE CASCADE`、Trigger 與無關外鍵測試驗證新行為。正式 Windows／WorkPool 實機仍須獨立驗收。