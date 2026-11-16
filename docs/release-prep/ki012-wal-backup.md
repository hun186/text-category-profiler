# KI-012 WAL 模式 SQLite 私人備份驗證

`run-bl001-sqlite-wal-backup.bat` 預設在私人 TemporaryDirectory 建立 40 筆 SQLite，切換 WAL 並保留未 checkpoint 的已提交資料與 WAL sidecar，接著使用 Python `sqlite3.backup` API 備份到新的私人檔案，再還原到第三份私人檔案。

測試要求來源因 WAL sidecar 被離線盤點拒絕，備份與還原則必須包含完整 `sampleSrc`、`text_Index`、pandas index、View、無關資料表，以及所有權未知的候選表。所有候選表保留 `owner_status=UNKNOWN`、`candidate_deletion_authorized=false`。

可設定 `--rows` 10～500，但**沒有可指定正式資料庫的 `--db` 參數**。`PASS_PRIVATE_WAL_BACKUP` 只代表這種受控私人 WAL 備份情境通過，不代表可以直接備份活動中的正式 WorkPool、網路共享磁碟、實際災難恢復或 OS 磁碟滿載。