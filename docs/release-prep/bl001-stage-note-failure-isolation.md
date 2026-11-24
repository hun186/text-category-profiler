# BL-001｜根流程 Stage Error 診斷失敗不得掩蓋原始錯誤

既有 `PipelineOrchestrator._run_named_stage` 為每個 Stage 的
`Exception` 加上不含私有資訊的 `TCP_PIPELINE_FAILED_STAGE`
例外註記。然而 Python 允許 exception subclass 覆寫
`add_note` 或 `__notes__`，若診斷函式自身拋錯，
就有機會替換掉真正的 Stage 失敗原因。

本批將 `getattr/__notes__/add_note` 註記區塊明確包在
不影響原始錯誤傳播的 `try/except Exception` 中：
- 原有例外**型別／物件身分**皆不變。
- 正常 `add_note` 仍會寫入一次 bounded Stage 名稱。
- 註記本身失敗時跳過記錄，讓原 Stage 原樣拋出；
  不印出 private exception 原文、不寫磁碟、不做 cleanup。
- `KeyboardInterrupt` 等 `BaseException` 不會被轉換成
  一般 Stage 錯誤，仍照原行為上傳。

Windows／Ubuntu 使用故障注入、舊 stage sequencing
及原始例外身分測試驗證。**這不是持久化 checkpoint、
自動恢復、異常吞噬或正式部署驗收。**
