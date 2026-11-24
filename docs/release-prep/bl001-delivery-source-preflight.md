# BL-001｜工作單交付前先確認 Processing 來源存在

原本 `DeliveryManager.backup_and_complete` 先把報告
備份至 WorkPool/<work-id>，才呼叫
`LegacyFileSystem.move(processing/<work-id>, processed/<work-id>)`。
如果 Processing 來源根本不存在、是一般檔案，或已被外部
程序換成 symlink/junction，最後的不覆寫 move 雖會失敗，
報告備份可能早已寫入另一個同 ID 目的地。

本批在任何 cleanup／WorkPool 備份前新增
`LegacyFileSystem.verify_delivery_source` **唯讀預檢**：
- 對應 Processing leaf 必須存在、為真正目錄，而且
  leaf 不是 symlink、reparse point 或 Windows junction。
- 無法確認則立即拋出
  `WORKITEM_DELIVERY_SOURCE_NOT_REAL_DIRECTORY`，
  不開始任何 backup、chown、Completed mkdir 或 move。
- 原有成功路徑依舊 backup → no-replace move → postcommit log。
- 空 ID 的一般（非 Work-ID）cleanup 模式不需要 Processing
  目錄，舊邏輯不變。

**限制：** 此檢查沒有取得跨程序 owner 的原子 lock/handle，
來源可能在檢查與最終 move 之間被競爭程序替換；
真正的 move 仍是最終權威，但對早期 backup 的競爭風險，
仍需設計由 owner、immutable token、隔離 WorkPool 和
實機驗收確認。不能以此聲稱完整 transaction safety。
Windows/Linux Hosted CI 只測試私有 tempdir 與 fake
filesystem，未操作正式 WorkPool。
