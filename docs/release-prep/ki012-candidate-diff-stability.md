# KI-012 離線候選表差異比較穩定性

`run-bl001-sqlite-candidate-diff.bat --before "D:\private\copy-a.sqlite3" --after "D:\private\copy-b.sqlite3"` 僅接受兩個獨立且已停止 writer 的離線 SQLite 複本；不接受正式 WorkPool 根目錄、symlink、sidecar、壞損結構或相同檔案。

除了原有的候選表總數與前 20 個名稱，現在還會在結構比對的前後取得檔案識別資訊（裝置、inode、大小與修改時間、狀態時間）。若前後資訊不同，就回傳 `UNVERIFIABLE`／`offline_copy_changed_during_diff`，不宣告新增或刪除數量。

**限制：** 檔案識別資訊相同不能證明完全沒有資料變更，更不能證明 writer 已停止；這只是多一道 fail-closed 偵測。工具僅讀取資料庫 schema metadata，`owner_status=UNKNOWN`、`deletion_authorized=false` 永遠不因這個比較而改變。