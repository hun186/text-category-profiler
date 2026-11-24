# BL-001｜根流程中斷與失敗的最小階段來源註記

`PipelineOrchestrator` 以既有 port 順序調用
`convert → classify → combine → visualize → (SDSMS merge) → deliver`。
在分類或 stage 間交接失敗時，錯誤原本由上層傳遞，但單靠
例外型別不容易判斷在哪一個 port 中止；缺乏一個可供日後
恢復設計共用的、不暴露私有資料的階段識別碼。

此批以 `_run_named_stage` 輕量 boundary 包住每個 port。
當 port 拋出一般 `Exception` 時，在原**同一個例外物件**
上使用 Python 3.11+ `add_note` 附加一段有限枚舉：
`TCP_PIPELINE_FAILED_STAGE=<convert|classify|combine|visualize|merge|deliver>`。
既有 `__notes__` 若已有相同註記不重複增加；
不支援 `add_note` 的執行環境只保留原錯誤傳播。
`KeyboardInterrupt` 與 `SystemExit` 繼續按原語意向上傳播。

重要限制：
- 不捕捉後重啟、不吞錯、不改例外 type/identity、
  不將中斷當成功，也不從這個註記推論已完成進度。
- 註記不含檔名、Work-ID、索引、憑證、正文、參數或私有路徑。
- 不寫 checkpoint 或日誌檔；正式恢復需要獨立持久化與
  WorkPool／SQLite owner 來源證據，不能靠例外註記重跑。
- `test=False` 模式仍僅執行 convert + classify；
  非 SDSMS 不觸發 merge，失敗時下游 stage 均不執行。

以 6 個不同 stage 的 fault-injection 和原有主流程
characterization 在 Windows／Ubuntu 隔離 CI 驗證；
不操作正式 WorkPool、資料庫、GUI、GPU 或模型。
