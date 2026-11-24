# BL-001｜明確指定 Work-ID 時不得認領另一工作單

當 `WeiTechworkID` 已由 caller 或設定提供，舊
`WorkPoolManager.acquire` 仍會倒序掃描 incoming 中的
可選 ID；如果有比指定 ID 更新的其他合格項目，可能將
**不同工作單**移到 Processing 並覆蓋回傳 ID。這違反
明確 ID 的語意，增加錯配備份／中斷追查風險。

本修正只修改選擇策略：
- 已指定非空 Work-ID 時，僅允許該字串的完全相等
  incoming 項目參與 WorkPool matching；不能移動其他工作單。
- 未指定時，保留原有倒序「最新候選」行為。
- 既有無可認領項目時的 preselected-ID fallback、
  缺少 incoming 候選時中止及工作單資料驗證時機均不變。
  **保留 fallback 不代表已驗證 preselected ID 的任務生命週期**。
- 不修改正在執行的正式 WorkPool、SQLite 或備份；不自動
  推論可 resume、清除 Processing 或任意修補資料夾。

隔離 Windows／Ubuntu 測試涵蓋未指定/指定 ID、最新與舊
工作單相衝突、指定 ID 缺席、Unicode ID 和非法 Windows
device alias 的 fail-before-I/O。正式多使用者／跨程序 claim
race 及原 preselected fallback 的實機設計仍待獨立驗收。

補充（#352）：上述舊 `preselected-ID fallback` 已由本次後續修正取消；若未從 incoming 成功認領指定 ID，現在明確 fail closed，而不是直接進入 Pipeline。詳見 `bl001-explicit-workid-unclaimed.md`。
