# BL-001：根流程階段函式的耗時紀錄歸屬

`TCFMain.py` 的 `DataConvert`、`RunClassfier`、`CombineTestResult`、
`TestResultVis`、`ArticleAnalysis` 過去使用 `exeTimeDict=dict()`
作為函式定義期的可變預設值。未明確提供字典的獨立呼叫會共享
同一個 Python dict，讓後續測試、重新進入或嵌入式觸發留下跨次耗時鍵。

本批改為 `exeTimeDict=None`，僅省略時每次新建
`{"start": time.time()}`。既有 `TCFMain.main` 會明確
建立並提供每次流程獨立的 `exeTimeDict`，其同一流程內的跨階段
累積耗時與命令字串、工作池交接、模型執行均不改變。
**明確傳入的 mapping 不複製也不補 start 欄位**，保留 caller 的
identity／責任與原有不完整參數失敗語意。

隔離測試透過原有無模型／無工作池的 root fake modules，
驗證五個公開階段 API 的預設值、不同獨立呼叫的 start 值、
ArticleAnalysis 同次共用／跨次隔離、明確提供 map 的原 identity，
以及既有 root command/stage ordering characterization。
未執行正式 WorkPool、模型、SQLite 或 GUI，不能視為實機驗收。
