# BL-001｜Legacy 動態載入程式碼的靜態證據

現有 legacy caller audit 已包含直接 AST import、裸名稱
import 候選與 literal path hint，但 `importlib.import_module`、
`__import__`、`runpy.run_module`、`runpy.run_path`
等動態載入呼叫的證據未依呼叫點清楚區分。

本批在原
`python -m scripts.bl001_legacy_root_audit --output <private-report.json>`
報告中加入 `dynamic_loader_callsites`，保留原有欄位：
- 指向 8 個 manifest 相容入口的 **字串常量實參**，僅標示
  `known_legacy_literal`、來源檔名/行號/loader 與明確 legacy target。
- 計算式、未提供字串常量或其他未知第一實參，標示
  `computed_or_missing_argument` 且 `target=null`。
- 其他正常第三方或 stdlib 固定字串載入不作 legacy 命中。
- 純 AST，不 import / runpy 執行 legacy code、模型或服務；
  不輸出計算後的動態實參、Private Work-ID 或檔案正文。

這是 **候選證據**，不是完整呼叫圖：名稱被其他程式碼遮蔽、
import aliases、sys.path、外部腳本、動態拼接和手動 caller
皆無法由靜態掃描確認。原報告新增
`external_dynamic_callers_verified=false`，即使全部無命中
也不能宣稱 8 個 legacy 入口沒有外部使用者，更不能授權刪除。

Windows/Ubuntu 隔離測試涵蓋已知 manifest literal、
未解計算式、普通 stdlib import、字串看似路徑但並非載入、
語法錯誤及不實際執行任何 loader；保留原始 Git blob audit。
