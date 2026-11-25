# BL-001｜外部 Work-ID 完成移交失敗不得假報完成

原 `DeliveryManager.backup_and_complete()` 在將外部工作單從
`AutoBertClassify_Processing` 搬到 `AutoBertClassify_Processed` 時，
以 `except Exception: reporter(error)` 吞掉搬移錯誤；而且在**尚未搬移前**
就記錄 `Complete ...`。若目的地已存在（包括使用者正常 Ctrl+C 留下的目錄），
可能出現工作單仍停在 Processing，根流程卻沒有收到失敗訊號。

此次修正：**只有移交成功才記錄 Complete**；搬移失敗時，
先向原有 `move_error_reporter` 回報，隨後重新拋出原例外，
使根流程無法誤判成功。若報錯 callback 本身失敗，仍保留搬移原錯誤。
搬移成功以後的單純紀錄器失敗，只回報、不再重試或重搬同一工作單，
避免反覆操作已提交的移交。

保持既有備份與 `SDSMS` 輸出格式不變。後續目的地預檢會在備份前拒絕已存在的 Completed 工作單；備份仍先於最後移交：
若最後移交失敗，可能已有備份產物，這不是跨備份與搬移的原子交易；
本 PR **不執行清理、補償性移動或自動恢復**。

```bash
python -m unittest -v tests.test_bl001_delivery_completion_fail_closed tests.test_workpool_manager tests.test_bl001_external_workitem_move_no_overwrite
```

所有新增案例使用私有 TemporaryDirectory 或 RecordingFileSystem
測試成功、既存 Completed、報錯器故障、成功後寫 Log 故障、
備份失敗與無 Work-ID。正式 WorkPool／模型／SQLite／實機磁碟
尚未驗證，GitHub CI 不等同正式部署驗收。
