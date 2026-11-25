# BL-001｜外部 WorkPool 自動挑選模式零交集應停止

`WorkPoolManager.acquire` 曾在沒有指定工作 ID
（`WeiTechworkID==""`）、但 Incoming 內有檔案而
WorkPool 內**完全沒有同名項目**時直接回傳空字串。
若呼叫端把此結果當作正常無外部工作而繼續資料轉換，
既有外部排程有可能處理未認領的資料來源。

本批在前置 #352 的「指定 ID 必須實際認領」之上，
擴充無指定 ID 模式：
- 有至少一個可認領同名候選：沿用原倒序挑最新、
  不覆寫移至 Processing 後回傳 ID。
- Incoming 有候選但 WorkPool 無任何交集：拋出
  `EXTERNAL_WORKPOOL_NO_MATCH`，不呼叫成功通知、
  不啟動 Stage 1 命令、不建立 Processing 目錄。
- 已指定 ID 卻未認領：仍依 #352 報
  `EXTERNAL_WORK_ID_NOT_CLAIMED`。
- Incoming 空集合：維持原有 aborted 路徑。

本項與 #352 有 Git 分支依賴，不得在 #352
尚未通過正式 Review／Merge 前繞過 gate 合併。
所有 Hosted 測試僅用隔離 fake filesystem，
不操作正式 WorkPool、SQLite、模型及排程，不代表
已驗證所有舊外部 caller 的操作相容性。
