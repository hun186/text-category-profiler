# 內網更新候選：BL-001 Stage-local Excel 共用輸出規則

> **狀態：候選重構，未部署。** 此文件供內網維護窗口評估與變更紀錄，不代表已實機驗收或更新正式環境。

## 修改

- 原本 `DatasetConverter/df_utils.py::dfToXLS` 與 `BertScript/df_utils.py::dfToXLS` 各保有同樣的 Excel 輸出選項；改為共用 `text_category_profiler/data/stage_xlsx.py::write_stage_xlsx`，避免兩份格式規則未來分歧。
- 原有兩個 public 入口及 `dfToXLS(df, OutputFN, excelindex=True, encoding='utf-8')` 簽名不變；舊 `encoding` 參數原本就不影響輸出，仍維持固定 UTF-8；`xlsxwriter` engine、index 參數與失敗時例外傳遞保持不變；新版 pandas 不再接受的 `to_excel(encoding=...)` 參數依實際方法簽名省略，舊版或接受 `**kwargs` 的實作維持原本固定 UTF-8 傳參。
- 保留 `text_category_profiler/data/df_utils.py::dfToXLS` 自己的 ExcelWriter、工作表、大小檢查與 fallback 行為。**不**合併彼此不同的 API。
- 不修改分類結果、資料庫 schema、工作池目錄狀態、模型推論、推薦、Jaal 或完整 GUI。

## 已知限制與驗證

- 新版 pandas（例如 2.x/3.x）移除了 `DataFrame.to_excel(encoding=...)`；本批改為**只在方法簽名明確不接受該參數時省略**，不重新選擇 engine、格式、欄位順序或索引設定。未知或不可檢查的自訂 writer 保留舊呼叫；若寫入失敗，不根據 TypeError 訊息重試，避免部分建立檔案後重複寫入。
- 新增無模型／無外部服務的函式行為測試，核對兩個舊入口只呼叫共用 writer 一次、參數一致與錯誤直接傳播；選用真實 pandas + xlsxwriter 的測試會比對成功輸出的工作表 XML；此外以顯式新舊方法簽名的 frame double 驗證只寫一次、保留例外。
- 最新 PR-head CI、正式 Codex Review 與合併狀態應以相應 GitHub PR 為準。CI 通過不等同內網模型與本機 xlsxwriter/pandas 實測通過。

## 部署前檢查與回復

1. 在內網或離線測試機記錄 Python、pandas、xlsxwriter 版本，並確認舊版 XLSX 實際是否可寫入。
2. 使用**非正式／隔離資料**跑 DatasetConverter 與 BertScript 各一個 XLSX 範例，比對儲存格、欄位順序與 index；若原環境仍因套件或文件鎖定無法輸出，應列為內網驗收阻擋，不得因 Hosted 測試成功就聲稱修復。
3. 維持既有 WorkPool 和模型資料不變；依維護窗口準備 git commit 回退點。遇格式或流程不一致時回退本 PR，不透過重新命名工作池階段來測試。

本批屬 BL-001 **局部去重**，後續仍需處理其他重複程式、動態/外部 callers 與完整實機驗收。
