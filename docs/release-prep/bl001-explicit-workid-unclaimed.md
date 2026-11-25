# BL-001｜明確指定 Work-ID 必須成功認領

既有 `WorkPoolManager.acquire()` 在非空 `plan.work_id`
但沒有對應 incoming + pool 項目時，會**直接回傳**
`plan.work_id`。根流程可能因此繼續執行 stage，
在未取得 processing 工作單的前提下嘗試備份和交付。
上次 #348 已防止認領另一個工作單，但仍保留此漏洞。

本批將明確指定的 ID 由「不匹配也接受」調整為：
- 若成功比對 incoming 和 WorkPool 中**完全相同的 ID**，
  沿用原 no-replace Move，成功後才能回傳。
- 若找不到對應 ID，拋出固定
  `RuntimeError("EXTERNAL_WORK_ID_NOT_CLAIMED")`，
  不印「Found」成功訊息、不建立 Processing、不執行 Move。
- 未指定 ID 的自動選擇排序及其他現行行為不變；
  incoming 完全為空仍沿用現有 abort。
- 不將某個曾在 processing 出現的同名 ID 視為成功認領，
  **不實作 auto-resume**，也不自動清除或移動歷史資料。

此變更影響使用預先填寫 Work-ID、但未提供 incoming
認領證據的舊手動呼叫；這屬刻意的 fail-closed 行為，
正式排程／外部 caller 相容性仍待實機驗收。
