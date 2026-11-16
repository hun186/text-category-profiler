# KI-012 離線 SQLite 複本檔案完整性快檢

本工具是**額外、明確執行**的讀取型檢查，不取代既有只檢查結構的 audit、candidate inventory 和 triage。它會執行 SQLite `PRAGMA quick_check(1)`，需要讀取 SQLite 內部頁面，因此不應用於正在寫入的資料庫。

操作前必須停止所有 writer，建立獨立、靜止、沒有 WAL/journal/SHM sidecar 的 SQLite 複本，放在**非 WorkPool** 資料夾。

```bat
run-bl001-sqlite-offline-health.bat --db "D:\private\offline-copy.sqlite3"
```

- `PASS_OFFLINE_QUICK_CHECK`／exit 0：離線複本結構檢查通過，且 SQLite quick_check=ok，沒有候選表；並非正式資料庫健康證明。
- `REVIEW_REQUIRED`／exit 1：quick_check=ok，但存在候選表或可疑前綴；仍是 `owner_status=UNKNOWN`，不得清理。
- `UNVERIFIABLE`／exit 2：離線來源不合規、SQLite 結構錯誤、quick_check 不通過、超過檔案上限、或檢查期間檔案識別資訊變動。

預設最多讀取 256 MiB SQLite 複本，`--max-mib` 可設定 1～4096 MiB。使用 `mode=ro&immutable=1` 與 `PRAGMA query_only=ON`，不執行 DROP、VACUUM、刪除、修復或備份操作。

SQLite `quick_check(1)` **不是**完整 `integrity_check`，也不檢查全部外鍵，不能證明業務資料內容正確、Windows／網路共享磁碟可靠性或正式 WorkPool 復原能力。檔案大小及修改時間前後檢查只是一種警戒，**不能證明**檔案在驗收期間完全靜止。