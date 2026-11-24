# BL-001｜Stage 4 DataTable 頁碼正規化邊界

`BertScript/Test_result_Vis.py::table_update` 以前直接包含
「換每頁筆數後頁碼重設為 0」以及「依篩選後的剩餘資料筆數，
限制要求頁碼不得超過最後一頁」兩種狀態規則，並把可觀測的
頁碼與 one-based 頁碼顯示回傳給 Dash。

兩項規則現在集中於無任何 import 的
`BertScript.visualization_pagination.select_table_page`。
`table_update` 仍保留原 Dash 登錄、在重掛載時先
`PreventUpdate`、資料來源選擇、`Build_VisDatatable`
及回傳的 `{"page_current": page_current}`、
`page_current + 1`。唯一變更是透過純函式取得
適用頁碼，沒有修改 SQLite、Pandas、分類結果或 UI 元件架構。

原語意完整保留：0 筆資料視為 page 0；頁數上限
`max((row_count - 1) // page_size, 0)`；非正數的既有頁碼
落在 0；若來源按鈕為 `Page Size Bar` 先重設 0；
正常 user page 轉換仍保留原值；無效 `page_size=0`
依舊丟出除零例外而非隱式採新預設。

Windows/Ubuntu 的依賴輕量測試涵蓋頁數上下界、
篩選後縮減、換頁容量、空表、錯誤傳遞、
原 `table_update` 的 callback 布線與頁碼輸出。
實際 Windows Dash 排序、分頁、0 筆篩選與閒置
1 分鐘無回饋循環（KI-008）仍須獨立實機驗收。
