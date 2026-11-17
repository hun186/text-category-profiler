# KI-012 根程式自檢結果：只允許唯一的終端 FINAL: PASS

`run-bl001-sqlite-release-preflight.bat` 的 `root_isolated`／`root_real_opt_in` 依賴 `TCFMain.py --self-test` 的文字輸出。根自檢程式在最後一行輸出 `FINAL: PASS` 或 `FINAL: FAIL`。

原本解析方式只要在輸出任意位置找到 `FINAL: PASS`，即使稍後有 `FINAL: FAIL` 或額外錯誤行、且子程序錯誤回傳 exit 0，仍可能判定成功。現在要求**唯一一筆** `FINAL:` 終局結果，且必須是最後一行非空輸出，內容精確為 `FINAL: PASS`；否則立即回報 `FAIL`，不放行後續真實模型自檢。

只有根程式本身完成這項自檢，不代表已在正式 WorkPool、Windows 主機或網路磁碟通過驗收。

## 成功標記的輸出來源（新增檢查）

根自檢的 `FINAL: PASS` 必須出現在 **stdout**，且為唯一、最後的非空行；
**stderr 必須為空**。僅在 stderr 印出 `FINAL: PASS`、stdout 印出失敗或
不完整內容、或 stdout 雖然通過但 stderr 仍有其他輸出，一律判為
`FAIL`。即使子程序退出碼為 0，也不會放行後續的 `root_real_opt_in`。

此限制僅套用於 `TCFMain.py --self-test` 的根自檢；`unittest` 的
標準輸出位置及既有私人檢查的成功格式維持原狀。這是輸出契約驗證，
不代表已完成正式 WorkPool 或實機部署驗收。
