# BL-001｜外部 WorkPool 路徑必須成對設定

在根 `TCFMain.DataConvert`，舊版只有在
`WeiTechworkIDPath` 與 `WeiTechWorkPoolPATH`
都非空時才啟動外部 Work-ID acquisition。若操作人員
只填其中一個，分類會**靜默切到一般 Stage 1 執行**，
可能讓外部排程誤以為已認領工作單。

新增純字串驗證 `validate_external_workpool_path_pair`：
- 兩者皆空表示外部模式未啟用；一般 DataConvert 不變。
- 兩者皆非空表示可啟動外部 WorkPool（不代表目錄有效）。
- 僅一項設定、值不是字串時，報固定
  `EXTERNAL_WORKPOOL_PATH_PAIR_REQUIRED`。
- Root DataConvert 於 Stage 1 CMD 執行前檢查。
  WorkPoolManager 被直接呼叫時也要求完整啟用。
- DeliveryManager 只要指定了非空外部 Work-ID，
  交付前也要要求路徑成對且皆非空；
  **非 Work-ID** 的一般 cleanup 模式維持舊行為。

本批不更動 `build_pipeline_plan` 以免將原本單獨供
`WeiTechFormatInputPATH` 或測試用的 CLI plan 
路徑範例誤判；真正 WorkPool 進入點在 runtime
各自檢查。這是設定契約，不是實體路徑 ACL、
liveness 或安全 resume 的保證。

Hosted Windows／Ubuntu 隔離測試證明單側路徑
不會產生 Stage 1 CMD 或備份副作用；正式排程
與手動 caller 的相容性仍待實機驗收。
