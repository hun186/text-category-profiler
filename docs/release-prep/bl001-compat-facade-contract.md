# BL-001｜8 個 Legacy 相容入口的結構邊界

目前 `text_category_profiler/` 有 13 筆 legacy manifest 資產：
**8 個相容入口、4 個 vendor 資產及 1 個 package marker**。
8 個相容入口仍保留公開函式、惰性轉送或舊 CLI 呼叫方式，
因為 external、動態及人工 script caller 尚未完成確認。

此批建立純 AST 工具
`python -m scripts.bl001_compat_facade_contract --output <private-report.json>`，
以 legacy inventory 為 scope，逐一檢查 8 個入口的原
compatibility function 定義清單、canonical target 存在、
限定的依賴來源及明顯的 `sys.path` 改寫、`os.chdir`。
出現新 class、非允許的 business function、缺少既有入口或
新增未核實的 heavy import 時 CI 必須失敗，避免將新功能
塞回舊的相容層。

原始 `ArtCluESJobTemplate.py` 的 `run_path`
會在載入時計算模板字典，屬已存在的特殊相容政策；
本次不擅自替換或宣稱所有 legacy import 都沒有副作用。
此 AST gate 也不是任意 Python 程式的完整形式驗證，無法
排除隱藏的動態行為。既有 `bl001_package_census` 與
`bl001_legacy_root_audit` 仍另外驗證 Git blob/path identity。

**報告即使 PASS 也固定 `facade_removal_authorized=false`、
`external_callers_verified=false` 與
`runtime_verified=false`。** 合併本次 CI 不能用來刪除
13 個 legacy 資產，也不能取代外部 Win/Linux 工具、
CLI、歷史 deployment snapshot 的使用盤點。
