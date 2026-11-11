# `text_category_profiler` 遷移 TODO

> 類型：可持續執行的重構工作清單。後續 Codex 任務應一次處理一個可驗證批次，完成後更新本檔核取方塊與 `.codex/backlog.md` 狀態。

> 目前狀態：application-side package namespace、path injection 與 deployment boundary 已收斂；`TRV_deploy` 保留為獨立 legacy snapshot。Phase 5 的 legacy path/container 與 current-state 文件同步已完成，但 `text_category_profiler/` root 仍有 Phase 0–3 所追蹤的 research/test/script/vendor/legacy artifact 候選需要逐批分類與分流；PR #145 已有 fresh targeted lightweight full discovery 912 OK（2 opt-in SKIP）證據，但仍須完成剩餘分流與合併後最新 main 驗收才能將 `BL-001` 標記 Done。

## 目標

將 `PythonModule/utils/` 中真正跨 stage 共用的 helper 整理為根目錄 `text_category_profiler/` package，同時把具明確領域歸屬、測試、實驗、維護腳本與第三方程式移到合適邊界。遷移完成後，active code 不再依賴 `PackageImporter` 修改 `sys.path`，但既有 CLI、stage handoff 與資料格式保持相容。

## 已確認方向

- Python package 名稱採用 `text_category_profiler`，與 repository 名稱 `text-category-profiler` 對齊，不使用過度泛用的頂層 `utils` 或舊專案縮寫 `tcf_utils`。
- 保留 `DatasetConverter/`、`BertScript/`、`ClassesTree/` 的既有 stage／領域責任；本計畫不要求一次重組所有 stage。
- 只有至少兩個 active stage 使用、責任明確且適合重用的程式才進入 `text_category_profiler/`。
- stage-specific 程式應留在或移回所屬 stage，不得為縮短 import 而塞進共用 package。
- 先建立測試與相容層，再搬實作；application-side `PythonModule/` 與 `PackageImport.py` 最後移除。獨立 deployment snapshot 若仍需舊結構，必須有明確隔離 guard。

## 必須維持的不變條件

- `python TCFMain.py ...` 與目前各 stage script 的既有命令形式，在相容期內仍可使用。
- CLI option 名稱、型別與預設值不因搬檔而改變。
- `_is_running_*`、`_rdy_for_*` 等 stage handoff suffix 不變。
- `train.tsv`、`dev.tsv`、`test.tsv`、SQLite schema 與預測結果格式不變。
- 不使用真實工作池、模型、SQL、Elasticsearch、FTP 或寄信操作作為遷移測試。
- 不把人工輸出、模型、資料集、憑證或其他敏感資料提交到 Git。

## 目標結構（第一階段）

```text
text_category_profiler/
├── __init__.py
├── console.py
├── progress.py
├── paths.py
├── serialization.py
├── hashing.py
└── model_paths.py
```

這只是起始候選；不得為填滿結構而建立空模組。模組名稱應描述單一責任，禁止新增 `misc.py`、`common.py`、`helpers.py` 或新的總括 `utilities.py`。

## 執行原則

後續每次 Codex 工作應遵守：

1. 開始前閱讀本檔、`.codex/backlog.md`、`.codex/architecture.md`、`.codex/contracts.md` 與 `.codex/workflows.md`。
2. 一次只選一個下列批次，先用 `rg` 找出 active callers、重複實作與 optional dependencies。
3. 先補 characterization test，證明搬遷前後公開行為一致。
4. 優先使用 `git mv` 保留歷史；拆分函式時避免同時改寫行為或命名。
5. 必須改 import 時，同一批次更新所有 active callers 與 tests。
6. 若保留 compatibility shim，實作只 re-export，不複製函式，並在本檔記錄移除條件。
7. 每批至少執行最相關測試、完整輕量測試與 `git diff --check`。
8. 完成後更新核取方塊；只有整體完成條件全部滿足時，才將 `BL-001` 標記為 `Done`。

## TODO

### Phase 0：盤點與安全網

- [x] 建立五個 canonical active entry point 的**可重現靜態清單**：`TCFMain.py`、DataConverter、classifier runner、result combiner、visualization；`scripts/bl001_canonical_import_audit.py` 對每個路徑做存在性與 AST parse fail-closed 檢查、輸出 `canonical_entrypoint_inventory`，`tests/test_bl001_canonical_import_audit.py` 保護五個角色與缺檔／無效語法。此為 source inventory，**未驗證實際 runtime dispatch、外部 caller、GPU、WorkPool 或 GUI**。
- [ ] 產生 `PythonModule/utils/` 模組 → active callers 對照表，排除 archive、vendor、copy 與部署 snapshot。
- [ ] 逐組比較重複模組，例如 `df_utils.py`、`MP_utils.py`、`utilities.py`，確認權威版本與差異。此批已建立三組九個來源的 source SHA256、top-level public AST 定義交集／差異、可見明確第一方 import 語法的唯讀報告（`scripts/bl001_duplicate_provider_audit.py`，Hosted JSON artifact）；`package_domain_owner` 僅指結構歸屬，不能代表 stage-local 版本可安全被取代。動態／外部 caller 與真實 API 語意差異尚未驗證，**不得將此項標記完成或自動刪掉任何版本**。
- [ ] 將檔案標記為 `shared`、`stage-specific`、`script`、`test/experiment`、`vendor`、`legacy/unknown` 六類。
- [ ] 為第一批候選模組確認或補齊無外部服務副作用的 characterization tests。新增 isolated `dfToTSV` AST functional test 對三版本做無外部依賴契約比對：`DatasetConverter`／`BertScript` 同為兩參數 TSV 不含 header/index，canonical `data/df_utils` 預設 CSV options 相同，但即使未啟用 adapter 仍執行 `multicoreJob.ComputeNProcess`，可造成異常且具有擴充版 tsvIndex/header/adapter 參數；不代表可互換、更不能刪除 stage-local implementation。模型／外部 caller／完整資料輸出尚待驗證。 另新增 `dfToXLS` 的 stdlib AST isolated tests：兩份 stage-local provider 固定傳 `encoding='utf-8'` 並接受但不使用傳入 encoding；canonical provider 使用 `pd.ExcelWriter` 指定 `strings_to_urls=False`、sheet/mode，超過 1,048,576 列跳過，writer 例外會嘗試 fallback `df.to_excel`。這些差異只由 recording stubs 確認呼叫邊界，尚未驗證真實 Excel 寫出、fallback 資料保全或外部 callers；PR #199 已 21/21 Hosted CI PASS、正式 Review 0 Findings 後合併；不做 provider 合併。
- [ ] 記錄 repository 外部是否仍有程式依賴 `from utils...`；未確認前保留相容策略。

另新增 `dfToSQL` 的隔離 AST/fake-SQLite 比較：stage-local 固定 `sampleSrc` replace 和 `text_Index`、成功路徑未 close；canonical 支援 `table`、`if_exists`、`IndexCols`、`UniqueIndexCols`、`dtype`，原先僅成功路徑 close、`to_sql`/索引/欄位選取例外時可能未關閉連線；PR #213 已於 `main@19d4431c21f8ef69f60ef53b1ad8ebec9107d37a` 合併：canonical `dfToSQL` 連線包於 `try/finally`，以 isolated fake-SQLite 驗證欄位選取、`to_sql`、索引例外時必須 close 且保留原例外；原 HEAD `c56eccc` 的 Hosted CI 21/21 PASS、正式 Codex Review 0 Findings、0 未解決 threads。仍無實際 SQLite/pandas 落盤或交易回滾驗收。這些只是無資料庫功能契約記錄，不能拿來證明 SQLite 真正成功或安全遷移；PR #200 於最新 HEAD 修正 Current Focus P1 後取得 21/21 Hosted CI PASS、正式 Codex Review 0 Findings 並合併；仍不得統一三份 provider。PR #216（`main@518239419b161e790f21f25f6fd622e78047fd71`）已將 alternate `dfToSQL_new_appending` 連線生命週期改為 `try/finally`，`tests/test_bl001_df_sql_new_appending_contract.py` 5 項 isolated AST/fake-SQLite 測試涵蓋 success、schema、to_sql、普通與唯一索引失敗，修正 Codex P2 fake cursor 缺乏 `fetchall()` 後，原 HEAD `e2ef3ad` 取得 21/21 Hosted CI PASS、正式 Review 0 Findings，已合併。PR #217（`main@07395c56bda695154d866f44b921c7747594042b`）新增 `tests/test_bl001_sqlite_memory_contract.py` 3 項 pandas + 私有記憶體 SQLite 測試，驗證 Unicode JSON 資料、真實普通/唯一索引、`if_exists='fail'` 舊列保全及 close，原 HEAD `6d57712` 21/21 Hosted CI PASS、正式 Review 0 Findings，已合併。仍未觸及 stage-local writer 或正式 WorkPool/DB，也不證明磁碟持久性、真正 `ensure_schema` adapter、交易原子性或安全統一 provider。

**下一批 real-schema acceptance（本 PR，驗證中）**：在同一測試檔使用 isolated AST 直接抽取 `text_category_profiler/data/DB_utils.py` 的實際 `ensure_schema` 與 `infer_sqlite_type`，但不匯入 DB_utils 的外部服務／手動入口。追加 pandas + SQLite 私有記憶體的 INTEGER/REAL/TEXT 型別、空 DataFrame TEXT fallback、兩次 alternate writer `if_exists='append'` 所需新增欄位、保留舊列及普通索引、兩筆 writer connection close 回歸測試。必須等 latest-head Hosted CI 與 Codex Review；不涉及真實 WorkPool、磁碟持久化、正式 runtime module import、交易回滾及 provider consolidation。追加一批 JSON 結構欄位 isolated test：canonical 對 dict/list/tuple 轉成 `json.dumps(ensure_ascii=False)`，stage-local 保留原物件；只使用 fake DataFrame 的 apply/to_sql 紀錄，沒有真實 SQLite、pandas 寫入或持久化驗證，本批 CI／Review 待確認。

### Phase 1：建立最小 `text_category_profiler`

- [ ] 建立 `text_category_profiler/__init__.py`，不在 package import 時載入大型 optional dependencies 或執行副作用。
- [ ] 將 `model_paths.py` 搬至 `text_category_profiler/model_paths.py`，更新測試與 active callers。
- [ ] 將 `torch_compat.py` 搬至 `text_category_profiler/torch_compat.py`，更新測試與 active callers。
- [ ] 將 `log_display.py` 搬至 `text_category_profiler/console.py`，更新測試與 active callers。
- [ ] 將 `progress_utils.py` 搬至 `text_category_profiler/progress.py`，更新 active callers。
- [ ] 確認以上模組可直接由 repository root import，不需要 `PackageImporter.proc()`。
- [ ] 若需要 compatibility shim，加入針對舊 import path 的測試並記錄移除條件。

### BL-001 可供內網維護窗口採納的小型重構（2026-11-09）

- 已將 `DatasetConverter.df_utils.dfToTSV(df, OutputFN)` 與 `BertScript.df_utils.dfToTSV(df, OutputFN)` 的**相同** stage-local TSV 格式規則收斂到 `text_category_profiler.data.stage_tsv.write_stage_tsv`，保留兩個呼叫端既有 API、錯誤傳遞與 UTF-8／TAB／無 header/index 的格式語意；對應 characterization + optional pandas bytes regression。**不**將含 `multicoreJob.ComputeNProcess` 的 canonical `text_category_profiler.data.df_utils.dfToTSV` 合併，亦未變更 WorkPool、模型或 GUI。
- 這是 `df_utils` 去重的**有限批次**；仍有其他版本與外部 callers 未驗證，以上 Phase 0 的全家族項目維持 `[ ]`。實機部署、資料流程及 GPU acceptance 不在 Hosted 測試範圍；部署候選摘要見 `docs/release-prep/bl001-stage-local-tsv.md`。

- 接續 TSV 小批次，將 `DatasetConverter.df_utils.dfToXLS` 與 `BertScript.df_utils.dfToXLS` 兩個同源的固定 xlsxwriter 呼叫收斂至 `text_category_profiler.data.stage_xlsx.write_stage_xlsx`；保留 `dfToXLS(df, OutputFN, excelindex=True, encoding='utf-8')` API（舊 `encoding` 參數**原本即被忽略**）、固定 `engine='xlsxwriter'`／`encoding='utf-8'`、無隱式重試、既有例外傳遞。現有 canonical `data.df_utils.dfToXLS` 含 ExcelWriter、欄位名、overflow、fallback 等不同策略，**不可互換、未整併**；對應 isolated stub 與 optional pandas 對照測試。2026-11-11 後續相容修正候選改以 `inspect.signature(df.to_excel)` 判斷是否接受 `encoding`，只在新版顯式不接受時省略；保留舊版與 `**kwargs` 傳參、單次呼叫及失敗例外，不進行 TypeError 重試。以新舊簽名 recording frames、真實私有 pandas + xlsxwriter XLSX 工作表內容驗證；**內網 WorkPool 與完整模型 GUI 未驗收**。詳細更新候選及實機條件見 `docs/release-prep/bl001-stage-local-xlsx.md`；BL-001 繼續 In Progress。

- **2026-11-09 Stage-local SQLite consolidation（本批候選）：** 已確認 `DatasetConverter.df_utils.dfToSQL` 和 `BertScript.df_utils.dfToSQL` 皆固定 `sampleSrc` replace + `text_Index`，但兩份 stage-local 原實作皆未明確關閉連線。以 `text_category_profiler.data.stage_sql.write_stage_sql` 形成一份 stage-local 固定政策實作，保留兩個 `dfToSQL(SQLname, df, SavingDfColumns=[])` 入口與 stage-local 的 `lite.connect`，新增 `try/finally` 例外與成功路徑關閉 SQLite 連線；**這是明確的行為修正，不是單純搬移**。隔離 fake DataFrame/SQLite 測試包括固定表／索引、選欄／寫入／建索引失敗與單次 close；另在私有記憶體 SQLite 驗證 rows/index 寫入後依舊可見。與 canonical `text_category_profiler.data.df_utils.dfToSQL` 的結構化欄位 JSON 轉換、自訂表名、dtype、各種索引等政策不同，不得合併；資料庫檔案持久性、Windows／Linux 真實 WorkPool、鎖定／rollback 及模型端到端仍待內網驗收。詳細 deployment gate 見 `docs/release-prep/bl001-stage-local-sql.md`；BL-001 仍為 In Progress。

- **2026-11-11 Stage-local writer 快檢（PR #242 已合併）**：新增 Windows `run-bl001-stage-writer-check.bat` 與跨平台 `python -m scripts.bl001_stage_writer_check`，重用既有三組 TSV／XLSX／SQLite 隔離測試，另強制真實寫出私人 TSV（避免 pandas 3.x 舊版預期例外誤判 PASS）；缺 pandas/xlsxwriter、任一 SKIP／失敗、無測試或 TSV 寫出失敗均不回報 PASS。此入口不操作真實 WorkPool、分類模型或正式 DB，成功只代表部署前 focused 環境驗證，不取代 Windows GUI、完整 pipeline 及內網實機 acceptance；BL-001 仍 In Progress。

- **2026-11-11 canonical TSV pandas 3 修復（本 PR，Hosted CI／正式 Review 待驗）**：發現 configurable `text_category_profiler/data/df_utils.py::dfToTSV` 同樣使用 `csv.QUOTE_NONE` + `quotechar=""`，在 pandas 3.1.1 實際輸出會 TypeError。僅改這個內部選項成 `None`；其 `multicoreJob().ComputeNProcess(log=False)`、可選 `TSVTextAdapter`、`tsvIndex`／`header` 與例外傳遞不變，絕不重導向 Stage-local writer。以 isolated function AST + FakeMulticore + 私有 tempfile pandas 2.2.3／3.1.1 fixture 測試成功且等值的輸出位元組。尚未做 Windows／完整 WorkPool acceptance，BL-001 繼續 In Progress。

- **2026-11-11 canonical 多工作表 XLSX 清單保全（本 PR，Hosted／Review 待驗）**：`data.df_utils.dfListToXLS` 過去對呼叫端 `sheetNameList` 執行 `reverse()`、`pop()`，一次匯出會消耗清單；改為先取得內部反轉複本再依既有順序 `pop()`。維持公開參數、已有 sheet 順序／缺少名稱時 `AutoSheetNameN`、ExcelWriter 設定與預設 row/column 格式；以 AST fake writer + pandas/xlsxwriter 私有 workbook 的多次輸出、Unicode sheet names、例外路徑測試。這不是文件／工作池部署證據，BL-001 繼續 In Progress。

- **2026-11-11 canonical XLSX 列高計算資料保全（本 PR，Hosted／Review 待驗）**：在 `dfListToXLS(AutoAdjustRowWidth=True)` 下，過去 `smart_reset_index(df, ...)` 在寫完工作表後直接修改呼叫端 DataFrame 的 index/columns，可能影響重複匯出；本批在列高路徑用 `reset_index()` 與 `rename()` 的非 inplace 寫法產生新的 DataFrame 供逐列高度計算，避免舊 `smart_reset_index` 對 pandas 3.1.1 的 inplace 棄用警告，保留既有 XLSX worksheet 名稱、列高公式、格式、選用 index 的行為與 API。新增 fake writer 和私有 pandas XLSX 測試，不更動模型、WorkPool 或真正內網資料。BL-001 仍 In Progress。

- **2026-11-11 canonical 多工作表 XLSX 空資料欄寬修復（本 PR，Hosted／Review 待驗）**：已重現 `dfListToXLS(AutoAdjustColWidth=True)` 遇到空 DataFrame 的 `Series.max()` 回傳 NaN，xlsxwriter 可將 `width="nan"` 寫入 workbook XML；現在僅在 Series 零列時以欄名長度＋1 取代 NaN，其他非空欄寬及 MaxColWidth 上限規則不變。私有 pandas/xlsxwriter XLSX 測試解析工作表 XML，確認欄寬有限、合理，對非空列仍能套用上限；不碰 WorkPool 或正式 XLSX，BL-001 保持 In Progress。

### Phase 2：拆分路徑、序列化與基礎 helper

- [ ] 從 `utilities_path.py` 盤點純路徑 helper，搬到 `text_category_profiler/paths.py`；檔案搬移／刪除函式需另行風險審查。
- [ ] 從 `json_utils.py` 搬移通用 serialization helpers；具資料領域語意的 serializer 留在原領域。
- [ ] 從 `utilities.py` 提取 hashing helpers，建立單元測試後搬到 `text_category_profiler/hashing.py`。
- [ ] 盤點 time、collection 與 text helpers；只有確有跨 stage callers 才建立對應單一責任模組。
- [ ] 移除已由新模組取代的重複實作，不保留兩份可分歧的 source of truth。

### Phase 3：將非共用內容分流

- 2026-10-31 `Graph_utils` canonical import fix：在 PR #154 6 件 `no_nearby_first_party_provider_filename` 中，視覺化 `Graph_utils.py` 的 `try: from text_category_profiler.core.utilities import flattenList; except: from utilities import flattenList` catch-all 會將 canonical 依賴失敗遮蔽成未明確來源匯入。本批只移除該 fallback，使用原本優先的 qualified import；用 AST no-service tests 保護解析、錯誤透傳與 connected-component contract。剩下 5 個 `DatasetConverter/df_utils.py`、`DatasetConverter/old_MP_utils.py` 仍待逐一確認 legacy 相容性，不改動且不能宣稱整批已清零。BL-001 In Progress。


- 2026-10-31 bare-import provenance follow-up：PR #153 靜態報告中 15 件候選，需區分 `BertScript` stage-local 同名模組及 `DatasetConverter` 缺少 sibling provider 的未決候選。本批為每件候選新增 first-party tracked Python sibling/ancestor 路徑證據，**不假定 Python 實際 import resolution**；對 7 個 scoped-import 零命中的 canonical modules，加入 top-level `__main__` guard evidence（仍未直接執行）。不搬移／刪除程式，runtime/sys.path/外部動態 caller 仍待驗證，BL-001 In Progress。


- 2026-10-31 canonical module consumer evidence：在 PR #152 71 個 Git tracked package 路徑完整 census 基礎上，對 44 個 domain-owned Python modules 建立 bounded first-party AST import report。區分完整 qualified imports（含 `from package import module`／相對 imports）、literal importlib/runpy 候選、bare import unresolved candidates；按 source area `TCFMain.py`／DatasetConverter／BertScript／ClassesTree／TCF_Params／package-internal／scripts 分開，但**不推論實際 runtime stage**。此批只新增無執行副作用的報告與測試，保留全部程式碼；未命中不代表 unused，跨 stage/externals 功能性驗收與所有開放 Phase 0–3 TODO 仍待完成，BL-001 In Progress。


- 2026-10-31 full tracked package structural census：`text_category_profiler/` 目前完整 Git tracked tree 有 71 個檔案：58 個 canonical `cli/concurrency/core/data/diagnostics/execution/filesystem/integrations/pipeline/text/visualization` 領域檔案（含 docs、init），與既有 13 個 legacy compatibility/vendor/marker。兩份獨立 manifest 的 path union 透過 `git ls-files` 完整比對，SHA/長度與 legacy canonical target 可由 stdlib 重現；Hosted 產生完整 JSON artifact，新增未分類 path 必須明確處理。這是**路徑／責任歸屬的結構盤點**，不能推論全部 canonical code 都是有證據的跨階段 shared helper，也無法排除 repo 外／非 Python／動態 callers；phase 0–3 中開放的業務職責／CLI／外部驗收仍需另行查證，BL-001 In Progress。


- 2026-10-31 manual DB_utils ES template bare import follow-up：PR #150 的 AST report 顯示 `text_category_profiler/data/DB_utils.py` 在 `__main__` 使用 `from ArtCluESJobTemplate import esJobTemplate`，取決於隱式 sys.path；此獨立批次改為 canonical `text_category_profiler.integrations.es_job_template`，保持 template 的 keys/default/env snapshot（第一次 canonical import 時）及預覽 + SQLConcat 順序。純 stdlib 測試抽取 `__main__` AST 使用 fake ES-job builder、redaction、OSWALK、SQLConcat 執行，禁止外部 I/O；legacy audit 對這個 in-repo caller 預期 unresolved bare-import 歸零，仍不推論 repo 外／動態 consumer。此變更不證明 `DB_utils.py` 真實 standalone runtime 在未設定套件搜尋路徑、ES、SQL、模型環境可執行。BL-001 In Progress。


- 2026-10-30 bounded legacy root import audit：`text_category_profiler/` 直接根目錄 7 個 Python entry（6 個兼容入口、1 空 package marker），外加老 Dijkstra 路徑 5 個資源和舊 Tulip 模組兼容入口 1 件，合計 13 個追蹤項目建立 SHA/大小/canonical 目的地 inventory 與 stdlib AST import 靜態稽核；CI 輸出可供人工檢視的 JSON 報告。舊路徑均維持原樣，並明確辨別全名 AST import、未確定的 bare-import（DB_utils 手動入口）、字串候選、語法解析失敗；不能宣稱非 Python、動態、repo 外或手動 caller 已查清。歷史 Dijkstra README 的 legacy 相容註解與 vendor 上游 README 不同，僅要求 LICENSE 和兩份 graph fixtures 位元組相同。BL-001 仍 In Progress，最終 Phase 0–3 census 尚未完成。


- 2026-10-30 Tulip Stage 4 visualization boundary：原 `text_category_profiler/tulip_utils/Graph_Builder.py` 之 Git blob `8d6919e56381e30003c7582ecb78f0490f04c857`（24,232 bytes）按 byte 完全相同移至 `text_category_profiler/visualization/tulip_graph_builder.py`，因 Hosted CI 與 Codex Review 確認 `BertScript/Test_result_Vis.py` 為實際 active caller，必須歸屬 visualization 領域而非 experiments。Stage 4 canonical imports 已同步更新；舊路徑保留 lazy facade 和手動 main() 轉送。舊原始碼尾端空白以單檔 .gitattributes 例外保留，而其他新檔繼續 git diff --check。增加 stdlib blob/hash、Stage 4 AST caller、lazy import 及委派測試；未啟動 Tulip GUI、模型、ES 或 WorkPool。外部／動態 callers 與舊 globals/star imports 尚未全面認證，BL-001 In Progress。


- 2026-10-30 similarity historical TXT input split：原 `text_category_profiler/切片相似度比對法測試/test Document/` 15 份 TXT（與前批 12 份 XLSX 共同組成 27 個歷史檔案、824,594 bytes）依原 Git blob SHA 與檔名完整搬至 `experiments/fixtures/similarity_experiment_inputs/test Document/`；manifest schema v3 為 27 件全部記錄 relocated_path。歷史研究文本未重新產生、解碼或處理。 `InnerCrossSimilarityForTextListTest()` 兩份啟用中文 fixture 路徑不變，先前僅註解的 TXT 例子改從 `__file__` 定位；XLSX 仍輸出 caller cwd。以隔離 AST/stub 測試 15 份輸入讀取及歷史完整性；未執行 NLP、ES、模型或資料管線，外部／動態 callers 及原始資料授權仍未查證。BL-001 In Progress。


- 2026-10-30 wiki article research sample：獨立的 `text_category_profiler/sample_data/俄烏戰爭@wiki`（83,123 bytes，blob `85e7f0573296fe49f603a6bec14c043b378e64db`）保留完整原始 Git blob，分流到 `experiments/fixtures/wiki_article/`；不重新抓取 Wikipedia、修訂研究內容或聲稱來源授權已釐清。原路徑移除且無相容 symlink；Hosted 測試發現 `text_category_profiler/integrations/ES_utils.py` 的手動 ES upsert 範例有實際 cwd-relative `sample_data` 檔案讀取，已改以 `__file__` 導向 fixture，並用隔離 AST/helper 測試（不載入或寫入 ES）及 Git tracked Python 檔名稽核防護；動態／外部 callers 與真正原始版本資訊尚未驗證。BL-001 繼續 In Progress。

- 2026-10-30 similarity historical output split：原 `text_category_profiler/切片相似度比對法測試/` 的 12 個歷史 `.xlsx` 實驗輸出以**相同 Git blob SHA、相同相對分組/檔名**分流至 `experiments/fixtures/similarity_experiment_outputs/`，其餘 15 個 `.txt` 研究輸入維持原路徑；manifest 更新 schema v2，記錄每個 output 的 `relocated_path`。保全測試同時檢查原 output 路徑不存在、完整新目錄集合、三組四個 XLSX 原位元組、ZIP header，以及 TXT 未變。`scripts/bl001_research_caller_audit.py` 能辨識原/新雙路徑與同名檔歧義；不以無直接命中推論外部或動態 caller 不存在、不執行相似度演算法、不重建 XLSX，來源授權仍未驗證。BL-001 In Progress。

- 2026-10-30 FTP marker：將原 `text_category_profiler/FTPTEST/abc.txt`（3 bytes；Git blob `f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f`）按原物件分流到 `experiments/fixtures/legacy_ftp_marker/abc.txt`；獨立的 `TRV_deploy` snapshot 同內容原位保留。`DatasetConverter/DataConverter.py` 的唯一字串命中是三引號 `rowlist sample` 範例，未發現實際 `open`/FTP 呼叫；用 AST 與保全測試明確驗證。manifest v6 中原 12 筆均已標示 relocated_path，但仍有其他 package-root artifacts、27 筆原位實驗資料、外部／動態 callers 與資料授權尚未確認，不足以宣稱 BL-001 Done。同批新增 Hosted Python 3.11 fresh dependency-light `python -m unittest discover -s tests` 流程（安裝輕量資料依賴及 GPUtil，明確不啟用 H100/model runtime），實測 PR #145 HEAD `56f0bf9c37a4`、Hosted run `41024022467` **912 tests OK（skipped=2）**，完整證據 artifact `12963076869`；沒有安裝全 root requirements，也沒有執行模型／GPU／WorkPool。

- 2026-10-30 legacy text tables preservation：`EmojiAlll.txt`（36,516 bytes；blob `b603c8a3979c057b104ddb002aa50ff0588cdd9a`）、`特殊符號表.txt`（27,063 bytes；blob `f41651e616f86ca2c24f6bca9a1ed3242a7f1be7`）、`total.txt`（216,074 bytes；blob `21a5d2114b23f18c4d0a9b76f3a6cd9502f06133`）保留完全相同原 Git blob 分流到 `experiments/fixtures/legacy_text_tables/`，manifest v5 12 筆中 11 筆搬出。重新核對第一方 Python 靜態檔名字面引用無命中、blob/大小一致、舊路徑消失；未確認這三份文字表實際功能、來源授權或外部／動態使用。`FTPTEST/abc.txt` 仍在原位，因 `DatasetConverter/DataConverter.py` 存在直接 `abc.txt` 字串命中；是否為同一檔案的實際讀取仍需個別追蹤。完整 discovery 尚未驗收，BL-001 In Progress。

- 2026-10-29 punctuation sample fixture split：`text_category_profiler/testFix.txt`（83 bytes；blob `e0bedf8bd7f5f940a187c807960ef76c9e5755df`）及 `testFix - 複製.txt`（59 bytes；blob `f890fe1ef548af6096588bc88464cc67fdf8b106`）以**相同原 Git blob** 分流至 `experiments/fixtures/text_normalization/`。保留全形中文逗號差異；`bl001_residual_inventory.json` v4 記錄 12 筆原始資料中 8 筆已分流、4 筆維持原路徑。原位保全測試與新的 stdlib boundary test 核對 SHA、大小、舊路徑不存在、標點差異，並用受限第一方 Python 靜態掃描確認沒有直接檔名引用；這不等於外部／動態 caller 已查清。`FTPTEST/abc.txt` 在 `DatasetConverter/DataConverter.py` 有直接字串命中，因此本次刻意不移動，另三個文字表亦不變。BL-001 In Progress。

- 2026-10-29 Chinese similarity manual fixture split：原 `text_category_profiler/` 的陳德銘相似度研究 TXT 2 件與歷史輸出 XLSX 2 件（合計 19,310 bytes）已按原 Git blob 身分搬至 `experiments/fixtures/chinese_similarity/`；`bl001_residual_inventory.json` 更新 v3，12 筆保留原始身分，其中 6 筆有 `relocated_path`、6 筆仍在原處。已確認手動 caller `InnerCrossSimilarityForTextListTest()` 原來以 cwd `open(FN)` 讀兩個樣本，現在使用 `Path(__file__).resolve().parents[2]` 對中文輸入解析固定 fixture；既有 `saveFN=FN.rpartition(".")[0]+".xlsx"` 完整保留，依原樣輸出到 caller cwd，不會寫入歷史 XLSX fixture。隔離 stdlib 測試以 stub 驗證輸入路徑與輸出 basename，不執行相似度算法、不重建 xlsx。註解的其他手動檔名仍依原先 cwd 路徑；repo 外／動態 caller、資料來源授權未驗證。BL-001 In Progress。

- 2026-10-29 similarity research experiment preservation：在 `text_category_profiler/切片相似度比對法測試/` 確認 27 個原始 Git blob（12 個 `.xlsx` 實驗輸出、15 個 `.txt` 樣本／研究文本），總計 824,594 bytes；建立 `experiments/fixtures/bl001_similarity_experiment_inventory.json` 記錄每筆相對路徑、Git blob SHA、大小、資料群組與副檔名，並以 stdlib 依檔案清單、blob 身分、ZIP 容器簽章及三組 4 個 Excel／一組 15 個 TXT 進行原地保全驗證。無資料檔移動、修改或模型／相似度流程執行；外部／動態 caller、文件來源授權尚未驗證，後續移檔需單獨確立相容性。BL-001 仍 In Progress。

- 2026-10-29 MoodleDocs locale reference split：原 `text_category_profiler/Table of locales - MoodleDocs.pdf` 為歷史 locale 靜態參考文件（353,177 bytes、Git blob `189909957805328d356495130b2899529504cb78`），原樣以同一 Git blob 移至 `docs/references/table-of-locales-moodledocs.pdf`，並附來源與外部 caller 未驗證說明。新增 stdlib 測試防止文件內容被更動、舊路徑重新出現或 repo Python 原路徑字面引用；不會打開 PDF、執行研究實驗或改動任何 runtime。`切片相似度比對法測試/` 等研究資料仍待另批處理；BL-001 仍 In Progress。

- 2026-10-29 RAG/Similarity research fixture residual batch：對原 `text_category_profiler/RAGTest.json`（10,156 bytes、Git blob `4df2b417d2f19720218edc1d52ff9e847a385389`）及 `Similarity.tsv`（34,615 bytes、blob `9fe2e4ad6660e64a2f3befd7011735340865b345`）執行原物件搬遷至 `experiments/fixtures/research_samples/`。已知唯一 RAG 檔名 literal caller 是 `core/utilities.py` 的註解範例，改向新研究 fixture 路徑；已確認 `visualization/Graph_utils.py` 的 Louvain 手動 `__main__` 範例直接以 cwd 開啟 `Similarity.tsv`，已改用 `Path(__file__).resolve().parents[2]` 定位搬遷後檔案，保留 `build_Louvain`／`load_graph` public API 與輸入行為；stdlib 回歸檢查 graph sample 59 個節點（未實際執行完整 Louvain）。`bl001_residual_inventory.json` v2 保留 12 筆原 Git blob 身分，2 筆以 `relocated_path` 標示、另 10 筆仍在原位，防止檔案改寫或誤刪；stdlib boundary 掃描在庫 Python 舊路徑 literal、以 `JSONDecoder.raw_decode` 驗證歷史兩段相連 JSON arrays（9 與 5 筆，不能以單次 `json.load` 解析）及 TSV 基本格式，不執行真實研究分析。外部 callers、中文 cwd 相似度文本、測試 xlsx 與其他 legacy 內容仍未驗證／分流，BL-001 保持 In Progress。

- 2026-10-29 bounded residual preservation inventory：以 `experiments/fixtures/bl001_residual_inventory.json` 列出 12 項尚留在 package root 的研究／legacy 資料，保存 main 上的 Git blob SHA 與位元組長度；`tests/test_residual_research_inventory.py` 驗證原路徑、`testFix` 全形標點差異、`FTPTEST/abc.txt` 與 deployment snapshot 的相同內容，以及相似度手動測試的 caller-cwd `open(FN)`。`RAGTest.json` 在 `core/utilities.py` 目前只見註解範例。這是**非窮盡清單**，GitHub code search 已遇到速率限制，不能宣稱外部或 repository-wide caller 已完全盤點；本批**不移檔、不改 runtime、不宣稱 BL-001 Done**。`Table of locales - MoodleDocs.pdf` 已分流至 `docs/references/`，`切片相似度比對法測試/` 仍待另批處理。

- [ ] 將 `DataConverter_utils*.py` 的 domain logic 移回 `DatasetConverter/`，維持 dataset contract。
- [ ] 將分類器、模型與 GPU/CPU runtime 專用程式移回 `BertScript/` 的適當子模組。
- [ ] 將 Dash、Plotly、graph 與 reusable components 移至 visualization 邊界。
- [ ] 將 SQLite、MongoDB、Elasticsearch、FTP、Email 功能按 backend／integration 拆分，避免 import 一個 backend 時強制載入其他 backend。
- [ ] 將可獨立執行的匯入／轉換工具移至 `scripts/`，並保留明確 CLI entry behavior。
  - 2026-10-28 residual batch ES ingest：`text_category_profiler/ES_ingest_txt_to_es.py` 是具 `CONTRACT-CLI-002` 的手動 Elasticsearch TXT bulk 匯入工具，不是 application shared helper。實作移至 `scripts/ES_ingest_txt_to_es.py`；舊路徑以 lazy Python helpers 與 direct-run wrapper 保留 CLI 選項／預設值／cwd-relative 語意。先前 top-level `from ES_utils`（舊 bare import）改為明確呼叫 bulk 才載入 `text_category_profiler.integrations.ES_utils` 與 ES client；std-lib tests 採暫存檔與 fake ES bulk，未連線真實服務、不改 production classifier 與 WorkPool。`scripts/` 並非 production import boundary，完成 external callers 查證前保留舊 wrapper。BL-001 仍 In Progress。
  - 2026-10-28 residual batch ArtClu ES job template：`text_category_profiler/ArtCluESJobTemplate.py` 是匯入時從 `TCP_ELASTIC_PASSWORD` 取得密碼值的 optional Elasticsearch job config dict，非 package-root 共用 helper。以同一 Git blob 將設定原樣移至 `text_category_profiler/integrations/es_job_template.py`，原路徑改為依原先執行／reload／runpy 語意重新執行權威設定並建立獨立 `esJobTemplate` dict（避免沿用已快取的密碼），保留原 keys、localhost host、user、`movies_%m`、語言及 import-time env snapshot。以 fresh Python subprocess、可控假環境值驗證缺密碼時 None、mutability 與 no ES import/socket；不測真實 ES。其他 residual dataset/fixture 和 final lightweight suite 尚待後續獨立批次，BL-001 未結案。
- [ ] 將 `*_test.py`、效能比較與研究原型分流到 `tests/` 或 `experiments/`。
  - 2026-10-29 CLI selector residual：`text_category_profiler/selector.py` 是互動式 terminal helper，非 classifier pipeline 核心；將 byte-identical 原始實作分流至 `text_category_profiler/cli/selector.py`，舊 module path 留作 class/colorama re-export。使用受控假 colorama、input 與 curses 測試實際選擇／預設／重試，不啟動真實終端；新的功能行為或修正既有 mutable default 另立 PR。剩餘資料樣本（FTPTEST、csvSample、KaggleExtraction、相似度研究原始資料）需先釐清可能的相對路徑與內容再決定搬移；本批不宣告 BL-001 Done。
  - 2026-10-29 Kaggle CSV fixture residual batch：`text_category_profiler/KaggleExtraction/` 只包含 2 個相同 Git blob 的小型 csvSample 輸入，`text_category_profiler/csvSample/` 含 24 個輸出 txt（4 種內容各 6 個）；不與 `data/df_utils.py` direct-script 所引用、但本 repo 並未附帶的 `KaggleExtraction/us/ads.json` 混為一談。共 26 個小型樣本以原 Git blob SHA/bytes 原樣搬至 `experiments/fixtures/kaggle_csv_sample/`，新增 manifest、stdlib tests 驗證資料內容及在庫程式靜態舊路徑引用；首輪 Hosted CI 實際攔下 `text_category_profiler/pipeline/DataConverter_utils.py` 手動 `__main__` 的 Windows 絕對舊路徑，已以 `Path(__file__).resolve().parents[2]` 定位新 fixture，維持既有迴圈而未呼叫真實 pandas/Kaggle 工作；舊資料路徑不建立跨平台風險的 symlink，外部手動 caller 須依 README 更新。其他相似度研究文本仍有可執行的 cwd-relative 測試函式依賴，不在此批搬移。BL-001 仍 In Progress。
  - 2026-10-01 residual batch 1：將 package root 的 `WTFOutputer_test.py`、`df_mpTest.py`、`df_mpTest_ThreadPoolExecutor.py`、`df_mpTest_wrapper.py`、`mp_test.py` 分類為 standalone test/experiment prototypes，原內容移至 repository-level `experiments/` 邊界；本批不刪除原型、不宣稱完成全部 Phase 3 inventory。
  - 2026-10-28 residual batch RAND：`text_category_profiler/utilities_RAND.py` 為手動 RAND corpus 分類與複製實驗，並非跨 stage 共享 helper；原本在 import 時載入已遷移的 bare `df_utils`、`utilities` provider。實作移至 `experiments/rand_corpus_labeling.py`，保留舊路徑的 direct-run 相容入口，原 `LoadTree`／`GetSubNodes`／`RANDLoader` 仍可懶載入；只有明確執行或取得 metadata 才載入依賴。新 stdlib 測試檢查 import 不碰資料、舊呼叫相容與直接執行委派，未連線真實 SQLite、複製 RAND 文件或跑模型。本批不代表 Phase 3／BL-001 完成。
  - 2026-10-27 residual batch 2（PR #124 已合併）：將 `text_category_profiler/Timestamp generator.py` 分類為手動執行的 timestamp corpus research experiment，實作移至 `experiments/timestamp_generator.py`，在新實作以明確 `main()` 保留原 5000 次生成及 cwd-relative 輸出語意；原路徑只保留 import-safe direct-script delegation shim，因 repository 外手動 caller 尚未查證，不先移除。使用 `tests/test_timestamp_experiment_boundary.py` 的 import-safety／bounded generation／old CLI dispatch characterization，加 Hosted `git grep` canonical caller guard。此批不涉及其他 residual root items，Phase 3 保持未完成。
- [x] 查證 `Edited_zipfile.py`、`dijkstra_algorithm_master/` 的來源、程式差異與授權，將來源已核實的第三方程式分流到 `vendor/`，並保留舊入口相容。
  - 2026-10-28 CPython ZIP vendor boundary：已將舊 `Edited_zipfile.py` 與 CPython v3.7.17 `Lib/zipfile.py` 逐行對比：原版 2,178 行全部維持相同順序，只在中央目錄及 local file header 的非 UTF-8 CP437 路徑各插入 4 行 CP437→GBK 嘗試／失敗回退，共 8 行；patch 作者未知。以相同 Git blob SHA 將原始 patched implementation 放到 `vendor/cpython37_zipfile_gbk/zipfile.py`，並附上從上游 v3.7.17 取得的完整 LICENSE（PSF 歷史授權，非 MIT），舊 `text_category_profiler/Edited_zipfile.py` 保留 public API／CLI lazy facade。使用只含臨時 ZIP 的 characterization 驗證 GBK、CP437 fallback、UTF-8、ASCII、CLI 與上游歷史 blob identity；不處理真實／不可信 ZIP，也不改動 patch 邏輯。仍需另批盤點 package root 剩餘研究資料及完成最終 dependency-light suite，BL-001 維持 In Progress。
  - 2026-10-28 Dijkstra vendor boundary：已核對原目錄自帶 MIT LICENSE（2019 Doug Mahugh）與 upstream README；將原始 algorithm、LICENSE、README、兩個 sample graph 以相同 Git blob SHA 搬到 `vendor/dijkstra_algorithm_master/`。舊 `text_category_profiler/dijkstra_algorithm_master/dijkstra_algorithm.py` 改為 import-safe 相容入口，舊資料與授權檔保留；graph shortest-path 輸出、舊 module names、direct-run 四個樣例透過 stdlib characterization 確認。外部操作指令仍待盤點，另一項 `Edited_zipfile.py` 的查證和處置另見下一筆；BL-001 仍未結案。
- [ ] 盤點 `- 複製.py`、日期版本、`old_*`、`deprecated` 檔；先比較差異，再整合、測試、歸檔或刪除。

### Phase 4：淘汰 path injection

- [x] 將 active code 的 `from utils...`／`import utils...` 改為 `from text_category_profiler...` 或明確 stage-local import。
- [x] 移除 `text_category_profiler/` package 內部、`TCFMain.py` 與 `TCF_Params/` 對 `PackageImporter.proc()` 的依賴；package layout test 會阻止這些邊界重新匯入 legacy path injector。
- [x] 移除四個 canonical stage entry points（DataConverter、classifier runner、result combiner、visualization）中的 `PackageImporter.proc()`；各入口只由 `__file__` 推導 repository root，其他輔助／legacy scripts 另批處理。
- [x] 移除 visualization layout support module 的 `PackageImporter.proc()`，並以明確的 `from BertScript import reusable_components as rc` 保留既有 stage-local implementation；repository-root bootstrap 仍只由 canonical visualization entrypoint 負責。
- [x] 移除 active PyTorch Transformers classifier backend 中的 `PackageImporter.proc()`；直接執行時只加入由 `__file__` 推導的 repository root。
- [x] 移除 DatasetConverter tree adapter 主動載入的 `ClassesTree/ClassesTree_utils.py` 對 `PackageImporter.proc()` 的依賴；taxonomy/tree 行為與既有檔案解析策略維持不變。
- [x] 移除 legacy/manual `DatasetConverter/DataConverter_Combiner.py` 的 import-time `chdir` 與 `PackageImporter.proc()`；repository 搜尋未發現 canonical production caller 或 active importer。直接執行時以 `__file__` 推導 repository root，並明確將相對的 WorkPool、來源資料、log 與輸出路徑解析至該 root，以保留舊有從 `DatasetConverter/` 啟動時的檔案位置而不改變 cwd。
- [x] 移除 legacy/manual `DatasetConverter/SummarizationExcels_Combiner.py` 的 `PackageImporter.proc()`；repository 搜尋未發現 active caller/importer。只有 direct-script mode 會由 `__file__` 推導並加入 repository root，cwd 不變，因此輸出仍位於 caller cwd 下的 `SummarizationTrain`。
- [x] 移除 legacy/manual `BertScript/TextClassification_XLM.py` 的 `PackageImporter.proc()`；repository 搜尋未發現 active caller/importer，canonical runner 仍使用 Transformers classifier。只有 direct-script mode 會由 `__file__` 推導並加入 repository root，cwd 與既有相對模型、dataset、output 路徑語意不變。
- [x] 移除 legacy/manual `BertScript/writeto_tsv.py` 的 `PackageImporter.proc()`；repository 搜尋未發現 executable caller/importer。Module import 不再產生 dataset，只有 direct-script mode 會由 `__file__` 推導並加入 repository root，再執行既有 workflow；cwd 不變，`data_set_THUC` 與 `THUC_txt` 仍相對 caller cwd。
- [x] 移除 legacy/manual `DatasetConverter/ConverterParameters.py` 的 `PackageImporter.proc()`；canonical `DataConverter.py` 的舊 import 只位於三引號歷史程式與註解，但 repository 搜尋確認 legacy/manual `DataConverter_Combiner.py` 仍有 `try` 內的 executable importer。只有 direct-script mode 會由 `__file__` 推導並加入 repository root，cwd 不變；module import 時的 GPUtil 與 process-count probes 原樣保留。
- [x] 移除 legacy/manual `DatasetConverter/DateChecker.py` 的 import-time cwd mutation 與 `PackageImporter.proc()`；local repository 搜尋只找到 inventory 與歷史 path listing，沒有 executable caller/importer。Module import 不再執行 SQLite/CSV checking workflow；direct-script mode 只以 `__file__` bootstrap repository import，資料路徑則由 caller cwd 的 legacy base 規則解析且不改變 cwd。
- [x] 移除 legacy/manual `DatasetConverter/CorpusMetadataManager.py` 的 `PackageImporter.proc()`；local repository 搜尋只找到 inventory、文件與歷史 path listing，沒有 executable caller/importer。Module import 不再掃描 corpus、備份或連線 SQLite；direct-script mode 只以 `__file__` bootstrap repository import，既有 metadata maintenance workflow 保留在 `main()`，SQLite 檔名與 corpus roots 仍相對 caller cwd。
- [x] 移除 legacy/manual `DatasetConverter/SMS/SMSMerger.py` 的 `PackageImporter.proc()`；local repository 搜尋沒有 executable caller/importer。Direct-script SMS merge workflow 保留在 `main()`，module import 不再執行 batch、SQLite、CSV、DataFrame transformation 或 TSV output；資料與輸出路徑仍相對 caller cwd。`DatasetConverter/SMS/` 沒有 sibling `ClassTable.py`，但 repository authoritative provider 是 `BertScript/ClassTable.py`，因此 bare import 已改為 explicit `from BertScript.ClassTable import ClassTable`。
- [x] 移除最後一個 legacy/manual consumer `ClassesTree/Visualization/jaal/jaalViewer.py` 的 `PackageImporter.proc()`、import-time cwd mutation 與依賴歷史祖先名稱 `TopicClassification` 的 bootstrap。Direct-script mode 只把由 `Path(__file__).resolve().parents[3]` 推導的 repository root 加入 `sys.path`；一般 import 不改 cwd 或 `sys.path`。Jaal taxonomy 明確使用 repository-absolute `ClassesTree/data/TopicTree.csv` 與 `ClassesTree/data/TopicTree_AK4.csv`，不受 caller cwd 同名檔 shadow。Local caller scan 只在 `BertScript/Test_result_Vis.py` 找到註解 import/calls，沒有 executable caller；Jaal-local `TopicTree.csv` 保留為 historical artifact，且該目錄沒有 `TopicTree_AK4.csv`，所以不作為 canonical pair。
- [x] 移除 test/experiment `DatasetConverter/Dataset Generator/ComponentGenerator/ComponentGenerator.py` 的 `PackageImporter.proc()` 與歷史 EXTConverter cwd mutation。Direct-script mode 在第一個 repository-local import 前由 `Path(__file__).resolve().parents[3]` 加入 repository root；普通 import 不改 cwd 或 `sys.path`。Embassy SQLite input 明確綁定 component-local resource 並只在 embassy email 第一次使用時讀取及快取；generated outputs 仍相對 caller cwd。未使用且會讀取 bundled JSON 的 `generate_job_title` import 已移除；bundled implementation 未修改。
- [x] 移除最後一個 test/experiment consumer `DatasetConverter/FreqAnalysis_dash.py` 的 `PackageImporter.proc()` 與 bare provider imports。Direct-script mode 在第一個 repository-local import 前由 `Path(__file__).resolve().parents[1]` 加入 repository root，普通 import 不改 `sys.path` 或 cwd。`reusable_components` 與 `dfOutputer` 分別明確綁定 canonical visualization/data packages；`StrDfFromJson` 以 target-local compatibility function 保留 legacy string/`"None"` semantics。Historical bare `MP_utils` provider was ambiguous；target 改用 repository canonical `MPlogger` instance，並以 `logSubDir=""`、`logFile="mp_processing_log.txt"`、`printOnScreen=False` 明確保留 caller-cwd log destination 與 silent logging behavior。`RandText.txt` input 固定為 DatasetConverter-local resource，而 `"test"` outputs 與 log 仍相對 caller cwd；canonical `dfOutputer` 明確設定 `IndexCols=["text"]` 以保留 legacy SQLite `text_Index`，並停用 canonical Excel 自動欄寬與列高調整。既有 standalone Dash module-scope app/data initialization 原樣保留，app-factory modernization 不在本批範圍。
- [x] 移除 active code 對目前 working directory 深度的 import 假設；application-tree AST guard 排除 direct-run function body，禁止任何 import-time `os.chdir()`。
- [x] 盤點 repository 內所有 `PackageImport.py`；application-side providers 已確認零 consumer 並移除，僅保留獨立 `TRV_deploy` snapshot provider 作為 deployment boundary。
- [x] 確認 application process 不再從 `D:/shared/PythonModule`、`Z:/PythonModule` 或相對深度 `PythonModule` 載入同名模組；application-tree guard 禁止 executable legacy `PythonModule` path literals，deployment snapshot 明確排除。

#### Phase 4 `PackageImport` inventory（baseline `main@2ac40236a697f531755dfcd3fe3c19257e0d8d6c` 加上本批變更）

以下以 repository-wide `rg` 找 filename、model type 與可能呼叫形式，再以 Python AST 辨識 executable `PackageImport` import/call，而非把註解或文件字串當成 caller。Fresh caller scan 確認兩支 deprecated XLM copies 都沒有 executable repository caller、operator documentation 也沒有要求直接執行它們；`RunClassfier.py` 只有一行已註解的舊 `TextClassification_XLM_Pred.py` command。`dir.txt` 是 historical path inventory，而本文與 layout test 是 inventory/guard，都不是 runtime caller。

Production PyTorch runner 由 `classifier_stage.py` 的 `PYTORCH_SCRIPT = "TextClassification_transformers.py"` 與 `render_pytorch_command(...)` dispatch `BertScript/TextClassification_transformers.py`。`BertScript/TextClassification_XLM.py` 是把舊的 train/predict 功能整合在同一 direct-run script 的較新 legacy/manual lineage，並非 production runner。比對 dataset selection、tokenizer/model setup、Trainer training、checkpoint discovery、pipeline inference 與 result output 後，沒有發現兩支 deprecated copies 提供仍被使用、但 active replacement 缺少的獨立必要 contract。因此本批直接刪除 `BertScript/TextClassification_XLM_Pred_deprecated.py` 與 `BertScript/TextClassification_XLM_Train_deprecated.py`，由 Git history 保存歷史，不建立 archive copy、wrapper 或 placeholder。

本批 fresh caller scan 對 `Combiner - 複製.py`、`EmbassyPagesCombiner`、`CZJCorpusFileBuilder`、`CreateCZJCorpusSQL` 及 Python dynamic import/process/shell invocation forms 做 repository-wide 搜尋。沒有 executable Python import、`runpy`、`importlib`、`spec_from_file_location`、`subprocess`、`os.system`、shell/batch/PowerShell command、test 或 operator manual 呼叫該 copy；主要 symbol 的 executable hits 都明確 import 正式 `DatasetConverter.EXTConverter.Combiner`。EXTConverter contract tests 也只對正式 `Combiner.py` 做 import、path 與 behavior assertions。因此本批直接刪除 `DatasetConverter/EXTConverter/Combiner - 複製.py`，由 Git history 保存，沒有 cleanup、archive copy、rename、wrapper 或功能搬移。

本批 actual AST scan 剩餘 2 個 consumer，兩個都是未變更的 deployment snapshot，並有 executable import、在 module import 時呼叫 `PackageImporter.proc()`。Application-side consumer 為 **0**。Canonical active boundaries（`TCFMain.py`、DataConverter、RunClassfier、CombineTestResult、Test_result_Vis、Transformers classifier）、canonical stages 會載入的 active support modules、legacy/manual scripts 與 test/experiment scripts 目前均為 **0** 個 consumer。

| Consumer | 分類 | 已知 caller／entrypoint | 額外 cwd／path side effect | 後續處置 |
| --- | --- | --- | --- | --- |
| `BertScript/TRV_deploy/deploy-dash-with-gcp-master/TRV/main.py` | deployment snapshot | snapshot app entrypoint | `proc()` path injection | deployment boundary |
| `BertScript/TRV_deploy/deploy-dash-with-gcp-master/TRV/PythonModule/utils/Email_utils.py` | deployment snapshot | snapshot utility；由 snapshot 自行維護 | `proc()` path injection | deployment boundary |

分類計數：canonical active **0**、active support/module **0**、legacy/manual script **0**、test/experiment **0**、vendor **0**、deployment snapshot **2**、copy/deprecated **0**、unknown **0**；本批 copy/deprecated consumer **1 → 0**、application debt **1 → 0**、total executable consumers **3 → 2**。`tests/test_package_layout.py` 對 application-zero、2 個 deployment consumers 和 canonical-zero boundary 分別做 AST guard；vendor tree 是明示排除邊界，盤點時未發現 consumer，不是靜默忽略。

| `PackageImport.py` provider | 狀態／consumer 關係 | 後續處置 |
| --- | --- | --- |
| `BertScript/TRV_deploy/deploy-dash-with-gcp-master/TRV/PackageImport.py` | deployment snapshot provider；只服務 snapshot 內既有 consumer | deployment boundary，主程式 migration 不修改 |

Provider inventory 已收斂：原有 **11** 個 provider 中，10 個非 deployment provider 都已沒有 application-side executable `PackageImport` consumer並已刪除；其中 root `PackageImport.py` 雖另含 `set_working_dir_to` 與 `get_relative_path_from_root`，但 application inventory 沒有任何 `PackageImport` import，因此不存在 repository application caller 需要保留該 provider。Git history 作為歷史保存，不建立 wrapper、placeholder 或 archive copy。刪除後 repository 只保留 **1** 個 `TRV_deploy` snapshot provider；兩個 executable consumers 也都侷限在同一 deployment snapshot。Hosted recursive tree `main@2ac40236a697f531755dfcd3fe3c19257e0d8d6c` 回報 `truncated=false`，所有 repository `PythonModule/` entries 與唯一 `PackageImport.py` 都只存在於該 `TRV_deploy` tree。另以 hosted raw source 分批掃描全部 **239** 個 application `.py`（排除 `TRV_deploy` 與既有 vendor boundary）；除兩個 0-byte `dash-cytoscape` `__init__.py` 無內容可讀外，其餘來源均完成檢查。掃描實際抓到兩個 Phase 4 殘留：`text_category_profiler/integrations/Email_utils.py` 仍建立 machine-specific `PythonModule` search paths，以及 `text_category_profiler/text/similarity_utils.py` 仍在 module import 時依 cwd 執行 `os.chdir()`。本批已移除前者整段 path injection，後者改為僅 direct-script mode 使用 `Path(__file__).resolve().parents[2]` 的 repository-root bootstrap，不再改 cwd。其他 `os.chdir()` raw hits 位於 stage/runtime/diagnostics functions，不在 module import 階段執行。`tests/test_package_layout.py` 以 application-tree AST/source guard 固定禁止 executable legacy `PythonModule` path、application import/reference `TRV_deploy`，以及 import-time `os.chdir()`。Phase 4 source-layout checklist 因此完成；`BL-001` 仍為 **In Progress**，待 Phase 5 的 legacy-container/docs 同步與最終輕量測試收尾。`KI-002` 維持 **Resolved**，`KI-003` 維持 **Open**；本批沒有進行 H100/CUDA acceptance。

### Phase 5：刪除 legacy 容器並同步文件

- [x] 確認 application executable imports 不再使用 `PythonModule`、頂層 `utils`／`tcf_utils` 或 `PackageImporter`；`tests/test_package_layout.py` 保留這些名稱僅作 inventory／防退步 guard，deployment snapshot 明確排除。
- [x] 確認部署副本若仍需舊結構，已有獨立且清楚的維護邊界，不會被主流程 import；recursive hosted tree 與 application import guard 將 `TRV_deploy` 固定為獨立 legacy island。
- [x] Application tree 已無 `PythonModule/` container；唯一剩餘 `PythonModule/` 位於隔離的 `TRV_deploy` snapshot。Migrated package-root compatibility copies 由 layout guard 保證不存在，不另建立 placeholder／shim。
- [x] 同步 README、AGENTS Quickstart、`.codex/project.md`、`.codex/architecture.md`、`.codex/contracts.md` 與 `.codex/workflows.md` 的 current-state 邊界；contracts/workflows 本批查核後無 path migration 必要變更。
- [ ] 完成 Phase 0–3 尚未收斂的 package-root residual inventory（research/test/script/vendor/legacy artifact），再取得 fresh dependency-light suite 證據；之後將 `.codex/backlog.md` 的 `BL-001` 標記為 `Done`，並在 `.codex/memory.md` 留下最終驗證摘要。

## 每批驗證清單

- [ ] 執行該批模組的針對性 unit tests。
- [ ] 執行 `python -m unittest discover -s tests`。
- [ ] 對修改的 Python 檔執行 `python -m py_compile <files...>`。
- [ ] 執行 `git diff --check`。
- [ ] 使用 `rg` 確認舊、新 import 數量符合該批預期。
- [ ] 人工檢查 diff 沒有意外搬入資料、模型、輸出、秘密或無關格式化。

## 整體完成條件

- `text_category_profiler` 只包含責任明確、確實跨 stage 使用的 helper。
- active imports 不再仰賴 `sys.path` 注入或 working-directory 切換。
- `PythonModule/` 已從主程式邊界移除，且沒有未解決的雙份權威實作。
- 既有 CLI、stage handoff、dataset 與結果檔案契約未改變，或任何必要改變已另立 contract migration。
- 輕量測試全數通過；需要模型、資料或外部服務的未執行驗證已明確記錄。

## 非本計畫範圍

- 一次將整個 repository 改為 `src/` layout。
- 同時重寫模型訓練、推論、資料轉換或 Dash UI 行為。
- 未經查證直接刪除第三方原始碼、deployment snapshot、歷史副本或資料 fixture。
- 僅為符合新命名而建立空 package、假測試或 silent fallback。
