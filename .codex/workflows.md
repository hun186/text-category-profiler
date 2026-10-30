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
| ClassTable metadata validator | `python -m BertScript.class_table_metadata validate --json` | repository root | Hosted CI 在 PR #127 初版 HEAD 驗證通過；不一致的 graph sets 僅 warning，`--strict-tree` 才視為失敗 |
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
| Dash UI callback / idle redraw | `python -m unittest tests.test_visualization_stage`：確認單獨的 DataTable null derived-filter remount 在輸出檔案前被略過，table data 不再是表格重建 callback 的 self-Input；CI 不執行瀏覽器 | 在 Windows 實機開啟 Stage 4，閒置至少 1 分鐘確認無 table→filter→chart 迴圈或重複磁碟輸出，再各測一次真實篩選、清除、排序及翻頁；沒有現場驗證前 KI-008 不得標示 Resolved |
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
| BL-001 historical wiki research sample boundary | `python -m unittest -v tests.test_wiki_research_sample_boundary tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_wiki_research_sample_boundary.py`；`git diff --check HEAD^ HEAD` | 保留 83,123-byte `俄烏戰爭@wiki` 原始 Git blob，搬出 package 的 `sample_data/`，同時掃描 Git tracked `.py` 的直接 filename literal；不執行模型／資料管線，外部/動態 callers 與來源授權未確認 |
| BL-001 similarity experiment inputs and archived results | `python -m unittest -v tests.test_similarity_experiment_inventory tests.test_residual_research_inventory tests.test_locale_reference_boundary tests.test_package_layout tests.test_project_docs tests.test_repository_compile_gate`；`python -m py_compile tests/test_similarity_experiment_inventory.py`；`git diff --check HEAD^ HEAD` | 核對 27 份歷史 TXT／XLSX 的 Git blob SHA、大小與四組檔案配置，確認整個資料夾無意外增刪；不解析 Excel 儲存格、不執行相似度、模型或 ES。外部與動態 caller 尚未盤點完整，15 份 TXT 維持原位，12 份 XLSX 以原 Git blob 分流至 `experiments/fixtures/similarity_experiment_outputs/`；BL-001 In Progress |
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
