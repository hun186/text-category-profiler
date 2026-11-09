# 內網更新候選：BL-001 Stage-local TSV 共用輸出規則

> **狀態：程式重構候選。** 這份文件不是內網已部署或已實機驗收的聲明。
> 發行日期、內網部署版號與實際上線紀錄，需待部署人員驗收後填入。

## 更新摘要

- 合併 `DatasetConverter/df_utils.py::dfToTSV` 與 `BertScript/df_utils.py::dfToTSV` 原本相同的格式邏輯，改由 `text_category_profiler/data/stage_tsv.py::write_stage_tsv` 集中管理。
- 兩個舊入口、`dfToTSV(df, OutputFN)` 呼叫形式與回傳 `None` 不變。
- 沿用原格式：UTF-8、TAB 分隔、無表頭／index、`csv.QUOTE_NONE`、反斜線 escape；不更動資料欄位順序與模型參數。
- **未**重新導向 `text_category_profiler/data/df_utils.py::dfToTSV`：它含多程序資源探測與擴充參數，不能視為完全相容。
- 未修改分類器、推薦／可視化 UI、Jaal、WorkPool 命名狀態、資料庫 schema 或部署檔。

## 驗證與發行條件

- 新增針對共用格式、兩個 legacy wrapper、單次寫入、例外透傳及選用真實 pandas 的行為等值測試：當 pandas 支援歷史格式時，比對 TSV 位元組；當 pandas 3.x 不接受空 `quotechar` 時，驗證新舊呼叫皆回報相同例外，不把既有相容性問題誤判為新功能成功。
- 保留舊的 `tests.test_bl001_df_tsv_provider_contracts`；正式版本必須再通過最新 HEAD 的 Hosted CI 與零未解決問題的 Codex Review。
- **已知限制：** 某些 pandas 3.x 版本（Review 已確認 3.1.1）對既有 `quotechar=""` 會擲出 `TypeError`；本次重構刻意不改變此歷史格式與失敗行為。更新內網前必須先核對當地 pandas 版本並在非正式資料上驗證 TSV 匯出，不可將 Hosted PASS 當作 pandas 3 相容性認證。未來如需支援 pandas 3，須另做有金標 TSV 比對的兼容修正。
- 本地部署前，依既有實務流程備份重要資料、確認維護窗口與回復點；先在隔離資料集比較 TSV 檔案 checksum 與關鍵欄位，再重啟完整分類流程。
- 內網仍需驗收 Windows／Linux 實機所需依賴與現有 CLI；Hosted 單元測試 **不等於** 已更新內網。
- 回復策略：若 stage TSV 實測不相容，回退到這次重構前的應用 commit；不得透過改名 WorkPool 目錄強迫重新分類。

## 未包含在此批次

- BL-001 其餘 `df_utils`／`MP_utils`／`utilities` 去重與跨 stage 行為整併。
- 原版 Stage 4 GUI、Jaal 結構檢視器、已儲存結果預覽功能擴充。
- 真實模型／GPU／WorkPool 端到端驗收，仍由現有 KI-003／KI-008／KI-009 等工作記錄追蹤。

這項修改屬於**有限的 BL-001 重構增量**，不代表 BL-001 全部完成，也不應因為這個 PR 自動發布內網版本。
