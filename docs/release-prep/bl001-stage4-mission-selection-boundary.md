# BL-001｜Stage 4 MissionTable 互動與純資料映射邊界

原始 `BertScript/Test_result_Vis.py::MissionTableSelection`
同時負責 Dash callback registration/logging 及 MissionTable
`Topics` → ColorTable `selected_rows` 的選取計算。
後者已抽到 `BertScript/visualization_mission_selection.py`
的 `mission_colortable_rows`，只使用 Python stdlib `ast.literal_eval`。

保留原本的語意：從 `derived_virtual_selected_rows` 取得目前
可見的 Mission 列、解析 `Topics` literal list、排序標籤，
逐一比對 `Colortable_data` 的 `Label`，回傳可能重複的 row
indices；None／空選擇回傳空陣列，錯誤格式與無效索引繼續
傳出原錯誤。**不偷換為 set、dedupe、非字面 eval、regex
或模糊字串比對**，以免舊 GUI 出現可觀測行為差異。

原 Dashboard 保留 `MissionTableSelection` callback 名稱、
裝飾器輸出、輸入與選取事件 logging；只把資料映射
委派給純函式。隔離測試包括未排序／重複標籤、大小寫、
無選擇、惡意 Topics 字串不執行、AST callback extraction
以及 Windows/Ubuntu 依賴輕量 CI。

未登入/啟動真實 Dash 瀏覽器，不能因此關閉 KI-008，
也不接觸模型、正式 SQLite 或 WorkPool。
