# KI-012 離線 SQLite 複本禁止硬連結

純讀取 `audit_stage_sqlite` 與 `inventory_offline_copy` 現在會在打開 SQLite 之前檢查一般檔案的 hard-link 計數。若 `st_nlink != 1`，回報 `hardlink_not_allowed`，不進行任何 schema 查詢。這可避免外部路徑透過硬連結意外指向正式 WorkPool 中仍在使用的資料庫。

**重要：** hard-link 計數等於 1 並不能證明資料庫已停止寫入，也不能證明外部複本真的獨立。仍須在所有 writer 已停止後建立實際分離的 SQLite 備份／複本，放在非 WorkPool 目錄。副檔名、檔名和複本路徑均不是安全證據。工具不修改、備份、修復或刪除任何外部資料庫。