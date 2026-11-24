# BL-001｜外部工作單 ID 不得被解讀成路徑

正式 WorkPool 整合可由排程佇列目錄取得工作單 ID，也可在 CLI
參數預先傳入 Work-ID。既有 `WorkPoolManager.acquire` 與
`DeliveryManager.backup_and_complete` 使用 `os.path.join(root, work_id)`
組成來源、備份目的地與完成目的地；其中使用者設定的 ID 未經
跨平台路徑檢查，若含 `../`、Windows drive／UNC 語法或
NTFS Alternate Data Stream（冒號），可能讓路徑離開預定根目錄。

本變更提供 `validate_external_work_id`：只允許**單一原樣子目錄名稱**，
拒絕空 ID 作為實際工作單、`.`、`..`、正反斜線、冒號、
控制字元、結尾點號或空格；保留中文字、內部空格及一般單號。
`""` 仍保留原有「無外部工作單」模式，不會被當成實際 ID。

在兩個執行入口皆採 fail-closed：選定佇列候選工作單**搬移前**
驗證，已指定的 CLI 工作單 ID 在**讀取佇列前**驗證；
完成階段在任何 WorkPool 備份、chown、移交或完成紀錄前驗證。
不對歷史目錄清理、不自動重新命名、不更改外部佇列選取排序。

隔離測試使用假的 filesystem 或私人 `TemporaryDirectory`，
驗證 Linux／Windows 路徑穿越、UNC、ADS、控制字元及 Unicode
正常工作單與原有完整備份／搬移呼叫。未接觸正式工作池，
此項 CI 不等於實機 SMB/NFS 工作池驗收。
