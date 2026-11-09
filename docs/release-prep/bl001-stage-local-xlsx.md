# 內網更新候選：BL-001 Stage-local Excel 共用輸出規則

> **狀態：候選重構，未部署。** 此文件供內網維護窗口評估與變更紀錄，不代表已實機驗收或更新正式環境。

## 修改

- 原本 `DatasetConverter/df_utils.py::dfToXLS` 與 `BertScript/df_utils.py::dfToXLS` 各保有同樣的 Excel 輸出選項；改為共用 `text_category_profiler/data/stage_xlsx.py::write_stage_xlsx`，避免兩份格式規則未來分歧。
- 原有兩個 public 入口及 `dfToXLS(df, OutputFN, excelindex=True, encoding='utf-8')` 簽名不變；舊 `encoding` 參數原本就不影響輸出，仍維持固定 UTF-8；`xlsxwriter` engine、index 參數與失敗時例外傳遞保持不變。
- 保留 `text_category_profiler/data/df_utils.py::dfToXLS` 自己的 ExcelWriter、工作表、大小檢查與 fallback 行為。**不**合併彼此不同的 API。
- 不修改分類結果、資料庫 schema、工作池目錄狀態、模型推論、推薦、Jaal 或完整 GUI。

## 已知限制與驗證

- 某些新版 pandas（例如 3.x）不再支援 `DataFrame.to_excel(encoding='utf-8')`；這是**原始實作即有的版本相容性問題**。本批只保留歷史行為，沒有將失敗偽裝為成功，也沒有宣稱已支援新版 pandas。
- 新增無模型／無外部服務的函式行為測試，核對兩個舊入口只呼叫共用 writer 一次、參數一致與錯誤直接傳播；選用真實 pandas 的測試會比對成功輸出的工作表內容，或確認既有失敗型別和訊息一致。
- 最新 PR-head CI、正式 Codex Review 與合併狀態應以相應 GitHub PR 為準。CI 通過不等同內網模型與本機 xlsxwriter/pandas 實測通過。

## 部署前檢查與回復

1. 在內網或離線測試機記錄 Python、pandas、xlsxwriter 版本，並確認舊版 XLSX 實際是否可寫入。
2. 使用**非正式／隔離資料**跑 DatasetConverter 與 BertScript 各一個 XLSX 範例，比對儲存格、欄位順序與 index；若原環境本就無法輸出，先列為相容性阻擋，不應因這次重構聲稱成功。
3. 維持既有 WorkPool 和模型資料不變；依維護窗口準備 git commit 回退點。遇格式或流程不一致時回退本 PR，不透過重新命名工作池階段來測試。

本批屬 BL-001 **局部去重**，後續仍需處理其他重複程式、動態/外部 callers 與完整實機驗收。
