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

**前置事實**：共享 Stage-local writer 先呼叫 pandas `to_sql(name="sampleSrc", if_exists="replace")`，然後才執行 `CREATE INDEX "text_Index" ...`，兩步間沒有應用層原子事務保障。在開發隔離環境中，使用同一寫入順序於替換之後故意中斷，可觀察到新的表資料已提交，但 `text_Index` 缺失，`PRAGMA integrity_check` 仍是 `ok`。**2026-11-16 Windows/Anaconda 已用私人 tempfile 實測重現相同結果**：`status=FAIL_ATOMICITY`、`original_preserved=false`、`new_partial_rows_present=true`、`text_index_present=false`、`integrity_check=ok`。這不是正式 WorkPool 已受損的證據。

新增可選診斷：`run-bl001-sqlite-atomicity-probe.bat`（或 `python -m scripts.bl001_stage_sqlite_atomicity_probe`）。工具**沒有 `--db` 或正式 WorkPool 輸入參數**；只使用新建私人臨時資料庫。它先寫入原始資料及原生 `text_Index`，在真正的子程序用現有 `write_stage_sql` 更新，當子程序正要執行 `CREATE INDEX` 時先寫入同步標記並暫停。母程序確認子程序仍存活後強制終止它，然後以新 SQLite 連線檢查原始資料是否保全、是否留下部分更新、索引是否保全與 SQLite integrity。

- `status=PASS_ATOMICITY`／exit 0：僅這個中斷點保全原始資料及索引。
- `status=FAIL_ATOMICITY`／exit 1：已觀察到部分寫入狀態；這是診斷發現的問題，**不是**診斷工具本身失靈。
- `status=BLOCKED_DIAGNOSTIC`／exit 1：測試環境或子程序啟動未能提供有效診斷。

回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_atomicity_probe` 只保證診斷正確分類、安全隔離及禁止外部 DB 參數；即使診斷回報 `FAIL_ATOMICITY`，回歸可以 PASS，**不能拿測試套件綠燈宣稱 writer 已原子化**。高風險 writer 重構、交易回復／備援設計與各平台進一步驗收須另行處理；不得用正式資料執行中斷注入。

## 原子替換可行性研究（**測試原型，未改正式 writer**）

- 採「先備妥候選表，後交易切換」：在私有 SQLite 用 pandas `to_sql` 寫入候選表（此階段不更動既有 `sampleSrc`）；再以 `BEGIN IMMEDIATE` 包住 `DROP TABLE sampleSrc`、`ALTER TABLE candidate RENAME TO sampleSrc`、`CREATE INDEX text_Index`，最後 `COMMIT`。在 index 之前故意 `ROLLBACK` 時，舊表資料與原索引會留下，SQLite DDL 於單一交易內可回滾。這不等於直接在現有 `pandas.to_sql(if_exists='replace')` 外面加 `BEGIN`；pandas 對原生 sqlite3 的內部 commit 行為須另外處理。
- **相容性阻擋**：pandas 依寫入的表名產生輔助索引（例如正式表的 `ix_sampleSrc_index` 與候選表的 `ix___bl001_candidate_index`）；直接改名候選表不會自動將該索引重新命名。成功切換後雖有 `text_Index`，但額外索引名稱仍不同。若工作池工具或舊 caller 依賴它，可能不相容。包含 named index／MultiIndex 的情況亦待證實。
- **故障清理阻擋**：pandas 準備候選表的交易可能先完成，因此寫入程序在正式切換前死亡，可能留下僅供候選的孤兒資料表。不能在未辨識活動程序或與其他 worker 協調的情況下任意刪除。
- **其他驗收**：需要涵蓋正式表以外的 schema／views／FK，外部與並行 caller、資料及索引完全等價；在私人暫存 DB 上多個注入點測試，然後使用者 Windows/Anaconda 實測與完整 WorkPool 隔離測試。測試原型 `python -m unittest -v tests.test_bl001_stage_sql_shadow_feasibility` 僅確認回滾特性及索引名差異，**不能用其 PASS 宣稱正式 writer 修復**。
- 這批只記錄實機缺口與設計可行性；正式 Stage-local writer、公開 API、真實資料及 WorkPool 均**維持不變**，KI-012 繼續 Open。

## KI-012 原子式 SQLite writer 修正候選（Windows／WorkPool 尚待驗收）

- **2026-11-16 實機證據**：修正前 Windows `run-bl001-sqlite-atomicity-probe.bat` 報 `FAIL_ATOMICITY`，舊資料未保留、新資料已可見、`text_Index` 不存在但 `integrity_check=ok`。只在私人 tempfile 重現，未見正式 WorkPool 損壞。
- **根因**：原生 sqlite3 pandas `to_sql(if_exists="replace")` 可能自行提交，接續的 `CREATE INDEX text_Index` 尚未執行時若程序死亡，原表已被替換。
- **修正**：新 `stage_sql.write_stage_sql` 在相同 SQLite DB 裡先寫入唯一候選表 `__bl001_stage_<uuid>`（pandas 仍可自行 commit）；候選表成功後，於 `BEGIN IMMEDIATE` 下依序刪除舊 `sampleSrc`、依候選表 DDL 重建同名正式表、在交易內 `INSERT ... SELECT` 複製候選列、依實際 `PRAGMA index_xinfo` 恢復預設／具名／MultiIndex 的 `ix_sampleSrc_*` 索引，建立 `text_Index`、在交易內刪除自己的候選表，最後同一 `COMMIT`。建立過程拋錯則 rollback 回原表；不改兩個 stage-local public `dfToSQL` 入口與 canonical 其他 writer。
- **相容限制**：未知／不支援的 pandas 候選索引在替換原表前拒絕；不會對正式 `sampleSrc` 進行自動修復。成功輸出依 `PRAGMA` 驗證索引的欄位、順序、類型，SQL 建表／建索引的字串空白格式可能與原版不同但語意相同。特別針對依賴 `sampleSrc` 的既有 SQLite View 增加回歸測試；直接 `ALTER TABLE ... RENAME` 的方案在這種 View 下會失敗，因此改為單一交易內建立同名表並複製列。這增加至少一次完整資料複製 I/O，需要獨立評估大工作量與磁碟空間。
- **未完成風險**：候選表先提交，程序若在切換前／切換期間突然死亡，可能留下獨立 `__bl001_stage_*` 孤兒表；不能自動刪除其他工作者可能正在操作的候選表。多工作者、網路磁碟、磁碟容量、較大批次、正式 WorkPool 專屬條件尚未驗收。
- **一鍵 Windows 私人驗收**：從 GitHub 更新修正版本，在原 Anaconda Prompt 的 repo 根執行 `run-bl001-sqlite-atomic-fix-check.bat`。這會測真實 pandas SQLite index/schema 等價、多個 DDL 注入失敗回滾、以子程序真正中斷 writer（預期 `PASS_ATOMICITY`）、跨程序鎖與解鎖重試；最後應為 `STATUS=PASS_KI012_PRIVATE`。若任何 FAIL，不得拿新版本處理正式 WorkPool。原版資料保全證據不等於本版 Windows 驗收。
- **部署 Gate**：Hosted CI／正式 Review、使用者 Windows 私人一鍵測試均通過、既有 `TCFMain.py --self-test isolated`／`--self-test real -p 8050` 復測及正式 WorkPool 備份確認後，才可討論內網實際部署；`KI-012` 仍先保持 Open／待 Windows UAT。

## KI-012 多程序交錯寫入與候選表殘留（私人 Windows 驗收候選）

原子式 Stage-local writer 已於 PR #260 合併 main；但原版 `FAIL_ATOMICITY` 的 Windows 重現結果不代表修正版已通過實機。修正版已於 2026-11-16 通過使用者 Windows/Anaconda 私有 SQLite 實機：21 tests OK、`PASS_ATOMICITY`、跨程序鎖 PASS、`STATUS=PASS_KI012_PRIVATE`；新增的 `run-bl001-sqlite-overlap-check.bat` 六項檢查也全部 PASS，兩種中斷各留下 1 張候選表。**正式 WorkPool／網路磁碟尚未驗收**。另有並行和候選表殘留風險，不應直接列為已解決。

新增 `run-bl001-sqlite-overlap-check.bat`，也可執行 `python -m scripts.bl001_stage_sqlite_overlap_acceptance`。此工具**不接受 --db、--WorkPool 等外部路徑**，只新建私人 TemporaryDirectory SQLite，啟動真正的 Python 子程序測兩種交錯：

1. **交易開始前**：writer A 先由 pandas 提交唯一候選表並暫停在 BEGIN IMMEDIATE 前；writer B 可完成新的 sampleSrc 與索引，接著終止 A。已成功提交的 B 不應受到 A 中斷影響；A 的候選表應可檢出且不應被其他 writer 擅自刪除。
2. **交易鎖期間**：writer A 已進入 SQLite 交易但尚未建立 text_Index，另一 writer 嘗試寫入須收到 `database is locked`，不得偷偷提交；中斷 A 後原來的 sampleSrc 與索引應回滾，後續 writer 才能重新提交。中斷 A 遺留的候選表不得被不相關 writer 自動清掉。

輸出 JSON 的 `status=PASS` 表示指定兩種交錯情境在目前環境通過，且 `orphan_candidates_after_pre_swap_kill=1` 和 `orphan_candidates_after_mid_swap_kill=1` 只表示**測試本身刻意留下孤兒表，證實必須管理空間與清理的所有權**，不表示可以直接刪除現實 DB 中的任何同名表。所有測試檔案在私人 TemporaryDirectory 結束後清理；CLI 出現 `FAIL`／`BLOCKED_DEPENDENCY` 不得視為成功。

測試模組：`python -m unittest -v tests.test_bl001_stage_sqlite_overlap_acceptance`。尚未涵蓋大資料量、真正連續併發壓力、共用網路磁碟、正式 WorkPool、殘留表的安全清理協議，或使用者修正版 Windows 實機驗收；`KI-012` 繼續 Open。**不允許直接操作正式資料庫去製造鎖或刪除殘留表。**

## KI-012 離線 SQLite 候選表唯讀盤點（不提供清理）

已確認兩種中斷情境都可能留下 `__bl001_stage_<32個十六進位字元>` 候選表，**是否仍有活動 writer 無法僅憑表名判定**。因此新增 `run-bl001-sqlite-candidate-inventory.bat`，只查詢 **已停止寫入且另存的離線 SQLite 複本**，不允許拿正式／活動中的資料庫做此項判斷。避免直接複製正在執行的 SQLite（尤其 WAL 模式）；必須先停止所有 writer 並確認複本不含 sidecar。

```bat
run-bl001-sqlite-candidate-inventory.bat --db "D:\\private\\offline-copy.sqlite3"
```

此處路徑僅為**自行準備的離線複本示意**；沒有必要為了執行新工具而操作你的正式 WorkPool。工具採 `mode=ro&immutable=1`、`PRAGMA query_only=ON`，只讀 SQLite schema metadata；不查資料列、不開啟可寫連線、不執行 `DROP`／`VACUUM`／`DELETE`／任何修復。檢查結果：

- `PASS_NO_CANDIDATES`／exit 0：來源複本的 `sampleSrc`／`text_Index` 合約通過，且沒有候選表名稱；不代表曾經沒有失敗或正式資料庫健康。
- `REVIEW_REQUIRED`／exit 1：存在符合格式的候選表或可疑前綴。列出候選表數量及最多前 20 名供人工查核；**不是自動清理建議**，絕對不能憑此直接 DROP。
- `UNVERIFIABLE`／exit 2：缺檔、symlink、WAL／journal／SHM sidecar、資料庫無效、或原有 schema 不符合。此時不能信任零候選的判斷，必須重新準備靜止複本。

CI 回歸入口：`python -m unittest -v tests.test_bl001_stage_sqlite_candidate_inventory`。新工具 Windows 實機尚待驗證，但此前原子修復與多程序重疊的 Windows UAT 已經通過。這個唯讀工具**不能證明候選表是否真正孤兒**，也沒有任何清理正式 DB 的能力。

**離線路徑保護（新增）**：唯讀候選表工具除了拒絕檔案自身 symlink／WAL/journal sidecar，也拒絕提交路徑或解析後路徑中任何以 `WorkPool` 開頭的目錄元件（不分大小寫，包括 WorkPool 備份資料夾）。這是防呆而不是對活躍資料庫的檢測能力；需把已靜止且另存的複本移到明確獨立的暫存位置才能查，不能拿正式 DB 冒險。

## KI-012 私人環境進階快檢（PR #263～#267）

此批新增的命令都維持**不操作正式 WorkPool**的界線。先使用已合併的 `run-bl001-sqlite-perf-check.bat` 測量本機私人 SQLite 的舊式與原子式寫入相對耗時（預設 1,000 rows × 2 rounds；最多 20,000 rows × 3 rounds），以及 `run-bl001-sqlite-parallel-stress.bat` 驗證有限的多程序重疊寫入（預設 3 workers × 2 rounds × 50 rows）。兩者通過也**不是正式共享磁碟、大批次或全工作池效能證明**。**2026-11-16 Windows／Anaconda 私人 SQLite 實機回報（業主提供的 CLI JSON）**：

- `run-bl001-sqlite-overlap-check.bat`：`status=PASS`，六項指定重疊／中斷／回滾檢查全部通過；`orphan_candidates_after_pre_swap_kill=1`、`orphan_candidates_after_mid_swap_kill=1`。兩個數值是受控中斷留下的候選表，不表示可清理正式庫。
- `run-bl001-sqlite-perf-check.bat`：`status=PASS_MEASURED`、`rows=1000`、`rounds=2`。atomic-staging 的實測耗時 `0.02638`、`0.027866` 秒；legacy two-step 為 `0.024825`、`0.028017` 秒；工具回報 `atomic_vs_legacy_elapsed_ratio=1.027`（約多 2.7% 耗時）。完成後 DB 大小 atomic `487424` bytes、legacy `319488` bytes（約多 52.6%，**不是**峰值磁碟空間）。短樣本不能推論大規模吞吐、磁碟 peak、共享磁碟或 SLA。
- `run-bl001-sqlite-parallel-stress.bat`：`status=PASS`、`workers=3`、`rounds=2`、`rows_per_writer=50`；兩回合各 `committed=3`／`locked=0`，最終勝出的 writer 為 `r0-w1`、`r1-w0`。表示這次測試最終資料一致，不代表三個 writer 同時持有 SQLite 寫入鎖，也未覆蓋長時間負載或所有交錯時序。
- 三項 JSON 均標為 `private_tempfile_only_no_workpool`，所以**正式 WorkPool、共享磁碟及峰值空間仍未驗收**；不可將私人 PASS 當成 Production PASS。

`run-bl001-sqlite-release-preflight.bat` **本次尚未提供 Windows 實測輸出**；一鍵整合驗收仍待回報。

在所有 writer 已停止且有獨立離線 SQLite 複本時，`run-bl001-sqlite-candidate-inventory.bat --db "<offline-copy.sqlite3>"` 與 `run-bl001-sqlite-candidate-triage.bat --db "<offline-copy.sqlite3>"` 只檢查 metadata。**任何 WorkPool 目錄中的 DB 均被拒絕**；候選表即使包含 `text` 欄及有效 pandas 索引，也仍標為 `owner_status=UNKNOWN`、`safe_to_delete=false`；目前**完全沒有自動或人工正式庫刪表入口**。

如需集中驗收，可在 Windows Anaconda Prompt 的 repository root 使用：

```bat
run-bl001-sqlite-release-preflight.bat
```

沒有明確模型參數時，全部私人寫入測試及隔離主流程成功會顯示 `PASS_PARTIAL_NO_REAL_MODEL`／exit 2（這是刻意的不完整狀態，不是失敗，也不是完整 PASS）。若本機已安裝 8050 對應的實際模型，才選擇：

```bat
run-bl001-sqlite-release-preflight.bat --real-port 8050
```

全部子檢查成功顯示 `PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION`／exit 0；任一必要測試失敗或檔案缺失回報 `FAIL`／exit 1。實際模型的完整流程由既有 `TCFMain.py --self-test real -p 8050` 以隔離工作池執行，目前 `config_from_cli()` 不會轉送 `TCP_REAL_PIPELINE_TIMEOUT_SECONDS` 給真實流程，因此 CLI 真正使用預設 1,800 秒；此快檢外層固定採 2,100 秒（多留 300 秒供 supervisor 終止子程序與清理），不會因外部同名環境變數縮短監督程序的生命週期。若未來 CLI timeout 契約改變，必須同步修正此驗收入口與測試。即使 `PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION`，`production_workpool_verified=false`，仍不得宣告正式資料庫上線／清理安全／正式 WorkPool 完整驗收。新一鍵快檢的 Windows 實機結果尚未收到。

## KI-012 私人 SQLite 候選寫入的磁碟階段量測（非正式上線）

`run-bl001-sqlite-disk-profile.bat`（或 `python -m scripts.bl001_stage_sqlite_disk_profile --rows 2000 --repeat 4`）只會在 Python `TemporaryDirectory` 中建立私人 SQLite；沒有 `--db` 或正式 WorkPool 路徑參數。預設 2,000 筆、文字重複 4 次，硬上限 20,000 筆與 8 次，不啟動模型。

量測包含原始資料庫、候選表準備完畢、交易複製、建立 `text_Index`、候選表交易內刪除、提交前／後與完全關閉後的資料庫及 `-journal`／`-wal`／`-shm` 佔用。結果 `PASS_CHECKPOINT_MEASURED` 只代表固定 SQL 階段的檔案大小取樣及最終 schema／資料完整；`checkpoint_max_total_bytes` **不是連續取樣的真正最大磁碟峰值**，也不是實際磁碟剩餘空間、配額或網路共享碟安全界線。若要為正式大批次決策，仍須補獨立空間限制與 WorkPool 隔離驗收。Windows 實機結果尚未回報。

## KI-012 一鍵快檢加入私人磁碟量測及 SQLITE_FULL 回滾驗收

`run-bl001-sqlite-release-preflight.bat` 現在也會在私人 TemporaryDirectory 中執行 `disk_checkpoints`（100 筆、文字重複 2 次；期待 `PASS_CHECKPOINT_MEASURED`）與 `sqlite_full_rollback`（120 筆、文字重複 64 次；期待 `PASS_SQLITE_FULL_ROLLBACK`）。兩項只使用私人 SQLite，拒絕外部資料庫路徑。任一必要狀態不符即 `FAIL`，不再進行後續模型測試。

**這不改變正式驗收界線。** 無真實模型時結果仍為 `PASS_PARTIAL_NO_REAL_MODEL`／exit 2；明確啟用真實模型的通過結果最多為 `PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION`。磁碟 checkpoint 不是連續峰值，SQLite page quota 也不是 OS 磁碟滿載；正式 WorkPool、網路共享碟及實際部署仍未驗證。

### KI-012 私人 SQLite 配額解除後重試

`run-bl001-sqlite-full-rollback.bat` 現在除驗證遭 `SQLITE_FULL` 拒絕時原資料完整，也在**同一個私人 tempfile 資料庫**解除測試頁數限制後，透過現有原子式 `write_stage_sql` 重新寫入。僅當重試資料列、`text_Index`、View、其他無關資料、SQLite integrity 和候選表清理均正確時，才回報 `PASS_SQLITE_FULL_ROLLBACK`，並以 `post_quota_retry_passed=true` 表達受控的恢復驗證。這**不是**正式磁碟滿載後一定能恢復的證據，且不影響任何正式 WorkPool。

## KI-012 私人 SQLite 讀取者與寫入者快照一致性

`run-bl001-sqlite-reader-snapshot.bat`（預設 40 rows；最多 500 rows）使用私人 TemporaryDirectory SQLite，真正啟動第二個 Python writer。先讓 writer 建好候選表並暫停在 `BEGIN IMMEDIATE` 前，讀取端開始交易並讀取舊內容，接著放行 writer；其 final swap 尚未提交時，再透過同一 reader transaction 查 `sampleSrc` 與 View，必須仍是舊內容。讀取端提交釋鎖後，writer 才可完成，重新連線必須讀到完整新內容、保留 `text_Index` 與 pandas index、View 正確、無候選表且 `integrity_check=ok`。

`PASS_PRIVATE_READER_SNAPSHOT` 只代表這個被控制的讀寫交錯在私人本機 SQLite 成功；不是正式 WorkPool、網路檔案系統或全部併發時序的保證，也沒有正式 DB 輸入參數。Windows 實機尚未驗收。

### KI-012 一鍵快檢加入私人 reader-snapshot 交錯測試

`run-bl001-sqlite-release-preflight.bat` 已將 `reader_snapshot`（20 筆、跨程序、TemporaryDirectory）列為必要子檢查，必須取得 `PASS_PRIVATE_READER_SNAPSHOT`；`PASS` 等其他回應不能冒充通過。原子式 writer、讀取端快照、View 和實際欄位索引必須保持一致。這仍**不是**正式 WorkPool／網路共享碟驗收；未啟用實際模型時，整體狀態依舊 `PASS_PARTIAL_NO_REAL_MODEL`。
