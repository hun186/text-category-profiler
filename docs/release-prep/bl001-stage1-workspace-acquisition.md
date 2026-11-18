# BL-001｜Stage 1 DataConverter running 目錄獨占建立

正式入口 `DatasetConverter/DataConverter.py` 在規劃後呼叫
`DatasetConverter/stage.py:activate_stage_context`。
此前使用 `make_directory(path)`（`os.makedirs(exist_ok=True)`）
建立 `*_is_running_DataConverter`，同名目錄存在時仍可能開始寫入，
包含使用者正常 Ctrl+C 測試的遺留目錄。

本變更僅對 **Stage 1 的新 running 工作目錄**使用
`acquire_stage_directory_exclusive`：父目錄仍依既有 helper 建立，
葉目錄使用單次 `os.mkdir` 原子獨占。若既存、競爭者剛建立、
檔案、symlink、Windows junction 等同名項目存在則明確拒絕，
不得啟動 logger 或接續寫入。無刪除、搬移、覆寫或自動恢復。
失敗（包含 logger 初始化失敗）時保留現場供檢查。

所有測試只使用私人 `TemporaryDirectory`，驗證新目錄成功、
舊目錄含資料保留、空目錄／檔案／連結、雙執行緒競爭、
非法尾碼及記錄器失敗。無正式 WorkPool、SQLite、模型、GPU 動作。

```bash
python -m unittest -v tests.test_bl001_stage1_workspace_acquisition tests.test_dataset_stage_utils tests.test_data_converter_stage_plan tests.test_data_converter_entrypoint
```

本保護不宣稱能防止父路徑遭敵意替換、網路磁碟所有 race，
也不表示已完成實機正式 WorkPool 驗收。
