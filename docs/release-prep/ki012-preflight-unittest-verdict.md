# KI-012 私人快檢 unittest 結果防偽通過

原本子程序只要輸出中同時出現「Ran N tests」與某一行「OK」、且 exit code=0，就可能被視為通過，即使同一份輸出稍後又出現 FAIL 或不完整的結尾。

現在私有快檢的 `stage_contracts` 子程序必須在正常 exit 0 以外，同時符合：**恰好一個** `Ran N tests in ...` 摘要（N>0）、最後一行非空輸出為**完整單獨的** `OK`，不得出現 skipped 標記。任何其他終止結果均回報 `FAIL`，不會進行其後或真實模型驗收。

此功能只改變子程序結果解讀，沒有連接正式 SQLite/WorkPool，也不能代表真實模型、正式部署或完整 WorkPool 驗收已成功。