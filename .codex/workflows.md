# Development Workflows

> 類型：Current state。保存可重現的安裝、執行與驗證方式。Codex 不得執行尚未查證的占位命令。

## 環境前提

| 項目 | 要求 | 查證來源 |
| --- | --- | --- |
| 作業系統 | 待確認；程式含 Windows 與 Linux 分支 | `TCFMain.py`, `TCF_Params/TCFParameters.py` |
| Runtime 版本 | Python 版本待確認；BertScript 要求 TensorFlow >= 1.11.0 | `BertScript/requirements.txt` |
| 套件管理器 | `pip` 可讀取根目錄 `requirements.txt`；尚無 lockfile | `requirements.txt`, `rg --files` 盤點 |
| 必要本機服務 | 主要流程需要本機資料／模型／工作池；Elasticsearch 只在部分工具中出現 | `TCFMain.py`, `text_category_profiler/ES_ingest_txt_to_es.py` |
| 必要環境變數 | 一般根流程無必要環境變數；完整 pipeline smoke profiles 由下列 opt-in 環境變數啟用 | `tests/test_full_pipeline_smoke.py`, `tests/test_full_pipeline_real_runtime.py` |

## Canonical Commands

| 用途 | 命令 | 工作目錄 | 狀態／最後查證 |
| --- | --- | --- | --- |
| 安裝／同步依賴 | `python -m pip install -r requirements.txt` | repository root | Command documented；未在容器執行，因會下載/安裝大量 ML dependencies |
| 啟動主流程 | `python TCFMain.py --WeiTechworkIDPath <path> --WeiTechWorkPoolPATH <path> -p 8099999 -TRVHost False -task SDSMS_Prediction` | repository root | Command shape verified from `TCFMain.py` comments；會讀寫資料，初始化未執行 |
| 生產資源診斷 | `python TCFMain.py --doctor` | repository root | Activation-free、read-only preflight；無 FAIL 時 exit 0，缺少本機模型／FixedTest／TopicTree／PyTorch 時會指出 failure boundary 並 non-zero |
| CUDA 必要診斷 | `python TCFMain.py --doctor --require-cuda` | repository root | 與一般 Doctor 相同，但 CUDA unavailable 為 FAIL；availability 不等於 classifier GPU execution evidence |
| 隔離完整流程自測 | `python TCFMain.py --self-test isolated` | repository root | Temporary WorkPool/model copy、PytorchXLM fixture、只攔截 inference；structured output |
| 真實 runtime 自測 | `python TCFMain.py --self-test real -p 8059` | repository root | Production default PytorchMMBERT 與 real classifier；temporary mutable state |
| CUDA classifier acceptance | `python TCFMain.py --self-test real -p 8059 --require-cuda` | repository root | 實際 classifier 必須明確回報 device=cuda:<n> |
| 單獨資料轉換 | `python DatasetConverter/DataConverter.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| 單獨分類 | `python BertScript/RunClassfier.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| 單獨結果合併 | `python BertScript/CombineTestResult.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| 單獨視覺化分析 | `python BertScript/Test_result_Vis.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| Jaal standalone GitHub 套件相容與來源 | `python -m unittest -v tests.test_jaal_topology_portable tests.test_jaal_external_source_contract tests.test_jaal_original_mount`；`node --test tests/jaal_visible_labels.test.cjs tests/jaal_structural_collapse.test.cjs` | repository root（安裝固定 SHA 的外部 `jaal-topology-viewer`） | `requirements.txt` 使用經驗證的 `hun186/jaal-topology-viewer` Git Commit；Hosted `Portable Jaal Topology Package` 和 `Stage 4 Original Jaal Same-Port Compatibility` 安裝外部套件後運行；不再讀取 `packages/jaal-topology/`，Stage 4 仍保留特製控制面板與同埠嵌入。外部專案自身 CI 須獨立 PASS，Windows 瀏覽器 UX 待現場驗收。 |
| Stage 4 一鍵唯讀 Doctor（跨機器） | Windows：`run-stage4-doctor.bat`；完整 Stage 4：`python BertScript/Test_result_Vis.py --doctor --mode full --model-type PytorchMMBERT --workpool WorkPool`；僅 Jaal：`python BertScript/Test_result_Vis.py --doctor --mode viewer --probe-jaal`；歷史結果：`python BertScript/Test_result_Vis.py --doctor --mode history --workpool WorkPool` | repository root、啟動服務的相同 Python 環境 | 快速檢查 Python、Dash、comm、visdcc、jaal／portable viewer、完整 Stage 4 的 Tulip 與 Windows `PATH`、工作池資料夾狀態；`--probe-jaal` 額外建構 Jaal（不開 port）。回報 PASS 代表已知的靜態相依與資料夾條件符合，不能取代 Native DLL、模型或瀏覽器實測；不安裝套件、不寫入 SQLite／WorkPool、不變更階段；附 `tests.test_stage4_doctor` 無依賴測試。 |
| Windows Stage 4／Tulip PATH 智慧處理 | Windows 完整主流程 `python TCFMain.py ...`；單獨 Stage 4 `python BertScript/Test_result_Vis.py ...`；先檢 `run-stage4-doctor.bat --mode full`；若仍有其他相對 DLL 路徑則在同一 CMD 手動檢查 | 啟動正式流程所用的 Windows Anaconda Prompt、repo root | 同一 `execution.process` 函式自動移除 `.`、`.\\`、`./`、`.\\.` 等**僅代表當前目錄**的 PATH 條目，保留其他原文和順序；TCFMain 的測試推論路線在 activateArguments／Stage 1 前完成處理與 fail-fast，Stage 4 直接執行在重型 import 前重做，lazy Tulip 真正使用前再檢；不修改父 CMD／Windows 系統 PATH。其他相對路徑 fail-closed，且不擅自更動 PATH 項目的相對語意。Doctor 唯讀模擬並 WARN。早期 TCFMain 的 `;.;` → `;\\.;` 字串替換已廢除。可由 `python -m unittest -v tests.test_process_runner tests.test_tcf_main_characterization tests.test_visualization_stage tests.test_stage4_doctor` 驗證；Hosted CI 不代表 Windows DLL 及完整瀏覽器驗收。 |
| Stage 4 Combine 後啟動失敗的安全恢復 | 確認目標 `WorkPool/dataset_<timestamp>_<ModelType>_pt<port>_rdy_for_TestResultVis` 仍存在，使用**原執行記錄**中 `python BertScript/Test_result_Vis.py ...` 命令，額外指定 `--BertDatasetSubDir` 與 `--modelDir` 以鎖定正確工作區與模型 | Windows Anaconda Prompt、repo root；不可重跑 `TCFMain.py` 或手動修改 WorkPool 階段名 | 本次 `PATH` 問題在 Stage 4 main／rename 之前即失敗，原 Combine 結果應可直接沿用；重試前確認目錄仍為 `_rdy_for_TestResultVis`。正式 Stage 4 非唯讀，啟動後會按既有流程進行 WorkPool handoff；若已為 `_is_running_TestResultVis` 應先檢查日誌及程序，不要自動改名。參考 `KI-010`。 |
| Jaal 唯讀 GUI（免 WorkPool） | `python BertScript/Test_result_Vis.py --viewer-only -p 8059`；Windows 可直接執行 `run-jaal-viewer-only.bat` | repository root | 本機 `127.0.0.1:8059` 只顯示 Jaal 進階檢視器；不載入完整 Stage 4 統計分析、不重新命名 `_rdy_for_Spike` 或其他工作池資料、Ctrl+C 不推進階段。Hosted `tests.test_jaal_viewer_only` 與 real Jaal WSGI smoke 驗證；Windows 畫面待實測 |
| Stage 4 已完成結果唯讀分布預覽 | `run-stage4-history-preview.bat` 或 `python BertScript/Test_result_Vis.py --history-preview --workpool WorkPool -p 8060` | repository root；只讀 `_rdy_for_Spike` 或明確確認停止寫入的 `_is_running_TestResultVis` 目錄 | 可選擇歷史工作區、兩類已存 SQLite、資料表和欄位，顯示最多前 **5,000 列**的前 **15 種**「欄位值前 120 字元前綴」出現次數長條圖；超長不同原始值若前綴相同會合併計數，介面會揭露截斷筆數，不能冒充完整原始值的精確去重；若還有更多列會標註「非全量統計」，不推論整體分類比例。SQL identifier 採 schema 白名單＋引號、唯讀 immutable SQLite、WAL/journal sidecar fail-closed；不執行模型、WorkPool rename 或分類輸出。與原版完整 Stage 4 分析／圖表仍有落差；Hosted 測試非 Windows 瀏覽器實機驗收。 |
| Stage 4 內嵌分類樹 | `python -m unittest -v tests.test_embedded_tree_data tests.test_embedded_tree_panel` | repository root | Hosted Stage 4 Embedded Lazy Taxonomy Graph 安裝 `dash` + `dash-cytoscape`，只測有界查詢、空白初始 canvas、明確全圖同意、Dash callback 註冊；不啟動 Jaal port 或完整模型／真實瀏覽器 |
| AI ClassTable candidate provenance + optional graph node alignment (BL-002) | `python -m BertScript.class_table_ai_proposals --candidates <candidate.csv> --json`; `python -m unittest -v tests.test_class_table_ai_proposals` | repository root | Pure stdlib, read-only; optional evidence manifest JSON 由 object_pairs_hook 在所有巢狀層級拒絕重複 key（避免 last-key-wins 隱藏 articles/source），其他 SHA256、來源與候選 Notes 精確綁定維持不變；不自動合併／核准，Hosted ClassTable workflow 執行 focused tests，但不會實際爬文或驗證來源真實性 |
| BL-001 canonical Excel 空 DataFrame 自動欄寬保全 | `python -m unittest -v tests.test_bl001_df_list_xls_sheet_names`；Hosted pandas 2.2.3／3.1.1 matrix | repo root，私有 pandas/xlsxwriter XLSX；不讀寫正式 WorkPool | `dfListToXLS(AutoAdjustColWidth=True)` 的空欄位 Series `.max()` 原為 NaN，可能寫出 XLSX 欄寬 `width="nan"`。僅零列時改用原有欄名長度加一的底限；非空欄位仍依既有最長內容／欄名規則與 `MaxColWidth` 上限。私有 XLSX XML 測試拒絕 NaN／Infinity 欄寬，並測試非空上限。仍待 Windows 實機驗收。 |
| BL-001 canonical Excel 列高調整時保全輸入 DataFrame | `python -m unittest -v tests.test_bl001_df_list_xls_sheet_names`；Hosted pandas 2.2.3／3.1.1 matrix 覆蓋 | repo root；AST fake writer、私人暫存 XLSX，無正式資料 | `dfListToXLS(AutoAdjustRowWidth=True)` 原本在寫完工作表後對原始 DataFrame 做 `smart_reset_index(..., inplace=True)`，會改變索引／欄位；現用 `df.reset_index(drop=True)` 或 `df.reset_index().rename(...)` 的非 inplace 轉換做同一列高計算，避免 pandas 3.1.1 舊 `inplace` 警告，保持原公式和設定的 Excel 列高，回傳前不變更呼叫端 DataFrame。fake writer 驗證只處理複本，真實 pandas／xlsxwriter 驗證 RangeIndex 與具名 index 的原 DataFrame 不變及 worksheet 存在列高設定；不證明 Windows／WorkPool。 |
| BL-001 canonical 多工作表 Excel 行數上限含標題列 | `python -m unittest -v tests.test_bl001_df_list_xls_sheet_names`；Hosted pandas 2.2.3／3.1.1 | repo root；FakeFrame 只偽造 `shape=(1048575, 2)`／`(1048576, 2)`，不配置百萬筆資料，不接觸 WorkPool | 因 `dfListToXLS` 固定輸出標題列，單張工作表 1048576 列的 Excel 上限實際最多允許 1048575 筆資料；保留既有超量跳過／列印提醒／其餘工作表繼續輸出行為。驗證門檻邊界、被略過頁籤不消耗呼叫端名稱、writer 關閉；這不保證批次所有頁籤都寫出，正式呼叫端應檢查提醒並做輸出驗收。 |
| BL-001 canonical 多工作表 Excel 欄數含索引層級 | `python -m unittest -v tests.test_bl001_df_list_xls_sheet_names`；Hosted pandas 2.2.3／3.1.1 | repo root，shape-only FakeFrame 模擬至 XFD 欄，無大型 XLSX 或 WorkPool | Excel 每頁最多 16384 欄，`dfListToXLS` 須將輸出的索引欄數（含 MultiIndex 的每個 level）加進 `df.shape[1]`；超量時在資料寫入前 `ValueError` fail-closed 並關閉 writer，避免被 xlsxwriter 悄悄丟棄右側資料。測試不配置 1.6 萬欄的實體 DataFrame；這是欄位數的邊界契約，不代表超大實體檔案驗收。 |
| BL-001 canonical 多工作表 XLSX 失敗後 writer 收尾 | `python -m unittest -v tests.test_bl001_df_list_xls_sheet_names`；Hosted `BL-001 Stage Writer Compatibility` pandas 2.2.3／3.1.1 | repo root；FakePandas/Frame 無檔案副作用，實際 XLSX 僅 tempfile | `dfListToXLS` 寫入第二張工作表或調整格式拋錯時，仍需呼叫一次 `ExcelWriter.close()`；若 close 同時失敗，保留主要輸出錯誤，正常輸出仍應讓 close 例外傳出。不能將中斷後磁碟上可能殘留的 XLSX 視為成功或原子輸出；本項不保證刪除部分檔案，也不取代 Windows／WorkPool 驗收。 |
| BL-001 canonical 多工作表自動命名衝突預防 | `python -m unittest -v tests.test_bl001_df_list_xls_sheet_names`；Hosted pandas 2.2.3／3.1.1 | FakeWriter 無磁碟，真實 XLSX 僅私有 tempfile | `sheetNameList` 指定 `AutoSheetName1`／大小寫相同名字時，剩餘自動生成頁籤需跳過所有既有使用者名稱（Excel 比對大小寫不敏感），而不是在後續產生重複工作表名而失敗；保留原有明確指定順序與內容，不自動修改使用者重複或無效名稱。FakeWriter 與真實 XLSX XML 驗證自動名稱無碰撞。 |
| BL-001 canonical 多工作表 Excel 名稱清單保全 | `python -m unittest -v tests.test_bl001_df_list_xls_sheet_names`；Hosted `BL-001 Stage Writer Compatibility` 的 Python 3.11／pandas 2.2.3、3.1.1 matrix 同時驗證 | repo root；AST 隔離注入 fake writer，選用 pandas + xlsxwriter 只寫私人 tempfile | `data.df_utils.dfListToXLS` 原本以 `sheetNameList.reverse()`／`pop()` 改動呼叫端清單；僅改成內部反轉複本，保留名稱順序、剩餘自動命名、原有 writer/options 與公開簽名。驗證重複呼叫、額外頁籤、預設值、例外不修改輸入，並讀取實際 XLSX workbook XML；不操作正式模型、WorkPool 或真實輸出。 |
| BL-001 canonical TSV pandas 3 相容驗證 | `python -m unittest -v tests.test_bl001_df_tsv_provider_contracts`；Hosted `BL-001 Stage Writer Compatibility` 的 Python 3.11 + pandas 2.2.3／3.1.1 matrix 另跑這組測試 | repo root；FakeMulticore 而非真實 WorkPool／模型資源 | `text_category_profiler.data.df_utils.dfToTSV` 保留原多程序資源探測、可選 TSVTextAdapter、index/header、UTF-8／TAB／`QUOTE_NONE`／反斜線規則；僅將 `quotechar=""` 改 `None`，在私人 tempfile 以中文、Tab、換行、反斜線驗證成功輸出 bytes 與 Stage-local 相同、舊 pandas 原輸出可比較、擴充參數仍有效。Canonical provider 其餘語意不等同 Stage-local；不算 Windows 真實並行/WorkPool 驗收。 |
| BL-001 一鍵 Stage-local TSV/XLSX/SQLite 相容快檢 | Windows `run-bl001-stage-writer-check.bat`；跨平台 `python -m scripts.bl001_stage_writer_check`；runner tests `python -m unittest -v tests.test_bl001_stage_writer_check` | repo root、與正式環境相同的 Python；不傳 WorkPool／DB 路徑 | 必須可匯入 pandas 與 xlsxwriter，才執行 Stage-local TSV/XLSX/SQLite、canonical TSV（隔離多程序 probe）及 canonical 多工作表 XLSX（名稱、列高、空資料欄寬）的五組測試（私有 tempfile SQLite/XLSX），**另外要求真實 Stage-local TSV 私有暫存檔成功寫出並符合內容**，不可把 pandas 3.x 的舊行為錯誤等價視為成功；缺依賴、無測試、SKIP、FAIL 皆不回報 PASS。`STATUS=PASS_FOCUSED` 僅表示此環境 focused 測試通過，不代表 Windows GUI、WorkPool、真實 DB 鎖競爭或模型完整驗收；Hosted `BL-001 Stage Writer Compatibility` 用 Python 3.11、pandas 2.2.3／3.1.1 matrix 和 xlsxwriter 3.2.9 走相同入口；Stage-local TSV 的 `QUOTE_NONE` 改用 `quotechar=None`，以相同 UTF-8 實際 bytes 證明舊版不變、新版可寫。只驗證這兩個版本，不推論所有 pandas 版本。 |
| BL-001 Stage-local SQLite schema 唯讀預檢 | `python scripts/bl001_stage_sqlite_audit.py --db "<quiescent-copy.sqlite3>"`；`python -m unittest -v tests.test_bl001_stage_sqlite_audit` | repository root；只使用停止寫入後另存的**私人複本**，無正式 WorkPool | 固定 `sampleSrc.text`、`text_Index` 真正的 `text` 索引欄位與原生非唯一、非部分、升冪 BINARY 索引語意（拒絕 UNIQUE、partial、DESC、NOCASE 等替代索引），使用 immutable/read-only SQLite 僅查 schema，不讀資料列、不寫資料；WAL／journal sidecar、缺檔、錯誤索引與無效 DB 均 FAIL，exit 1，PASS exit 0。Hosted tempfile 測試不等於真實磁碟交易、並發、Windows 或 WorkPool 驗收。詳見 `docs/release-prep/bl001-stage-local-sql.md`。 |
| BL-001 Windows 跨程序 SQLite 鎖與解鎖／持鎖程序終止測試 | Windows `run-bl001-sqlite-lock-check.bat`；跨平台 `python -m scripts.bl001_stage_sqlite_lock_acceptance`；回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_lock_acceptance` | repo root、實際 pandas/sqlite3 Python 環境；**無外部路徑參數**，只用私人 TemporaryDirectory SQLite | 真實 `data.stage_sql.write_stage_sql` 寫入並驗證 `sampleSrc` / `text_Index` 與資料完整性；第二程序持有 `BEGIN EXCLUSIVE`，確定 writer 在短 timeout 被鎖阻擋、既有列不變，分別測正常解鎖及強制終止**持鎖程序**後重試成功、資料及 index 可重讀。CLI 只輸出 JSON PASS／FAIL／BLOCKED，失敗非零。**不能**宣稱中斷寫入程序的跨 `replace`/`CREATE INDEX` 交易原子性、安全並行正式 WorkPool；2026-11-16 使用者 Windows/Anaconda 實機回報五項檢查全部 PASS，私人 tempfile only；**仍不證明**中斷 writer 原子性。 |
| BL-001 SQLite writer 中途終止原子性診斷（私人測試） | Windows `run-bl001-sqlite-atomicity-probe.bat`；跨平台 `python -m scripts.bl001_stage_sqlite_atomicity_probe`；回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_atomicity_probe` | repository root，實際 pandas/sqlite3；**無外部 DB 路徑參數**，私人 TemporaryDirectory／單一 child writer；Windows/Anaconda 2026-11-16 原版 private tempfile 實測 FAIL_ATOMICITY；正式原子修復分支須以 PASS_ATOMICITY 重新 Windows UAT（符合已知缺口，不代表正式 WorkPool 受損） | 正常 seed 原始 `sampleSrc` 與 `text_Index`；子程序在 `to_sql(if_exists=replace)` 返回、`CREATE INDEX` 執行之前寫入同步標記並暫停；母程序強制終止**寫入程序**，用新連線確認資料庫 integrity、舊列是否原樣保留以及 `text_Index` 是否仍存在。`PASS_ATOMICITY` 代表此單一中斷點舊資料保全；`FAIL_ATOMICITY` 表示不完整的寫入已可見，exit 1（非工具失靈）；`BLOCKED_DIAGNOSTIC` 表示環境阻擋，同為 exit 1。測試模組驗證**診斷工具**的判別邏輯，不會把 `FAIL_ATOMICITY` 當成 writer 通過。不能證明所有中斷點、真正生產 WorkPool、網路磁碟或多程序交易安全；不改現行 writer。 |
| KI-012 SQLite transaction-first final swap、索引相容與 Windows 完整私人驗收 | Windows `run-bl001-sqlite-atomic-fix-check.bat`；跨平台 `python -m unittest -v tests.test_bl001_stage_sql_atomic_fix tests.test_bl001_stage_sql_shared tests.test_bl001_df_sql_provider_contracts`；再執行 `python -m scripts.bl001_stage_sqlite_atomicity_probe` 與 `python -m scripts.bl001_stage_sqlite_lock_acceptance` | repository root；新建私人 temp SQLite、真實 pandas、子程序中斷與跨程序鎖；無正式 WorkPool 路徑參數；2026-11-16 Windows/Anaconda 私有 DB：21 tests OK、PASS_ATOMICITY、lock PASS、PASS_KI012_PRIVATE；正式 WorkPool 未驗收 | 以 pandas 先寫候選表；SQLite `BEGIN IMMEDIATE` 單次 commit 刪除／重建 sampleSrc、複製候選資料（依賴 sampleSrc 的 View 不可中斷）及保留 `ix_sampleSrc_*` / `text_Index`。測試預設／具名／MultiIndex／空資料實際 schema、Unicode、其他表保全、重覆 replace、交易期間注入失敗 rollback，並殺死 writer 驗證原表保留、原子性狀態 PASS_ATOMICITY；既有 CLI 鎖測試 PASS。此批仍可能於 writer 突然終止後留下獨有候選表，禁止自動刪除其他 worker 的候選表；不等於正式 WorkPool、內網或 GPU 驗收。 |
| KI-012 Windows 多程序重疊／中斷後候選表保全（私人測試） | Windows `run-bl001-sqlite-overlap-check.bat`；跨平台 `python -m scripts.bl001_stage_sqlite_overlap_acceptance`；測試 `python -m unittest -v tests.test_bl001_stage_sqlite_overlap_acceptance` | Repository root、pandas/sqlite3；**僅 TemporaryDirectory、新建私人 SQLite，無 --db 或正式 WorkPool 路徑** | 兩個真正 Python 程序共用私人 DB：① writer A 已提交候選表、在 BEGIN IMMEDIATE 前暫停，writer B 成功切換，強制終止 A 後 B 的正式資料與索引不變，孤兒候選表可見且後續 writer 不擅刪；② writer A 持有交易鎖且在 text_Index 建立前暫停，B 被 lock 拒絕，殺死 A 後正式資料與索引回滾，後續重試成功且不擅刪候選。`status=PASS` 代表只在指定兩個干預點成功，無清理策略或正式 WorkPool 保證。2026-11-16 Windows/Anaconda 實機六項全部 PASS，兩種中斷各留下 1 張候選表；不得因 CI 通過宣稱生產並行完整驗收。 |
| KI-012 私人 SQLite 寫入效能量測 | `run-bl001-sqlite-perf-check.bat` 或 `python -m scripts.bl001_stage_sqlite_performance_profile --rows 1000 --rounds 2`；測試 `python -m unittest -v tests.test_bl001_stage_sqlite_performance_profile` | 僅 TemporaryDirectory 兩份私人 SQLite，最大 20000 rows / 3 rounds，不接受 DB 路徑 | 量測 legacy 非原子兩段與新版 atomic 的單輪耗時、完成後檔案大小、列數及 text_Index/integrity；不能當作正式 WorkPool 時間、瞬時磁碟尖峰或 SLA。2026-11-16 Windows/Anaconda 實測 `PASS_MEASURED`：1000 rows × 2 rounds，atomic `0.02638/0.027866s`、legacy `0.024825/0.028017s`，耗時比 `1.027`；完成 DB 487424 vs 319488 bytes（+52.6%）。**不是**瞬時磁碟尖峰或正式環境效能認證。 |
| KI-012 私人 SQLite 多程序壓力測試 | `run-bl001-sqlite-parallel-stress.bat` 或 `python -m scripts.bl001_stage_sqlite_parallel_stress --workers 3 --rounds 2 --rows 50`；回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_parallel_stress` | 只用私人 TemporaryDirectory DB，2-4 子程序、1-3 rounds、5-500 rows/writer，不接受 DB 路徑 | 真子程序同時寫入，允許正當 lock 拒絕，但至少一位成功並確定最後列屬單一已完成 writer、View/schema/index 完整、無正常路徑候選殘留。不代表正式 WorkPool 或網路共享磁碟可安全併發。2026-11-16 Windows/Anaconda 實測 `PASS`：3 workers × 2 rounds × 50 rows，兩回合各 3 committed／0 locked，winner r0-w1、r1-w0；最終資料完整，但不等於同時持鎖、長時間壓力或正式 WorkPool 合格。 |
| KI-012 離線候選表結構分流 | `run-bl001-sqlite-candidate-triage.bat --db "<quiescent-offline-copy.sqlite3>"`；回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_candidate_triage` | 非 WorkPool 路徑、已靜止且無 WAL/journal 的獨立 SQLite 複本，只查 metadata | 顯示前 20 張 `__bl001_stage_` 候選表的 text 欄位與 pandas 具名／MultiIndex 索引結構，拒絕 WorkPool 目錄。候選表即使 schema 完整也 **owner UNKNOWN / safe_to_delete=false**，不得執行 DROP、VACUUM 或推斷 orphan。Windows 實測未回報。 |
| KI-012 一鍵私人發布前快檢 | `run-bl001-sqlite-release-preflight.bat`（不載入模型，輸出 `PASS_PARTIAL_NO_REAL_MODEL`，exit 2）；或 `run-bl001-sqlite-release-preflight.bat --real-port 8050`（僅已配置真實模型時）；回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_release_preflight` | 根目錄、私有 SQLite probes 和 TCFMain disposable self-test；不允許正式 WorkPool 路徑；真實模型明確 opt-in | 聚合 writer 契約、強制中斷原子性、lock、overlap、私人 perf、parallel、isolated root；real 有 opt-in 且全 PASS 時只回報 `PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION`。任一必需子模組不存在或失敗則 FAIL。**即使 exit 0，正式 WorkPool／網路磁碟／備份回復及部署仍未驗證**；Windows 一鍵驗收未回報。 |
| KI-012 候選表唯讀盤點（**只在停止寫入的離線 SQLite 複本**） | Windows `run-bl001-sqlite-candidate-inventory.bat --db "<offline-quiescent-copy.sqlite3>"`；跨平台 `python -m scripts.bl001_stage_sqlite_candidate_inventory --db <offline-copy>`；回歸 `python -m unittest -v tests.test_bl001_stage_sqlite_candidate_inventory` | 只使用已停止寫入、單獨複製且無 WAL/journal/SHM sidecar 的 SQLite；`immutable=1` + read-only + PRAGMA query_only；正式 WorkPool/活躍 DB **不得**傳入。 | 只查 sqlite_master 中表名與既有 sampleSrc/text_Index schema，精確辨認 `__bl001_stage_` + 32 hex；最多顯示前 20 名及總數，格式異常前綴另列出。無候選 `PASS_NO_CANDIDATES`/exit 0，候選或可疑前綴 `REVIEW_REQUIRED`/exit 1，缺檔／sidecar／非法DB／正式 schema 無法驗證 `UNVERIFIABLE`/exit 2。名稱**不能區分孤兒／仍活動的候選表**，無 row-scan、DROP、VACUUM、清理或安全刪除許可。新 CLI Windows UAT 待確認。 |
| BL-001 SQLite 交易式候選表切換可行性／索引命名差異 | `python -m unittest -v tests.test_bl001_stage_sql_shadow_feasibility` | repo root；僅私人 TemporaryDirectory SQLite、pandas，**非正式 stage writer** | 測試「pandas 先建候選表／BEGIN IMMEDIATE 內 drop＋rename＋建 text_Index／rollback」可保留舊 sampleSrc/索引及其他表，同時證明直接 rename 後 pandas 自動建立的 `ix_<candidate>_index` 名稱不等同 `ix_sampleSrc_index`；候選表失敗後可能殘留。不處理正式資料、多程序或全部索引相容性，不宣稱 KI-012 已修復。 |
| BL-001 兩個 Stage-local SQLite writer 整合及 close 保護 | `python -m unittest -v tests.test_bl001_df_sql_provider_contracts tests.test_bl001_stage_sql_shared tests.test_bl001_sqlite_memory_contract tests.test_bl001_package_census tests.test_bl001_canonical_import_audit`；`python -m unittest discover -s tests` | repository root；私有記憶體與 tempfile 磁碟 SQLite，不碰正式 WorkPool | 原 `DatasetConverter`／`BertScript` 固定 `sampleSrc` replace 和 `text_Index` 集中為 `data.stage_sql`，保持原兩個入口；**新加 try/finally close 是行為修正**；2026-11-11 後續的 `KI-011` 因 SQLite DQS 對遺失 `text` 欄位可能默認建立錯誤索引，改為在連線前拒絕缺欄；`tests.test_bl001_stage_sql_shared` 以私有磁碟檔驗證反覆 replace、真正 `text_Index`、無效輸入不連線且 DB 位元組不變。仍須內網檔案鎖、跨平台和 WorkPool 實測，且此高風險修正的 Merge 須額外明確授權。canonical `data.df_utils.dfToSQL` 有不同 JSON/schema/索引政策，未合併。詳見 `docs/release-prep/bl001-stage-local-sql.md`，Hosted PASS 不代表磁碟資料／交易／WorkPool 實機通過。 |
| BL-001 兩個 Stage-local XLSX writer 共用格式 | `python -m unittest -v tests.test_bl001_df_xls_provider_contracts tests.test_bl001_stage_xlsx_shared tests.test_bl001_package_census tests.test_bl001_canonical_import_audit`；`python -m unittest discover -s tests`；`python -m py_compile text_category_profiler/data/stage_xlsx.py BertScript/df_utils.py DatasetConverter/df_utils.py` | repository root；依賴完整 pandas、xlsxwriter 的實機匯出應額外在內網驗證 | 重構僅保留兩個 `dfToXLS` 的舊固定 `xlsxwriter` 行為與錯誤，canonical `data.df_utils.dfToXLS` 的 ExcelWriter/fallback 尚未合併；新版 pandas 不支援舊 `encoding` 參數；共用 writer 以 inspect.signature 只在移除該參數的新版方法上省略 encoding。CI 需驗證新舊簽名、無錯誤重試、真實 pandas + xlsxwriter 的工作表內容；內網匯出實機驗收另行檢查。部署候選說明：`docs/release-prep/bl001-stage-local-xlsx.md`。 |
| BL-001 Stage 4 explicit reusable-components import | `python -m unittest -v tests.test_bl001_labelviewer_provider tests.test_bl001_canonical_import_audit` | repository root | 靜態 AST 與 stub component 保證 Stage 4 6 個使用中 `rc` API 屬於 `BertScript` provider、無剩餘 canonical-basename bare imports；不代表 Windows/Dash 真實瀏覽器驗收 |
| ClassTable metadata validator | `python -m BertScript.class_table_metadata validate --json` | repository root | Hosted CI 在 PR #127 初版 HEAD 驗證通過；不一致的 graph sets 僅 warning，`--strict-tree` 才視為失敗 |
| ClassTable Notes provenance / AI future proposal | `python -m unittest -v tests.test_class_table_metadata`；`python -m BertScript.class_table_metadata validate --json`；`python -m py_compile BertScript/class_table_metadata.py BertScript/migrate_class_table.py`；Hosted `ClassTable CSV Metadata Contract` workflow additionally verifies historical migration and 1,994-row output | `ClassLabel,CT,Explanation,Notes` 順序固定、空 Notes 與 AI 文字/引號/逗號/換行 round-trip 保全，舊 CT/Explanation strict migration replay；Notes 並非 AI 自動 merge 核准。 |
| ClassTable dependency-light tests | `python -m unittest -v tests.test_class_table_metadata` | repository root | Hosted ClassTable workflow 有此測試；不等同完整 ML acceptance |
| Format | 待確認，禁止執行 | repository root | Unverified |
| Lint | 待確認，禁止執行 | repository root | Unverified |
| Type check | 待確認，禁止執行 | repository root | Unverified |
| Lightweight discovery | `python -m unittest discover -s tests` | repository root | Canonical discovery entry；Layer A／B modules 未 opt in 時明確 SKIP。PR #145 Hosted Python 3.11 全新 targeted test dependencies 下已實跑 912 tests、OK（2 opt-in SKIP），證據 GitHub Actions run `41024022467`；`GPUtil`、`pymongo`、`elasticsearch`、`pytz` 均明確安裝，但未驗收完整 root requirements 安裝或真實模型／H100／WorkPool |
| 完整 test suite | 待確認，禁止執行 | repository root | Unverified：未找到 CI 或 canonical test command |

## 驗證矩陣

| 變更類型 | 最小必要檢查 | 需要擴大驗證的條件 |
| --- | --- | --- |
| 純文件 | 優先執行 `python -m unittest tests.test_project_docs tests.test_package_layout`；另做 `git diff --check` 與 README、AGENTS Quickstart、`.codex/*.md` 一致性檢查。Repository-wide discovery 可補跑，但目前有已知 `GPUtil` dependency errors | 文件新增可執行命令或改變資料邊界 |
| CLI parser／參數 | 檢查 `text_category_profiler/pipeline/TCF_utils.py` 與 `TCFMain.py` stage command 組裝一致 | 參數影響工作池、模型、輸出路徑或外部服務 |
| 資料轉換 | `python -m unittest tests.test_dataconverter_fixture_integration`；使用 repository 小型 fixture、process workers 與 temporary output，不接觸真實工作池 | 變更 pandas／SQLite output adapter、完整 CLI bootstrap、fixed-test／ES 或 handoff 時仍需擴大驗證 |
| 分類器 | 需要已確認模型／fixture 後執行 RunClassfier smoke test；目前待確認 | 影響模型格式、GPU/CPU resource gate 或 output contract |
| 視覺化 lifecycle | `python -m unittest tests.test_visualization_stage tests.test_tcf_main_characterization tests.test_stage_commands`；`python -m py_compile BertScript/Test_result_Vis.py BertScript/visualization_stage.py` | layout、Dash callback 或部署設定改變時才需 browser/screenshot；lifecycle tests 不啟動 Dash server |
| Dash UI filter → charts → table loop protection (KI-008) | `python -m unittest -v tests.test_visualization_stage`；`python -m unittest discover -s tests` | 回歸驗證：實際 nonempty filter 重掛載在任意 SQL/XLS 寫入前 PreventUpdate，僅真實 filter/sort/keywords/labels 變更觸發修正；`ChunkDF_update` 不再輸出 `VisDatatable.page_current`，並由 revision Store 驅動 table/chart；相同頁碼重掛載不自觸發，篩選後頁碼超界 clamp | Windows 實機另外開啟完整 Stage 4 測 `0 筆` 與有結果篩選、清除、排序、分頁及閒置至少 60 秒；檢查 `FilteredPreambleCols_df` 是否只在真實變更後寫入、Dash 前端不鎖死。中斷目錄 `is_running_TestResultVis` 不能因原 ready 名稱不存在就自動改名／重跑，必須另行安全恢復。Hosted CI ≠ Windows GUI acceptance。 |
| ClassTable metadata / GUI field | `python -m unittest -v tests.test_class_table_metadata`（純 stdlib）；`tests.test_sms_merger_path_contract` 需要 pandas，另於安裝完整資料轉換依賴的環境驗證、`python -m BertScript.class_table_metadata validate`；另確認 Dash 欄位／樣式皆改為 Explanation，及歷史 migration replay | full ML／瀏覽器只在實際有相關行為變更時擴大 |
| Timestamp research experiment / legacy CLI shim | `python -m unittest tests.test_timestamp_experiment_boundary tests.test_package_layout tests.test_repository_compile_gate`；`python -m py_compile "experiments/timestamp_generator.py" "text_category_profiler/Timestamp generator.py"` | 這些測試在記憶體內限制產生數量、mock locale／輸出，不啟動真實 5000 次資料生成。真的要大量生成才人工執行 `python experiments/timestamp_generator.py`（輸出至 caller cwd）。 |
| Vendor Dijkstra reference / compatibility path | `python -m unittest -v tests.test_dijkstra_vendor_boundary`；`python -m py_compile vendor/dijkstra_algorithm_master/dijkstra_algorithm.py text_category_profiler/dijkstra_algorithm_master/dijkstra_algorithm.py` | 同時驗證 MIT LICENSE 原樣保留、Graph／INFINITY／verify_algorithm lazy 相容、兩種 direct-run sample 工作目錄語意；不得用該示範演算法宣稱 production graph 功能已驗收 |
| CPython 3.7 GBK ZIP vendor / legacy module | `python -m unittest -v tests.test_edited_zipfile_vendor_boundary`；`python -m py_compile vendor/cpython37_zipfile_gbk/zipfile.py text_category_profiler/Edited_zipfile.py` | 比對歷史 Git blob SHA、保存上游 LICENSE，臨時 ZIP 測 GBK 中央與 local header、CP437 fallback、UTF-8、ASCII、CLI；不使用真實外部 ZIP、不能宣稱正式不可信檔案的安全性 |
| ArtClu Elasticsearch job-template config / legacy import | `python -m unittest -v tests.test_es_job_template_boundary`；`python -m py_compile text_category_profiler/integrations/es_job_template.py text_category_profiler/ArtCluESJobTemplate.py` | fresh interpreter 檢查原始 Git blob、不帶密碼及假環境值、兩種匯入順序、import-time snapshot、legacy runpy/reload 時的重新取值與各自獨立的可變 dict；不得連線真實 Elasticsearch 或輸出真實環境變數 |
| CLI selectors / old import facade | `python -m unittest -v tests.test_cli_selector_boundary`；`python -m py_compile text_category_profiler/cli/selector.py text_category_profiler/selector.py` | Characterization 將 colorama、input、curses 隔離；不啟動真實 terminal，不測 Windows curses 可用性，行為維持歷史版本 |
| Historical Kaggle CSV sample fixture boundary | `python -m unittest -v tests.test_kaggle_csv_fixture_boundary` | 驗證 26 原始 Git blob、相同 CSV 輸入與輸出群、來源程式不再引用舊資料路徑、`DataConverter_utils.py` 的手動 CSV sample 以 `__file__` 解析新路徑；不執行真實 Kaggle/Elasticsearch／WorkPool／ML。移除的是研究資料路徑而非 `KaggleExtraction/us/ads.json` 的其他範例 |
| BL-001 research residual preservation inventory | `python -m unittest -v tests.test_residual_research_inventory`；`python -m py_compile tests/test_residual_research_inventory.py text_category_profiler/text/similarity_utils.py text_category_profiler/core/utilities.py`；`git diff --check HEAD^ HEAD` | 只查保存中的 12 個 Git blob、原路徑及已知手動 caller；不移動資料、不執行研究流程。bounded 12-item inventory 已全部分流、fresh targeted Hosted discovery 已 PASS（PR #145）；仍缺其他 package-root／外部 caller 全盤 inventory 與最終 main 驗收 |
| BL-001 moved RAG/Similarity research fixtures | `python -m unittest -v tests.test_relocated_research_fixtures tests.test_residual_research_inventory tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_relocated_research_fixtures.py tests/test_residual_research_inventory.py text_category_profiler/core/utilities.py`；`git diff --check HEAD^ HEAD` | 保護兩個研究檔原始 Git blob SHA／位元組長度、4 欄 TSV 與兩段連續的 JSON arrays（9+5 筆，不是單一 JSON document）的歷史格式；確認舊位置消失、RAG 註解與 `Graph_utils.py` Louvain 手動範例改用新檔案，characterize 59 節點（不執行聚類），並掃描在庫 .py 直接路徑 literal；外部／動態 caller 未驗證，不執行 RAG／模型／ES／WorkPool |
| BL-001 historical locale PDF reference boundary | `python -m unittest -v tests.test_locale_reference_boundary tests.test_residual_research_inventory tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_locale_reference_boundary.py` | 只查歷史 PDF Git blob 位元組完整性、舊路徑不存在、全 repository Python 原路徑字面引用及來源說明，不解析或產生 PDF、不啟動模型／ES／WorkPool。外部 caller 未查證；BL-001 仍未完成 |
| BL-001 Graph_utils canonical `flattenList` import | `python -m unittest -v tests.test_bl001_graph_utils_canonical_import tests.test_bl001_canonical_import_audit tests.test_bl001_legacy_root_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile text_category_profiler/visualization/Graph_utils.py tests/test_bl001_graph_utils_canonical_import.py`；`python scripts/bl001_canonical_import_audit.py --output artifacts/bl001-canonical-import-evidence.json`；`git diff --check HEAD^ HEAD` | 用 stdlib AST 隔離新 canonical import 和 `ComputeComponent` 演算法，不載入依賴／服務；確定舊 catch-all bare fallback 不再遮蔽 canonical 故障。其它 DatasetConverter legacy 裸匯入保留待查；沒有執行真實模型／資料源。 |
| BL-001 legacy MP clock explicit provider | `python -m unittest -v tests.test_bl001_legacy_mp_clock_import tests.test_bl001_graph_utils_canonical_import tests.test_bl001_canonical_import_audit tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile DatasetConverter/old_MP_utils.py tests/test_bl001_legacy_mp_clock_import.py`；`python scripts/bl001_canonical_import_audit.py --output artifacts/bl001-canonical-import-evidence.json`；`git diff --check HEAD^ HEAD` | stdlib AST 驗證舊 `old_utilities.timeNow` 與 canonical `concurrency.MP_utils.timeNow` 函式結構一致、原 logger log path/格式、匯入失敗不 fallback；不 import 依賴或觸碰真實 logs、外部服務。`df_utils.py` 4 件裸匯入及外部／動態 caller、實機 CLI acceptance 均待查。 |
| BL-001 legacy dataframe explicit providers | `python -m unittest -v tests.test_bl001_legacy_df_providers tests.test_bl001_legacy_mp_clock_import tests.test_bl001_graph_utils_canonical_import tests.test_bl001_canonical_import_audit tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile DatasetConverter/df_utils.py tests/test_bl001_legacy_df_providers.py`；`python scripts/bl001_canonical_import_audit.py --output artifacts/bl001-canonical-import-evidence.json`；`git diff --check HEAD^ HEAD` | 以無服務 AST 驗證 legacy `MPlogger` 靜態 logging、七個既有 call sites、舊版 `multicoreJob` constructor、`hash` 與 `ShowElapsedTime`；只連到 tracked first-party providers，不更動 SQLite/Excel/MySQL 行為。外部／動態 callers 與 full direct-script／工作池驗收仍待確認。 |
| BL-001 core utilities canonical MPlogger import | `python -m unittest -v tests.test_bl001_core_mp_logger_import tests.test_bl001_legacy_df_providers tests.test_bl001_legacy_mp_clock_import tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile text_category_profiler/core/utilities.py tests/test_bl001_core_mp_logger_import.py`；`git diff --check HEAD^ HEAD` | 僅移除 canonical `concurrency.MP_utils.MPlogger` 匯入失敗時對不存在 `core.MP_utils` 的 catch-all 相對 fallback，使用 stdlib AST 證明 provider 存在、instance API 與錯誤傳播，不啟動 core 模組依賴、model/GPU/ES/WorkPool 或直接 CLI。 |
| BL-001 bare-import filename provenance and direct-run candidate syntax | `python -m unittest -v tests.test_bl001_canonical_import_audit tests.test_bl001_package_census tests.test_bl001_legacy_root_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python scripts/bl001_canonical_import_audit.py --output artifacts/bl001-canonical-import-evidence.json`；`python -m py_compile scripts/bl001_canonical_import_audit.py tests/test_bl001_canonical_import_audit.py`；`git diff --check HEAD^ HEAD` | 將 15 件 bare-import candidate 分成 sibling/ancestor/missing first-party provider filename evidence，並為 44 個 canonical modules 註記 top-level `__main__` guard。此稽核不解析 sys.path，不執行任何 CLI，不證實實際 provider 或外部 callers；報告位於 CI JSON artifact。 |
| BL-001 bounded canonical module import evidence | `python -m unittest -v tests.test_bl001_canonical_import_audit tests.test_bl001_package_census tests.test_bl001_legacy_root_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python scripts/bl001_canonical_import_audit.py --output artifacts/bl001-canonical-import-evidence.json`；`python -m py_compile scripts/bl001_canonical_import_audit.py tests/test_bl001_canonical_import_audit.py`；`git diff --check HEAD^ HEAD` | 對 canonical 44 個 Python 模組掃 Git tracked first-party Python AST 的完整 import syntax；報告來源 area 分組、relative imports、動態字串與 bare 名稱 candidate 分開記錄，CI artifact 可用於逐項 Phase 0–3 判斷；未命中不等於 dead code，不能當作實際執行或跨-stage 使用證明。 |
| BL-001 full tracked package structural census | `python -m unittest -v tests.test_bl001_package_census tests.test_bl001_legacy_root_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python scripts/bl001_package_census.py --output artifacts/bl001-package-census.json`；`python -m py_compile scripts/bl001_package_census.py tests/test_bl001_package_census.py`；`git diff --check HEAD^ HEAD` | 71 Git-tracked package files complete path census；58 canonical domain-owned（structural only）、13 legacy; digest, sizes, canonical target, unclassified guard + artifact。不能因此宣稱有跨 stage active call graph、動態／外部 callers、真實模型／GPU／ES／WorkPool 已驗證。 |
| BL-001 DB_utils manual ES-template canonical import | `python -m unittest -v tests.test_db_utils_manual_es_template_import tests.test_es_job_template_boundary tests.test_bl001_legacy_root_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile text_category_profiler/data/DB_utils.py tests/test_db_utils_manual_es_template_import.py`；`python scripts/bl001_legacy_root_audit.py --output artifacts/bl001-legacy-root-audit.json`；`git diff --check HEAD^ HEAD` | 僅修正 `DB_utils.py` direct-script 裡的裸 ES template import，保持 BuildESJobList 參數／兩筆 redacted preview／SQLConcat 順序。isolated AST/stub 不執行真實 DB_utils module dependencies、ES network 或 SQL／filesystem；full direct-script acceptance 未驗證，與 KI-006 credential rotation 分離。 |
| BL-001 residual legacy root compatibility inventory | `python -m unittest -v tests.test_bl001_legacy_root_audit tests.test_dijkstra_vendor_boundary tests.test_tulip_manual_graph_boundary tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python scripts/bl001_legacy_root_audit.py --output artifacts/bl001-legacy-root-audit.json`；`python -m py_compile scripts/bl001_legacy_root_audit.py tests/test_bl001_legacy_root_audit.py`；`git diff --check HEAD^ HEAD` | 13 個原 Git blob（7 package root、5 Dijkstra、1 Tulip）保全及 canonical 目的地；掃描 in-repo first-party Python 明確 AST import、未確定的 bare-import（含 DB_utils 手動 caller）與 literal/comment 候選，分開保存 CI artifact；外部/dynamic/manual caller 不可因此宣稱不存在。不執行模型／ES／Tulip GUI／WorkPool。 |
| BL-001 optional Tulip manual experiment boundary | `python -m unittest -v tests.test_tulip_manual_graph_boundary tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile text_category_profiler/tulip_utils/Graph_Builder.py text_category_profiler/visualization/tulip_graph_builder.py tests/test_tulip_manual_graph_boundary.py`；`git diff --check HEAD^ HEAD` | 保護 24,232-byte 歷史 Tulip graph source 完全相同 Git blob，原始實作搬至 visualization 領域；Stage 4 active caller 在相似度分群實際使用時才直接匯入 domain provider，舊 module path 延遲 optional Tulip import 的 facade，`main()` 仍委派原程式；不連線實際 Tulip GUI、ES、模型、WorkPool，外部 callers 和來源授權未驗證。 |
| BL-001 historical wiki research sample boundary | `python -m unittest -v tests.test_wiki_research_sample_boundary tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_wiki_research_sample_boundary.py`；`git diff --check HEAD^ HEAD` | 保留 83,123-byte `俄烏戰爭@wiki` 原始 Git blob，搬出 package 的 `sample_data/`，同時掃描 Git tracked `.py` 的直接 filename literal，並以隔離 AST 驗證 `ES_utils.py` 手動 ES upsert 範例的檔案定位；不執行模型／資料管線，外部/動態 callers 與來源授權未確認 |
| BL-001 similarity experiment inputs and archived results | `python -m unittest -v tests.test_similarity_experiment_inventory tests.test_residual_research_inventory tests.test_locale_reference_boundary tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_similarity_experiment_inventory.py`；`git diff --check HEAD^ HEAD` | 核對 27 份歷史 TXT／XLSX 的 Git blob SHA、大小與四組檔案配置，確認整個資料夾無意外增刪；不解析 Excel 儲存格、不執行相似度、模型或 ES。外部與動態 caller 尚未盤點完整，15 份 TXT 與 12 份 XLSX 均保留原 Git blob 分流至 `experiments/fixtures/similarity_experiment_inputs/` 與 `experiments/fixtures/similarity_experiment_outputs/`，手動 caller 路徑同步修正；BL-001 In Progress |
| BL-001 bounded static caller audit | `python -m unittest -v tests.test_bl001_research_caller_audit tests.test_residual_research_inventory tests.test_similarity_experiment_inventory tests.test_relocated_research_fixtures tests.test_locale_reference_boundary tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python scripts/bl001_research_caller_audit.py --output artifacts/bl001-research-caller-audit.json` | 由兩份 manifest 掃描 39 個歷史研究資料路徑在 Git 追蹤且排除任一層 vendor/tests/experiments、部署快照與兩個第三方 Dash 範例樹的 Python 程式中之名稱候選；區分包含跨行字串的 AST 字串與文字／註解、保留 basename 重名不確定性及 parse errors，並上傳 CI artifact；不能證明真實 open 行為、動態或 repo 外 callers，且不移檔、不執行資料處理 |
| BL-001 Chinese similarity manual sample fixtures | `python -m unittest -v tests.test_chinese_similarity_fixture_boundary tests.test_residual_research_inventory tests.test_bl001_research_caller_audit tests.test_similarity_experiment_inventory tests.test_relocated_research_fixtures tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile text_category_profiler/text/similarity_utils.py tests/test_chinese_similarity_fixture_boundary.py`；`git diff --check HEAD^ HEAD` | 保護 2 TXT／2 XLSX 原始 Git blob、移除舊 package-root 位置；隔離執行手動 caller，保證只讀新 TXT fixture，Excel 輸出仍是 cwd-relative basename，歷史 XLSX 不會被覆寫；不運行相似度計算、模型或 ES |
| BL-001 punctuation sample fixture relocation | `python -m unittest -v tests.test_punctuation_fixture_boundary tests.test_residual_research_inventory tests.test_bl001_research_caller_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_punctuation_fixture_boundary.py tests/test_residual_research_inventory.py`；`git diff --check HEAD^ HEAD` | 2 個原 83/59-byte Git blob 完全不改寫，舊 package-root 路徑移除，兩份全形逗號差異與 manifest schema v4 保持；first-party Python 靜態掃描無直接檔名引用，但不能排除外部／動態 callers，不執行模型、ES 或檔案批次轉換 |
| BL-001 legacy text tables preservation | `python -m unittest -v tests.test_legacy_text_tables_boundary tests.test_residual_research_inventory tests.test_punctuation_fixture_boundary tests.test_bl001_research_caller_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_legacy_text_tables_boundary.py`；`git diff --check HEAD^ HEAD` | `EmojiAlll.txt`、`特殊符號表.txt`、`total.txt` 依原始 Git blob 不變搬到 `experiments/fixtures/legacy_text_tables/`；manifest schema v5 保全總計 12 筆中的 11 個 relocated_path，唯一 FTP marker 原位。排除直接 first-party Python 檔名引用不等於外部／動態 call graph 已核實；不解析未知文字表、模型、ES 或工作池 |
| BL-001 historical FTP marker | `python -m unittest -v tests.test_ftp_marker_boundary tests.test_residual_research_inventory tests.test_bl001_research_caller_audit tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`git diff --check HEAD^ HEAD` | 保留 3-byte marker 原始 Git blob、移除舊 package-root 位置，獨立 TRV_deploy snapshot 原封不動。AST 只發現 DataConverter 三引號 rowlist 範例，不是 runtime I/O；不能排除外部或動態 caller |
| Fresh Hosted dependency-light discovery | `python -m unittest discover -s tests`，Hosted Python 3.11，安裝特定 data/GPUtil/utils test deps；`TCP_RUN_FULL_PIPELINE_SMOKE=0 TCP_RUN_REAL_PIPELINE_SMOKE=0` | PR #145 HEAD `56f0bf9c37a4` Hosted run `41024022467` 取得 `912 tests OK (skipped=2)`、artifact `12963076869`；兩次失敗先後揭露 `pymongo`、`pytz` 缺口，已補 workflow targeted deps 與根 `requirements.txt` 對 `pytz` 的明列。未安裝全套 root requirements 的重型 TF/PyTorch/CUDA，不代表模型、H100 或 WorkPool 驗收；應於整體 BL-001 完工後再次在最新 main 重跑 |
| Architecture boundaries | `python -m unittest tests.test_package_layout tests.test_project_docs` | import arrows、legacy entrypoints、DatasetConverter boundaries 或 current-state docs 改變 |
| Elasticsearch TXT ingest CLI | `python -m unittest -v tests.test_es_ingest_script_boundary`；`python -m py_compile scripts/ES_ingest_txt_to_es.py text_category_profiler/ES_ingest_txt_to_es.py`；read-only `python scripts/ES_ingest_txt_to_es.py --help` | 只有實際導入受控測試 Elasticsearch 時才驗證遠端 API／索引 mapping；dependency-light mock 無法證明真實 ES 相容性，禁止以 bulk 寫入作一般 smoke test |
| 匯入外部服務 | 先以 dry-run 或 mock 明確標示；不得把真實 DB/ES 寫入當 smoke test | 會連線 SQL Server、Elasticsearch 或批次寫入資料 |

## Full-pipeline smoke profiles

Production operator commands與 unittest profiles 共用 `text_category_profiler.diagnostics.full_pipeline`；production 不 import `tests.*`。

兩個 profiles 都以 temporary WorkPool 隔離 mutable state，並使用 `-TRVHost False`；一般 `python -m unittest discover -s tests` 會 discover 兩個 runtime modules 並將它們明確報為 opt-in SKIP。

### Layer A：隔離的 real-root smoke

Layer A 執行真實 `TCFMain.py` 與 Stage 1–4 child entrypoints，先將 committed model metadata 複製到 temporary writable runtime state，再僅以 PATH dispatcher 替代 inference child。POSIX：

```bash
TCP_RUN_FULL_PIPELINE_SMOKE=1 python -m unittest tests.test_full_pipeline_smoke
```

PowerShell：

```powershell
$env:TCP_RUN_FULL_PIPELINE_SMOKE='1'
python -m unittest tests.test_full_pipeline_smoke
```

PASS 必須包含 root exit 0、唯一 classifier marker、final `*_rdy_for_Spike`、Stage 1–4 artifacts 與 `logs/Test_result_Vis.log`；這不是 real model/GPU acceptance。

### Layer B：real-model/GPU acceptance profile

Layer B 不安裝 inference interception；它透過 temporary writable model facade 讀取 production resolver 選出的 checkpoint。啟用時只有 opt-in 變數是必要的；port、model type、timeout 與資源路徑都是 optional overrides：

```text
TCP_RUN_REAL_PIPELINE_SMOKE=1
TCP_REAL_PORT=8050                                   # optional
TCP_REAL_MODEL_TYPE=PytorchMMBERT                    # optional; canonical default
TCP_REAL_PIPELINE_TIMEOUT_SECONDS=1800               # optional
TCP_REAL_MODEL_DIR=<source model override>            # optional
TCP_REAL_FIXED_TEST_DIR=<FixedTest Using override>    # optional
TCP_REAL_TOPIC_TREE_DIR=<taxonomy directory override> # optional
TCP_REAL_TOPIC_TREE_FILES=<taxonomy files override>   # optional
```

POSIX：

```bash
TCP_RUN_REAL_PIPELINE_SMOKE=1 \
TCP_REAL_PORT=8059 \
TCP_REAL_MODEL_TYPE=PytorchXLM \
python -m unittest tests.test_full_pipeline_real_runtime
```

PowerShell：

```powershell
$env:TCP_RUN_REAL_PIPELINE_SMOKE='1'
$env:TCP_REAL_PORT='8059'
$env:TCP_REAL_MODEL_TYPE='PytorchXLM'
python -m unittest tests.test_full_pipeline_real_runtime
```

Layer B 只有在 root exit 0、production classifier evidence、final `*_rdy_for_Spike`、外部 inputs unchanged 及預定 H100 acceptance 的 CUDA available/selected evidence 完整時才算 acceptance PASS。

詳細的 discovery、Doctor、failure interpretation、source-isolation 與 CUDA evidence 規則見 `docs/operations/pipeline-diagnostics-and-smoke-testing.md`。

## 測試資料與外部服務

- 最小 fixture：`tests/fixtures/dataconverter_small/`；目前涵蓋兩個 labels、三個純文字來源、worker read、split bounds 與 temporary TSV artifacts。
- 測試是否允許網路：待確認；預設不讓測試依賴網路成功。
- 外部服務替代方式：待確認；mock 必須明確揭露，不得冒充正式成功。
- 測試產物位置與清理方式：待確認；`WorkPool*`、`logs`、模型與 output 目錄需先視為可能有狀態。

## Windows／Anaconda：PyTorch 分類與 TensorFlow DLL 後端隔離

`BertScript/TextClassification_transformers.py` 為 PyTorch 專用入口，現會在首次載入 PyTorch／Hugging Face Transformers **之前**將本 Python 子程序的 `USE_TF=0`、`USE_TORCH=1`，避免同環境已安裝卻無法載入的 TensorFlow DLL 中斷 `from transformers import BertModel`。這不是修復 TensorFlow DLL 本身；也**不會**修改上層 `TCFMain.py` 或 `TF15Bert` 的 shell/batch 執行路徑。

這個自動隔離只有 dependency-light／Hosted CI 驗證；Windows 先前通過的是**手動**設定環境變數的完整流程。要驗收自動修正，使用新的 **Anaconda Prompt (CMD)**，不要先執行 `set USE_TF`／`set USE_TORCH`，在與既有工作相同的 Python 環境檢查：

```bat
echo USE_TF=%USE_TF%
echo USE_TORCH=%USE_TORCH%
python -c "import sys; print(sys.executable)"
python -c "from transformers import BertModel; print('BertModel import OK')"
```

最後一個單獨 `BertModel` 匯入在 **TensorFlow 壞掉且未手動隔離**的機器上仍可能報錯，這**不是**自動修正失效，因為只有 `TextClassification_transformers.py` 專用入口才啟用後端隔離。應使用原本的 `TCFMain.py` PyTorch 分類指令跑完 Stage 2／後續交接，並檢查未再出現 `_pywrap_tensorflow_internal` DLL traceback。不要為了避開 DLL 問題擅自全域移除 TensorFlow，舊 `TF15Bert` 路徑需保留。

Hosted CI 驗證：`python -m unittest -v tests.test_classifier_stage tests.test_torch_compat tests.test_tcf_main_characterization tests.test_stage_commands tests.test_runtime_dependency_contract`（Stage 2 PyTorch Transformers Backend Isolation workflow）；CI 未安裝壞掉的 Windows TensorFlow DLL，不能宣稱 Windows 免手動設定已通過。

## Windows Anaconda：Dash/comm 載入前檢查

當獨立啟動 `Test_result_Vis.py` 的 `import dash` 透過 `dash._jupyter` → `comm.create_comm(target_name="dash")` 拋出 `NotImplementedError: Cannot`，屬於啟動 Python 環境的舊 `comm` 實作與 Dash 不相容；它不是 RunClassfier／CombineTestResult 的模型錯誤。

在**執行 TCFMain.py 的同一個 Anaconda 環境與 Python 解譯器**下，先查明版本與所在路徑：

```powershell
python -c "import sys, importlib.metadata as m, comm; print(sys.executable); print('comm:', m.version('comm'), comm.__file__); print('dash:', m.version('dash'))"
```

先備份／複製原本的 Conda 環境，再修復依賴（只升級 `comm`，避免順手升級整套 ML/CUDA 套件）：

```powershell
python -m pip install --upgrade "comm>=0.2.3"
python -c "import dash; print(dash.__version__)"
```

第二行通過後，才重試原本的 Stage 4 命令。若無法安裝或升級，留下上述診斷輸出與 pip dependency conflict 資訊；**不得聲稱 Stage 4 已在 Windows 實機通過**。專案回歸測試不啟動真實 Dash server：`python -m unittest tests.test_visualization_stage tests.test_tcf_main_characterization tests.test_stage_commands`。

## 常見失敗與替代驗證

| 限制 | 首選驗證 | 安全替代 | 不足之處 |
| --- | --- | --- | --- |
| 缺少完整 runtime／test dependency | `python -m unittest tests.test_dataconverter_fixture_integration` | 依變更範圍執行 targeted dependency-light tests；repository-wide discovery 目前另有已知 `GPUtil` dependency errors | 可證明隔離的 source → worker → split → TSV 契約，但不能證明完整 legacy CLI、pandas／SQLite、工作池 handoff或 repository-wide clean PASS |
| 流程命令可能搬移／刪除工作池資料 | 在隔離 fixture 中執行 | 僅檢查 command assembly 與 contract 文件 | 不能覆蓋 I/O side effects |
| Repository-wide compile | `python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler` | 修改個別 Python 模組時可另跑 `py_compile` 作為 scoped verification | Repository-wide compile gate is expected to PASS；此 canonical command 不得縮小掃描範圍或加入排除項 |

## 完成前檢查

- 使用的是此 repo 已確認的 runtime 與 package manager；若未確認，不猜測安裝命令。
- 先跑最相關檢查，再依風險擴大；不為小改動無條件重裝全部依賴。
- 不把資料庫、雲端、寄信、發布、刪除或 migration 當成無副作用測試。
- 所有未執行或失敗的檢查都在最終回報中明確區分。
