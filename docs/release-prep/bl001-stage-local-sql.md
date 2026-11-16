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

工具只檢查 `sampleSrc` 是否存在且包含 **精確** `text` 欄位、`text_Index` 是否只綁定該欄位且是原始 `CREATE INDEX` 的非唯一、非 partial、升冪 BINARY 索引（不是同鍵的 UNIQUE、partial、DESC、NOCASE 變體），使用 `mode=ro&immutable=1` 且 `PRAGMA query_only=ON`；不讀取任何資料列、不執行 `CREATE/REPLACE/UPDATE`、不修復或轉移資料、不修改 WorkPool。輸出單行 JSON：`status=PASS/FAIL`、`issues`、欄位與索引 key 欄位，PASS exit 0、FAIL exit 1。缺檔、symlink、WAL／SHM／journal sidecar、SQLite 無法讀取與 schema 不符均 fail closed。

**重要限制：** 使用 SQLite immutable 會略過即時 journal/WAL 狀態；即使沒有 sidecar，也**不能**證明並行寫入安全，必須先建立已靜止的複本才能合理解讀結果。這只是 schema 確認，不會證明原始資料內容、交易 rollback／原子性、磁碟鎖、正式 Windows runtime 或分類成功。測試：`python -m unittest -v tests.test_bl001_stage_sqlite_audit`（私有 tempfile SQLite，無正式資料庫）。

## Windows 跨程序檔案鎖與持鎖程序中斷快檢（私人測試檔）

更新含 `run-bl001-sqlite-lock-check.bat` 的 GitHub 版本後，在平常使用的 Windows Anaconda Prompt、repository root 直接執行：

```bat
run-bl001-sqlite-lock-check.bat
```

跨平台等價命令：`python -m scripts.bl001_stage_sqlite_lock_acceptance`；回歸測試：`python -m unittest -v tests.test_bl001_stage_sqlite_lock_acceptance`。

這個 CLI **不提供 `--db` / WorkPool / 輸出路徑參數**；它只在 `tempfile.TemporaryDirectory` 建立測試用 SQLite，透過現行 `data.stage_sql.write_stage_sql` 寫入 Unicode 資料、`sampleSrc` 及 `text_Index`。子程序執行 `BEGIN EXCLUSIVE` 真正持鎖，驗證寫入被拒絕，接著先正常釋鎖，再測一次強制終止持鎖子程序，於新連線核對未被覆寫的資料與原生 text 索引，最後驗證重試成功與 SQLite integrity_check。測試絕不讀寫正式 WorkPool／外部 DB、也不改工作池階段狀態。

`status=PASS` 僅證明該機器的**私人 SQLite 跨程序鎖拒絕與釋鎖後重試**運作正常。`status=FAIL` 或 `BLOCKED_DEPENDENCY` 不可視為通過。此測試**不是**在 `to_sql(replace)` 與 `CREATE INDEX` 之間終止**寫入程序**，不能據此保證整段 writer 的交易原子性或生產資料中斷恢復；也不證明正式 WorkPool 的多工作者競爭、Windows 網路磁碟鎖或長時間穩定性。若要驗證這些高風險情境，須另以隔離的完整測試工作池及失敗注入設計，不能拿正式 SQLite 做破壞測試。

**2026-11-16 已收到的 Windows 實機證據：** pandas 2.0.1／xlsxwriter 3.1.9 下 Stage writer 快檢 39/39 PASS；`TCFMain.py --self-test isolated` 10 PASS；`TCFMain.py --self-test real -p 8050` 7 PASS、1 CPU WARN、0 FAIL，模型和 FixedTest 均 unchanged，`_rdy_for_Spike=1`。Jaal／歷史預覽畫面及 Stage 4 篩選由使用者回報正常。**2026-11-16 跨程序鎖工具 Windows 實測 PASS：** 五項 `initial_write_and_index`、`graceful_unlock_rejects_write_and_preserves_rows`、`graceful_unlock_retry_and_index`、`terminated_lock_holder_rejects_write_and_preserves_rows`、`terminated_lock_holder_retry_and_index` 均 PASS；JSON `scope=private_tempfile_only_no_workpool`。這僅代表在該 Windows/Anaconda 環境、該私人資料庫的鎖拒絕與重試通過，不能視為寫入程序異常終止的原子性保證。


## 下一項：寫入程序在 replace 與索引之間終止（獨立高風險診斷）

**前置事實**：共享 Stage-local writer 先呼叫 pandas `to_sql(name="sampleSrc", if_exists="replace")`，然後才執行 `CREATE INDEX "text_Index" ...`，兩步間沒有應用層原子事務保障。在開發隔離環境中，使用同一寫入順序於替換之後故意中斷，可觀察到新的表資料已提交，但 `text_Index` 缺失，`PRAGMA integrity_check` 仍是 `ok`。**這不是正式資料損壞報告，更不代表使用者 Windows 已執行此新測試**。

新增可選診斷：`run-bl001-sqlite-atomicity-probe.bat`（或 `python -m scripts.bl001_stage_sqlite_atomicity_probe`）。工具**沒有 `--db` 或正式 WorkPool 輸入參數**；只使用新建私人臨時資料庫。它先寫入原始資料及原生 `text_Index`，在真正的子程序用現有 `write_stage_sql` 更新，當子程序正要執行 `CREATE INDEX` 時先寫入同步標記並暫停。母程序確認子程序仍存活後強制終止它，然後以新 SQLite 連線檢查原始資料是否保全、是否留下部分更新、索引是否保全與 SQLite integrity。

- `status=PASS_ATOMICITY`／exit 0：僅這個中斷點保全原始資料及索引。
- `status=FAIL_ATOMICITY`／exit 1：已觀察到部分寫入狀態；這是診斷發現的問題，**不是**診斷工具本身失靈。
- `status=BLOCKED_DIAGNOSTIC`／exit 1：測試環境或子程序啟動未能提供有效診斷。

回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_atomicity_probe` 只保證診斷正確分類、安全隔離及禁止外部 DB 參數；即使診斷回報 `FAIL_ATOMICITY`，回歸可以 PASS，**不能拿測試套件綠燈宣稱 writer 已原子化**。高風險 writer 重構、交易回復／備援設計與各平台進一步驗收須另行處理；不得用正式資料執行中斷注入。
