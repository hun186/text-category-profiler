# KI-012 最底層離線盤點一致性修正

原本 `inventory_offline_copy` 先從 SQLite 複本讀取候選表名，再另外呼叫 `audit_stage_sqlite` 進行第二次結構稽核。如果稽核期間候選表新增或等量改名，可能產生過期的「沒有候選表」或候選表名快照。

現在 inventory 本身會在稽核後重新查詢完整表名，與首次擷取的候選／可疑前綴 SHA-256 名稱指紋、裝置、inode、硬連結數、檔案大小、mtime、ctime 及 sidecar 狀態交叉比對；任何異常回報 `UNVERIFIABLE`／`offline_inventory_changed_during_audit`，不宣告空盤點或刪除安全。測試涵蓋掃描途中新增候選表與不改變總數的改名。

**限制：** Metadata 前後相同不能證明檔案真正靜止。只能在所有 Writer 已停止後，對非 WorkPool、非 symlink／hardlink 的獨立 SQLite 複本進行。完全不讀取業務資料列，也不清理資料庫。