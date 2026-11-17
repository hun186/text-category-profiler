# KI-012 基礎 SQLite Schema Audit：獨立快照檢查

最底層 `audit_stage_sqlite` 原本只在開啟資料庫之前檢查 WorkPool 路徑、符號／硬連結、sidecar 和檔案是否可讀；若有人在檢查過程中改寫檔案或新增 WAL sidecar，可能仍在函式結尾回傳 PASS。

現在 Audit 本身會在進行 schema metadata 查詢前後比對 **st_dev、inode、hard-link 數、檔案大小、mtime_ns、ctime_ns 及 resolved path**，並再次檢查 symlink/hardlink 與 `-wal/-shm/-journal` sidecar。檢查期間任何可觀察到的變動都回報 `FAIL`／`offline_copy_changed_during_audit`。私人 SQLite 回歸測試在真正開啟時注入新資料表與新 sidecar，確保不能誤判成功。

限制：檔案識別資訊與側車檔檢查是**盡力偵測**，不能證明所有並行寫入或惡意改動。請只對已停止 writer 的獨立離線 SQLite 複本執行，不代表正式 WorkPool 驗收。此工具不讀取業務資料列，也不修改資料庫。