# `text_category_profiler` 遷移 TODO

> 類型：可持續執行的重構工作清單。後續 Codex 任務應一次處理一個可驗證批次，完成後更新本檔核取方塊與 `.codex/backlog.md` 狀態。

> 目前狀態：根目錄 package 已從泛用的 `utils/`、歷史縮寫 `tcf_utils/` 逐步改名為 `text_category_profiler/`，repository 的 active imports 已同步使用完整專案 namespace。下列清單仍追蹤內容分流、deployment 相容與 path injection 淘汰。

## 目標

將 `PythonModule/utils/` 中真正跨 stage 共用的 helper 整理為根目錄 `text_category_profiler/` package，同時把具明確領域歸屬、測試、實驗、維護腳本與第三方程式移到合適邊界。遷移完成後，active code 不再依賴 `PackageImporter` 修改 `sys.path`，但既有 CLI、stage handoff 與資料格式保持相容。

## 已確認方向

- Python package 名稱採用 `text_category_profiler`，與 repository 名稱 `text-category-profiler` 對齊，不使用過度泛用的頂層 `utils` 或舊專案縮寫 `tcf_utils`。
- 保留 `DatasetConverter/`、`BertScript/`、`ClassesTree/` 的既有 stage／領域責任；本計畫不要求一次重組所有 stage。
- 只有至少兩個 active stage 使用、責任明確且適合重用的程式才進入 `text_category_profiler/`。
- stage-specific 程式應留在或移回所屬 stage，不得為縮短 import 而塞進共用 package。
- 先建立測試與相容層，再搬實作；最後才刪除 `PythonModule/` 與 `PackageImport.py`。

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

- [ ] 建立 active entry point 清單：`TCFMain.py`、DataConverter、classifier runner、result combiner、visualization。
- [ ] 產生 `PythonModule/utils/` 模組 → active callers 對照表，排除 archive、vendor、copy 與部署 snapshot。
- [ ] 逐組比較重複模組，例如 `df_utils.py`、`MP_utils.py`、`utilities.py`，確認權威版本與差異。
- [ ] 將檔案標記為 `shared`、`stage-specific`、`script`、`test/experiment`、`vendor`、`legacy/unknown` 六類。
- [ ] 為第一批候選模組確認或補齊無外部服務副作用的 characterization tests。
- [ ] 記錄 repository 外部是否仍有程式依賴 `from utils...`；未確認前保留相容策略。

### Phase 1：建立最小 `text_category_profiler`

- [ ] 建立 `text_category_profiler/__init__.py`，不在 package import 時載入大型 optional dependencies 或執行副作用。
- [ ] 將 `model_paths.py` 搬至 `text_category_profiler/model_paths.py`，更新測試與 active callers。
- [ ] 將 `torch_compat.py` 搬至 `text_category_profiler/torch_compat.py`，更新測試與 active callers。
- [ ] 將 `log_display.py` 搬至 `text_category_profiler/console.py`，更新測試與 active callers。
- [ ] 將 `progress_utils.py` 搬至 `text_category_profiler/progress.py`，更新 active callers。
- [ ] 確認以上模組可直接由 repository root import，不需要 `PackageImporter.proc()`。
- [ ] 若需要 compatibility shim，加入針對舊 import path 的測試並記錄移除條件。

### Phase 2：拆分路徑、序列化與基礎 helper

- [ ] 從 `utilities_path.py` 盤點純路徑 helper，搬到 `text_category_profiler/paths.py`；檔案搬移／刪除函式需另行風險審查。
- [ ] 從 `json_utils.py` 搬移通用 serialization helpers；具資料領域語意的 serializer 留在原領域。
- [ ] 從 `utilities.py` 提取 hashing helpers，建立單元測試後搬到 `text_category_profiler/hashing.py`。
- [ ] 盤點 time、collection 與 text helpers；只有確有跨 stage callers 才建立對應單一責任模組。
- [ ] 移除已由新模組取代的重複實作，不保留兩份可分歧的 source of truth。

### Phase 3：將非共用內容分流

- [ ] 將 `DataConverter_utils*.py` 的 domain logic 移回 `DatasetConverter/`，維持 dataset contract。
- [ ] 將分類器、模型與 GPU/CPU runtime 專用程式移回 `BertScript/` 的適當子模組。
- [ ] 將 Dash、Plotly、graph 與 reusable components 移至 visualization 邊界。
- [ ] 將 SQLite、MongoDB、Elasticsearch、FTP、Email 功能按 backend／integration 拆分，避免 import 一個 backend 時強制載入其他 backend。
- [ ] 將可獨立執行的匯入／轉換工具移至 `scripts/`，並保留明確 CLI entry behavior。
- [ ] 將 `*_test.py`、效能比較與研究原型分流到 `tests/` 或 `experiments/`。
- [ ] 查證 `Edited_zipfile.py`、`dijkstra_algorithm_master/` 等來源、修改與授權，再決定移至 `vendor/`、以 dependency 取代或移除。
- [ ] 盤點 `- 複製.py`、日期版本、`old_*`、`deprecated` 檔；先比較差異，再整合、測試、歸檔或刪除。

### Phase 4：淘汰 path injection

- [x] 將 active code 的 `from utils...`／`import utils...` 改為 `from text_category_profiler...` 或明確 stage-local import。
- [x] 移除 `text_category_profiler/` package 內部、`TCFMain.py` 與 `TCF_Params/` 對 `PackageImporter.proc()` 的依賴；package layout test 會阻止這些邊界重新匯入 legacy path injector。
- [x] 移除四個 canonical stage entry points（DataConverter、classifier runner、result combiner、visualization）中的 `PackageImporter.proc()`；各入口只由 `__file__` 推導 repository root，其他輔助／legacy scripts 另批處理。
- [x] 移除 visualization layout support module 的 `PackageImporter.proc()`，並以明確的 `from BertScript import reusable_components as rc` 保留既有 stage-local implementation；repository-root bootstrap 仍只由 canonical visualization entrypoint 負責。
- [x] 移除 active PyTorch Transformers classifier backend 中的 `PackageImporter.proc()`；直接執行時只加入由 `__file__` 推導的 repository root。
- [x] 移除 DatasetConverter tree adapter 主動載入的 `ClassesTree/ClassesTree_utils.py` 對 `PackageImporter.proc()` 的依賴；taxonomy/tree 行為與既有檔案解析策略維持不變。
- [x] 移除 legacy/manual `DatasetConverter/DataConverter_Combiner.py` 的 import-time `chdir` 與 `PackageImporter.proc()`；repository 搜尋未發現 canonical production caller 或 active importer。直接執行時以 `__file__` 推導 repository root，並明確將相對的 WorkPool、來源資料、log 與輸出路徑解析至該 root，以保留舊有從 `DatasetConverter/` 啟動時的檔案位置而不改變 cwd。
- [ ] 移除 active code 對目前 working directory 深度的 import 假設；不得在 import 階段 `chdir`。
- [ ] 盤點 repository 內所有 `PackageImport.py`，區分 active、vendor、deployment snapshot 後逐一處理。
- [ ] 確認同一程序中不可能從外部 `D:/shared/PythonModule` 或其他相對深度載入同名模組。

#### Phase 4 `PackageImport` inventory（`main@ce9c4888` 加上本批變更）

以下以 `rg` 找候選、再以 Python AST 排除註解與字串；`Graph_Builder.py` 的兩行註解因此不算 consumer。剩餘 17 個 consumer 都有 executable import、在 module import 時呼叫 `PackageImporter.proc()`，所以皆會改動 `sys.path`。Canonical active boundaries（`TCFMain.py`、DataConverter、RunClassfier、CombineTestResult、Test_result_Vis、Transformers classifier）目前為 **0** 個 consumer。

| Consumer | 分類 | 已知 caller／entrypoint | 額外 cwd／path side effect | 後續處置 |
| --- | --- | --- | --- | --- |
| `DatasetConverter/EXTConverter/ExtractionConverter.py` | active support/module | `adapters/extraction_source.py::run_extraction()`，只在 extraction mode 載入 | 從 `EXTConverter` 啟動會 `chdir`，另有 `proc()` | remove bootstrap |
| `DatasetConverter/EXTConverter/Combiner.py` | active support/module | `adapters/extraction_source.py::build_czj_corpus()`，WeiTech conversion 才載入；亦可直接執行 | 從 `EXTConverter` 啟動會 `chdir`，另有 `proc()` | remove bootstrap |
| `BertScript/TextClassification_XLM.py` | legacy/manual script | 無 active caller；目前 classifier runner 使用 `TextClassification_transformers.py` | `proc()` path injection | preserve as legacy for now |
| `BertScript/writeto_tsv.py` | legacy/manual script | 無 repository caller；直接執行／import 都會立即讀寫 THUC dataset | `proc()` 且 module-scope filesystem I/O | preserve as legacy for now |
| `ClassesTree/Visualization/jaal/jaalViewer.py` | legacy/manual script | `Test_result_Vis.py` 僅有註解 import；可直接啟動 Jaal viewer | `proc()` 後依 cwd 名稱無條件 `chdir` | preserve as legacy for now |
| `DatasetConverter/ConverterParameters.py` | legacy/manual script | DataConverter 的舊 import 位於三引號字串／註解，另有 boundary test 禁止重新載入 | `proc()`；import 時偵測 GPU/process capacity | preserve as legacy for now |
| `DatasetConverter/CorpusMetadataManager.py` | legacy/manual script | 無 repository caller | `proc()`；import 時掃檔、備份及開啟 SQLite | preserve as legacy for now |
| `DatasetConverter/DateChecker.py` | legacy/manual script | 無 repository caller | 依 cwd `chdir`、`proc()`，並在 import 時讀 SQLite/text | preserve as legacy for now |
| `DatasetConverter/SMS/SMSMerger.py` | legacy/manual script | 無 repository caller | `proc()`；import 時可執行 batch command 並讀寫結果 | preserve as legacy for now |
| `DatasetConverter/SummarizationExcels_Combiner.py` | legacy/manual script | 無 repository caller；只有 `__main__` 執行合併 | `proc()` path injection | preserve as legacy for now |
| `DatasetConverter/Dataset Generator/ComponentGenerator/ComponentGenerator.py` | test/experiment | ExtractionRule 只把其目錄列為資料來源，沒有 import/call | `proc()`；若 cwd 名為 `EXTConverter` 會 `chdir` | investigate separately |
| `DatasetConverter/FreqAnalysis_dash.py` | test/experiment | 無 repository caller；獨立 Dash analysis | `proc()` path injection | investigate separately |
| `BertScript/TextClassification_XLM_Pred_deprecated.py` | copy/deprecated | 無 active caller（runner 只留註解舊 command） | `proc()` path injection | investigate separately |
| `BertScript/TextClassification_XLM_Train_deprecated.py` | copy/deprecated | 無 active caller | `proc()` path injection | investigate separately |
| `DatasetConverter/EXTConverter/Combiner - 複製.py` | copy/deprecated | 無 repository caller | 依 cwd `chdir`、`proc()` | investigate separately |
| `BertScript/TRV_deploy/deploy-dash-with-gcp-master/TRV/main.py` | deployment snapshot | snapshot app entrypoint | `proc()` path injection | deployment boundary |
| `BertScript/TRV_deploy/deploy-dash-with-gcp-master/TRV/PythonModule/utils/Email_utils.py` | deployment snapshot | snapshot utility；由 snapshot 自行維護 | `proc()` path injection | deployment boundary |

分類計數：canonical active **0**、active support/module **2**、legacy/manual script **8**、test/experiment **2**、vendor **0**、deployment snapshot **2**、copy/deprecated **3**、unknown **0**。`tests/test_package_layout.py` 對 15 個 application debt consumers、2 個 deployment consumers 和 canonical-zero boundary 分別做 AST guard；vendor tree 是明示排除邊界，盤點時未發現 consumer，不是靜默忽略。

| `PackageImport.py` provider | 狀態／consumer 關係 | 後續處置 |
| --- | --- | --- |
| `PackageImport.py` | root provider；沒有 canonical consumer，legacy scripts 的實際解析仍取決於啟動 cwd／`sys.path` | remove bootstrap（待 consumer 清空後） |
| `BertScript/PackageImport.py` | BertScript legacy/support local provider | remove bootstrap |
| `DatasetConverter/PackageImport.py` | DatasetConverter legacy local provider | remove bootstrap |
| `DatasetConverter/EXTConverter/PackageImport.py` | EXTConverter support/copy local provider | remove bootstrap |
| `ClassesTree/PackageImport.py` | ClassesTree legacy provider；目前無同目錄 executable consumer | investigate separately |
| `ClassesTree/Visualization/jaal/PackageImport.py` | Jaal legacy local provider | preserve as legacy for now |
| `DatasetConverter/Dataset Generator/ComponentGenerator/PackageImport.py` | generator experiment local provider | investigate separately |
| `TCF_Params/PackageImport.py` | 無 verified consumer | remove bootstrap |
| `text_category_profiler/PackageImport.py` | 無 verified consumer；shared package 已禁止重新引入 | remove bootstrap |
| `text_category_profiler/tulip_utils/PackageImport.py` | 無 executable consumer；`Graph_Builder.py` 只有註解 | remove bootstrap |
| `BertScript/TRV_deploy/deploy-dash-with-gcp-master/TRV/PackageImport.py` | deployment snapshot provider | deployment boundary |

建議後續順序：先處理剩餘兩個有 canonical caller 的 EXTConverter support modules（ExtractionConverter／Combiner 一批）；其次處理無 caller 且副作用較小的 legacy/manual scripts；再個別判定會在 import 時讀寫資料的 manual scripts；最後才處理 experiment、deprecated/copy 與無 consumer providers。Deployment snapshot 維持獨立 boundary；本批未移除任何 provider，Phase 4 與 `BL-001` 仍為進行中。

### Phase 5：刪除 legacy 容器並同步文件

- [ ] `rg` 確認 active code 與 tests 不再引用 `PythonModule`、頂層 `utils` 或 `PackageImporter`。
- [ ] 確認部署副本若仍需舊結構，已有獨立且清楚的維護邊界，不會被主流程 import。
- [ ] 刪除已清空的 `PythonModule/` 與不再需要的 compatibility shims。
- [ ] 同步 README、`.codex/project.md`、`.codex/architecture.md`、`.codex/contracts.md` 與 `.codex/workflows.md` 的 current-state 路徑。
- [ ] 將 `.codex/backlog.md` 的 `BL-001` 標記為 `Done`，並在 `.codex/memory.md` 留下最終驗證摘要。

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
