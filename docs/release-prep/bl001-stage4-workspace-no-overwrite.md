# BL-001｜Stage 4 工作目錄交接保護

Stage 4 正式入口 `BertScript/Test_result_Vis.py` 透過
`BertScript/visualization_stage.py` 執行 ready → running → completed。
此前其預設 `os.rename` 在 Linux 對既存空目錄可能發生替換，
導致歷史 Ctrl+C 遺留目錄或另一批次的工作目錄被覆寫。

本變更使 **未顯式注入 rename 的正式執行流程** 使用
`_stage4_move_noreplace`，兩段轉移都驗證：

- 精確的工作目錄 basename 尾碼及正確目的位置；
- 來源真實資料夾，不允許 symlink／Windows reparse/junction；
- 目的位置不存在，包括斷掉的 symbolic link；
- 共用 `TCF_utils._handoff_rename_noreplace`：Linux `renameat2(RENAME_NOREPLACE)`、
  Windows `os.rename` 不可覆寫語意；其他 POSIX 平台不支援時直接拒絕；
- 完成後檢查來源名稱已消失、目的是真實目錄；`EXDEV` 跨磁碟
  若發生部分複製／刪除失敗，不自動清理、不開始下一階段。

保留顯式 `rename=` 注入，用於既有測試與相容呼叫者；
正式 `Test_result_Vis.main` 未注入，會自動使用新安全行為。
不變更 Dash UI、模型、資料庫 schema 或任何既有 WorkPool 資料。

離線驗證：

```bash
python -m unittest -v tests.test_bl001_stage4_workspace_no_overwrite tests.test_visualization_stage
```

所有新增測試僅使用 Python `TemporaryDirectory`，不需要真實分類模型、
GPU、資料庫或正式 WorkPool。Hosted Ubuntu/Windows CI 驗證通過也不代表
正式工作站、網路共享磁碟、所有競爭時序已完成實機驗收。
