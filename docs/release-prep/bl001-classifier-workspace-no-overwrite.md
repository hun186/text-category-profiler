# BL-001｜Stage 2 RunClassfier 目錄交接不可覆寫

原正式入口 `BertScript/RunClassfier.py` 對
`*_rdy_for_RunClassfier` 啟動用 `os.rename`，完成時使用
`_retry_classifier_handoff`，後者僅檢查 `isdir`，
可能跳過既有目的目錄或在 Linux 意外覆寫競爭建立的空資料夾。
Ctrl+C 遺留的 running 目錄應保留，不能被自動清理。

此次正式執行採用 `_classifier_transition_noreplace`：

- 嚴格驗證 ready → running、running → CombineTestResult ready
  的 basename 尾碼與目的路徑；不替換父目錄中的同名文字。
- 支援使用者輸入尾端 `/` 或 `\\` 的工作目錄，僅去除尾端分隔符，
  保留原本路徑寫法。
- 保護真實來源資料夾與 symlink／Windows Junction；目的目錄存在即拒絕。
- 使用共用 `_handoff_rename_noreplace` 保證 Linux/Windows
  的無覆寫語意。遇跨磁碟部分複製或刪除失敗，保留兩邊供人工檢查，
  不執行下一個階段。
- 舊 `_retry_classifier_handoff` 保留供相容性測試／明確外部呼叫；
  **正式成功交接不再使用可能覆寫的舊重試機制**。
- 現有 TF15Bert 模型輸出目錄租用／釋放行為不在本 PR 範圍；
  未變更模型計算、資料庫、GPU 操作。

```bash
python -m unittest -v tests.test_bl001_classifier_workspace_no_overwrite tests.test_classifier_stage
```

新測試全部使用私人 `TemporaryDirectory`，不存取真實
WorkPool／SQLite／模型。Hosted CI 通過不等於完成正式工作池的實機驗收。
