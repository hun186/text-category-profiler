# BL-001｜WorkPool 中斷位置觀測與安全復原契約

現有 WorkPool external work-ID 會涉及 incoming、processing、
processed 三個資料夾及獨立的 SQLite/report backup。
備份、Stage 1～4、最後 Work-ID move 並**非原子交易**；
單純看到某個資料夾存在，不足以知道程序是否仍執行、
報告是否完整、是不是同一輪 owner、資料庫是否可重試，
更不能自行刪除或重新啟動工作單。

新 `classify_external_work_item_locations` 是**純資料**
函式：由經過驗證的 work-ID 與第三方明確提供的
incoming/processing/processed 三組三值 metadata
（`True`、`False` 或 `None=未知`）產生
frozen `WorkItemRecoveryObservation`：

| 輸入觀測 | 狀態 | 可採行的系統行為 |
| --- | --- | --- |
| 恰一處為 True，其他已觀測 False | `INCOMING_ONLY` / `PROCESSING_ONLY` / `PROCESSED_ONLY` | 只顯示人工調查線索 |
| 三處均已觀測 False | `NO_LOCATION_OBSERVED` | 不能宣稱資料已清除或完成 |
| 兩處以上為 True | `MULTIPLE_LOCATIONS` | 辨識衝突，禁止默默選取位置 |
| 任何觀測未知而未有已知雙重出現 | `INCOMPLETE_OBSERVATION` | 保留未知，不作自動決策 |

**所有狀態**固定
`automatic_retry_authorized=False`、
`delivery_verified=False`、
`requires_operator_review=True`。輸出僅包含位置類型名稱
而非實際路徑或 Work-ID；Work-ID 在判斷前採既有
跨平台合法性驗證。非 `bool/None` 值必須報錯，不能
隱式把空字串、數字或任意物件轉成真偽觀測。

此函式**不讀取磁碟、不開啟資料庫、不列出工作池內容、
不掃描 process、不移動目錄、不補償、不再執行 job**。
現有正式 scheduler/WorkPool 不會因加入此函式而自動復原。
它是未來可信的人工診斷或恢復 UI 的候選基礎，真正要
批准安全重跑，仍須確認 job owner/quiescence、檔案完整性、
SQLite/backup/Report commit 狀態及 Windows/Linux 實機驗證。

跨平台 Hosted CI 以 27 種三值組合與既有 WorkPool 行為測試，
不宣稱此為正式環境的 end-to-end recovery 實作。
