# KI-012 離線 SQLite 替換相依結構檢查

在獨立、已停止所有 writer、放在非 WorkPool 路徑的 SQLite 複本上，可執行：

```bat
run-bl001-sqlite-dependency-inventory.bat --db "D:\private\offline.sqlite3"
```

這是**唯讀 schema metadata 檢查**，統計附在 `sampleSrc` 的 Trigger、其他資料表參照 `sampleSrc` 的外鍵，以及候選表狀態；最多顯示 20 個名稱，數量完整計算。若存在相依結構，回報 `REVIEW_REQUIRED`／exit 1；若沒有觀察到，回報 `NO_DEPENDENCIES_OBSERVED`／exit 0；來源不合規或檢查過程資料庫身分資訊變動則 `UNVERIFIABLE`／exit 2。

**不是執行授權。** 無論結果為何，`replacement_authorized=false`、`candidate_deletion_authorized=false`、`production_workpool_verified=false`。只用於提前判斷 Stage writer 為何會拒絕替換，不讀取任何業務資料列，不執行 DROP/DELETE/修復，也不觸碰真正的 WorkPool。