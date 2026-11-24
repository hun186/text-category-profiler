# BL-001｜WorkPool 認領完成後的資訊通知是 Best-effort

`WorkPoolManager.acquire` 在外部 Work-ID 由 Incoming
不覆寫移至 Processing 後會呼叫傳入的 `info` callback。
舊版如果 log/console callback 出現例外，會把**已成功移動**
的 Work-ID 對上層回報為失敗。這時重試 acquisition
不會是安全的冪等操作；即使 WorkPool 有了內容也不能自動重跑。

此批僅在 non-idempotent move *完成後* 的資訊通知
捕捉一般 Exception。保持：
- move 失敗仍原樣傳遞，不能認列成功。
- move 成功時回傳原選定 ID，log 故障不會把結果改為失敗。
- 正常 log 收到與舊版相同的訊息。
- `KeyboardInterrupt` 不被轉成普通診斷故障。

此行為與「沒有成功認領不准進入 Pipeline」為不同契約；
**本次不自動找回或修補 Processing、也不掃正式 WorkPool**。
Hosted Win/Ubuntu 隔離測試驗證 callback 與 move 順序，
實際 log 權限與多程序競爭仍需後續驗收。
