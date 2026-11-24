# BL-001｜Stage 4 DataTable 派生篩選狀態恢復

Dash 在重新掛載 `VisDatatable` 時，可能暫時把
`derived_filter_query_structure` 設成 `None`，
但原來的 `filter_query` 文字仍在。既有
`FilteredDF_update` 必須先反序列化上次解析結構，
在原文字不空且目前解析結構為 `None` 時恢復，
才能由重複事件 guard 辨認這只是同一個查詢的重掛載。

此邏輯現集中到 `BertScript/visualization_callback_state.py` 的
`restore_derived_query_state`，並由既有
`visualization_stage` facade 匯出。
函式使用注入的 `loads=json.loads`，因此 callback policy
模組保持無任何重依賴 import，原 callback 也保留
**先反序列化、後讀取/log/匯出** 的順序。

保留既有語意：
- 非空文字查詢且當前派生結構為 `None`，使用上次結構。
- 當前派生結構非 `None`，優先保留它的 object identity。
- 文字查詢為空時不從舊結構還原。
- 舊 JSON 始終先解析，格式不合法仍明確拋出例外，
  不把它誤判成正常查詢後繼續輸出檔案。
- 兩個狀態值返回給原 callback，後續相同事件抑制與 revision
  更新、輸出及頁面 callback 連線均不變。

新增 Windows/Ubuntu 隔離測試與既有
`FilteredDF_update` 不觸發磁碟輸出 guard 測試。
這不能代替 KI-008 的 Windows/Dash 實機閒置、
0 筆／非 0 筆篩選、排序、分頁及長時間回饋迴圈驗收。
