# 內網更新候選：BL-001 Stage-local SQLite 寫入重構

> **狀態：GitHub 重構候選，內網尚未部署／驗收。** 正式內網更新日期、版本與維護人員均需依實際部署後補記，不得以 CI 代替正式驗收。

## 變更與相容性

- `DatasetConverter/df_utils.py::dfToSQL` 和 `BertScript/df_utils.py::dfToSQL` 原本各自寫入相同的 `sampleSrc` SQLite 表（`if_exists='replace'`）並建立 `text_Index`。
- 現集中至 `text_category_profiler/data/stage_sql.py::write_stage_sql`；保留兩個 stage-local public `dfToSQL(SQLname, df, SavingDfColumns=[])` 入口、原有的選欄預設、固定 table/index 名稱與 DataFrame 原始 cell 行為。
- **2026-11-11 安全性增量（PR #240 已合併，內網待驗收）：** SQLite 可能將缺少欄位的 `CREATE INDEX ... ("text")` 接受為字串運算式索引，導致 `replace` 已刪除舊資料但 writer 仍回報成功。新候選在 `connect` 之前檢查最終選取欄位必含 `text`；否則明確 `ValueError`，不嘗試開啟或替換資料庫。**這是預期的 fail-closed 行為變更**，不代表已發生正式資料損失；詳見 `KI-011`。
- **刻意修正連線生命週期：** 原 stage-local 兩份實作執行完後未顯式 `close()`。現在在成功、欄位選取失敗、`DataFrame.to_sql` 失敗、索引建立失敗時，均透過 `finally` 關閉連線，並保留原始錯誤。不新增自動重試、schema 升級、JSON 正規化或新的結果表。
- 既有 canonical `text_category_profiler/data/df_utils.py::dfToSQL` 支援更多選項與 JSON 結構處理，**未整併**；`DB_utils`、分類模型、GUI/Jaal、WorkPool 命名狀態、索引慣例和資料類別均未變動。

## 已新增的驗證

- 檢驗兩個舊入口皆委派到共用 writer，且各自函式簽名和回傳值維持不變。
- 隔離 fake DataFrame/SQLite connection：固定 `sampleSrc` replace、`text_Index`、指定欄位、成功及三種異常路徑的連線關閉。
- 私有共享記憶體 SQLite + pandas：驗證兩個 stage 的中文字串資料與 `text_Index` 在關閉 writer connection 後仍存在。
- 新增私有 `TemporaryDirectory` **磁碟 SQLite** 驗證：兩個 stage 的重複 `replace`、關閉與重新開啟、`PRAGMA index_info` 真的指向 `text`；預設缺欄或選欄不含 `text` 時禁止連線，且既有 DB 位元組不變。此測試不碰正式檔案，不代表內網部署驗收。
- BL-001 完整套件清單與 canonical import audit 更新；原有 SQL、TSV、XLSX contract tests 仍應保持 PASS。
- 上述測試不代表真實磁碟 SQLite 交易、並行寫入、鎖定競爭、WorkPool、模型／GPU 的實機行為。

## 內網部署前驗收

> **PR #240 已由業主明確授權合併至 GitHub main；內網部署與實機驗收仍未完成。** 禁止為了測試而在正式資料上故意移除 text 欄位或執行 replace。

1. 確認更新時間與可回復版本，備份實際工作池資料；不在正式資料庫上直接做清除／replace 的測試。
2. 使用**隔離的測試工作池與 SQLite 檔案**，分別執行 DatasetConverter 和 BertScript `dfToSQL`；檢查資料列數、Unicode 文字、欄位、`sampleSrc` 與 `text_Index`。
3. 在測試資料庫刻意重複執行 replace，確認沒有 SQLite 檔案鎖定與新連線衝突；再實測異常後能否立即重開資料庫。
4. 驗證主流程／Stage handoff、Windows／Linux runtime，並確認最近一次內網成功的 pandas／sqlite3 依賴版本。
5. 若出現交易、索引、檔案鎖或資料差異，回退本次重構 commit，恢復原應用；不得自行改名正式 WorkPool 階段或在正式資料上重跑。

**完成狀態：** 只完成 BL-001 的一個可驗證小批次；不得宣稱整體重構、部署或實機驗收已完成。

## 不需模型／工作池的唯讀 SQLite schema 預檢（本批）

先**複製並停止寫入**的測試 SQLite 到獨立路徑，再從 repository root 執行：

```bash
python scripts/bl001_stage_sqlite_audit.py --db "path/to/copied-stage.sqlite3"
```

工具只檢查 `sampleSrc` 是否存在且包含 **精確** `text` 欄位、`text_Index` 是否唯一綁定該欄位，使用 `mode=ro&immutable=1` 且 `PRAGMA query_only=ON`；不讀取任何資料列、不執行 `CREATE/REPLACE/UPDATE`、不修復或轉移資料、不修改 WorkPool。輸出單行 JSON：`status=PASS/FAIL`、`issues`、欄位與索引 key 欄位，PASS exit 0、FAIL exit 1。缺檔、symlink、WAL／SHM／journal sidecar、SQLite 無法讀取與 schema 不符均 fail closed。

**重要限制：** 使用 SQLite immutable 會略過即時 journal/WAL 狀態；即使沒有 sidecar，也**不能**證明並行寫入安全，必須先建立已靜止的複本才能合理解讀結果。這只是 schema 確認，不會證明原始資料內容、交易 rollback／原子性、磁碟鎖、正式 Windows runtime 或分類成功。測試：`python -m unittest -v tests.test_bl001_stage_sqlite_audit`（私有 tempfile SQLite，無正式資料庫）。
