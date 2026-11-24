# BL-001｜Stage 4 表格篩選語法解析模組邊界

`BertScript/Test_result_Vis.py` 原本在巨型 Dash composition entrypoint
直接定義 `to_string`、`operators`、`split_filter_part` 與
`construct_filter`，而 DataTable 篩選、圖表、表格多處直接依賴這些
函式。新增篩選功能若持續改大型 entrypoint，容易增加 GUI import
負擔及不必要的跨區域修改。

現在上述整段既有函式與常數**原樣搬到**
`BertScript/visualization_filter.py`。原 Stage 4 的同名符號透過
明確絕對匯入保留，Stage 4 內部 callback 與外部以
`Test_result_Vis.to_string` 等名稱取得的函式不需改寫。
這是 Stage 4 專屬邊界，沒有不適當地移入跨 stage 共用套件。
獨立 filter module 不匯入 Dash、pandas、WorkPool、模型或
其他執行 runtime。

相容測試使用無依賴 FakeDataFrame，涵蓋關係／邏輯／字串
運算、split_filter_part legacy alias、空 filter、contains、
datestartswith、整合複合 query 及主入口 import AST。
**刻意維持原有查詢字串與 dataframe 運算行為**，未擅自修改
pandas contains regex、篩選安全策略、GUI callback wiring、
SQLite/XLS 輸出、版面或 Stage 4 的執行狀態。
真實 Windows Dash 的 0 筆／非 0 筆篩選、分頁、排序、
靜置時的回呼迴圈（KI-008）仍需獨立驗收，
Hosted CI 通過不代表已做 UI E2E。

## Filter DataFrame application follow-up

後續將同一 Stage 4 區域中直接使用 `split_filter_part` 的
`df_upd_filter_query(df, filter_query)` **整函式原樣搬入**
`BertScript/visualization_filter.py`，並在大型 Stage 4
入口中以原名重新匯出。這讓 DataTable 字串語法、衍生查詢結構，
以及對既有 pandas-like DataFrame 的篩選套用，共同由同一個
Stage 4 模組持有；新功能可直接寫純函式回歸測試，不必載入 Dash。

現有 `ge/lt/eq/contains/datestartswith`、`&&`、
不明篩選運算子無動作以及原本 `.str.contains` 的 pandas
regex 預設行為皆**刻意維持不變**。不宣稱修復過濾語法注入、
複雜查詢效能或 KI-008 真實 GUI 的回饋迴圈；
Windows Dash 瀏覽器、資料庫與檔案輸出的 UAT 仍另外驗證。
