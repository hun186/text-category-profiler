# 內網更新候選：BL-001 Stage-local SQLite 寫入重構

> **狀態：GitHub 重構候選，內網尚未部署／驗收。** 正式內網更新日期、版本與維護人員均需依實際部署後補記，不得以 CI 代替正式驗收。

## 變更與相容性

- `DatasetConverter/df_utils.py::dfToSQL` 和 `BertScript/df_utils.py::dfToSQL` 原本各自寫入相同的 `sampleSrc` SQLite 表（`if_exists='replace'`）並建立 `text_Index`。
- 現集中至 `text_category_profiler/data/stage_sql.py::write_stage_sql`；保留兩個 stage-local public `dfToSQL(SQLname, df, SavingDfColumns=[])` 入口、原有的選欄預設、固定 table/index 名稱與 DataFrame 原始 cell 行為。
- **刻意修正連線生命週期：** 原 stage-local 兩份實作執行完後未顯式 `close()`。現在在成功、欄位選取失敗、`DataFrame.to_sql` 失敗、索引建立失敗時，均透過 `finally` 關閉連線，並保留原始錯誤。不新增自動重試、schema 升級、JSON 正規化或新的結果表。
- 既有 canonical `text_category_profiler/data/df_utils.py::dfToSQL` 支援更多選項與 JSON 結構處理，**未整併**；`DB_utils`、分類模型、GUI/Jaal、WorkPool 命名狀態、索引慣例和資料類別均未變動。

## 已新增的驗證

- 檢驗兩個舊入口皆委派到共用 writer，且各自函式簽名和回傳值維持不變。
- 隔離 fake DataFrame/SQLite connection：固定 `sampleSrc` replace、`text_Index`、指定欄位、成功及三種異常路徑的連線關閉。
- 私有共享記憶體 SQLite + pandas：驗證兩個 stage 的中文字串資料與 `text_Index` 在關閉 writer connection 後仍存在。
- BL-001 完整套件清單與 canonical import audit 更新；原有 SQL、TSV、XLSX contract tests 仍應保持 PASS。
- 上述測試不代表真實磁碟 SQLite 交易、並行寫入、鎖定競爭、WorkPool、模型／GPU 的實機行為。

## 內網部署前驗收

1. 確認更新時間與可回復版本，備份實際工作池資料；不在正式資料庫上直接做清除／replace 的測試。
2. 使用**隔離的測試工作池與 SQLite 檔案**，分別執行 DatasetConverter 和 BertScript `dfToSQL`；檢查資料列數、Unicode 文字、欄位、`sampleSrc` 與 `text_Index`。
3. 在測試資料庫刻意重複執行 replace，確認沒有 SQLite 檔案鎖定與新連線衝突；再實測異常後能否立即重開資料庫。
4. 驗證主流程／Stage handoff、Windows／Linux runtime，並確認最近一次內網成功的 pandas／sqlite3 依賴版本。
5. 若出現交易、索引、檔案鎖或資料差異，回退本次重構 commit，恢復原應用；不得自行改名正式 WorkPool 階段或在正式資料上重跑。

**完成狀態：** 只完成 BL-001 的一個可驗證小批次；不得宣稱整體重構、部署或實機驗收已完成。
