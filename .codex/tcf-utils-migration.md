# `tcf_utils` 遷移 TODO

> 類型：可持續執行的重構工作清單。後續 Codex 任務應一次處理一個可驗證批次，完成後更新本檔核取方塊與 `.codex/backlog.md` 狀態。

## 目標

將 `PythonModule/utils/` 中真正跨 stage 共用的 helper 整理為根目錄 `tcf_utils/` package，同時把具明確領域歸屬、測試、實驗、維護腳本與第三方程式移到合適邊界。遷移完成後，active code 不再依賴 `PackageImporter` 修改 `sys.path`，但既有 CLI、stage handoff 與資料格式保持相容。

## 已確認方向

- 共用 package 名稱採用 `tcf_utils`，不使用過度泛用的頂層 `utils`，也暫不將整個應用程式包成 `text_category_profiler`。
- 保留 `DatasetConverter/`、`BertScript/`、`ClassesTree/` 的既有 stage／領域責任；本計畫不要求一次重組所有 stage。
- 只有至少兩個 active stage 使用、責任明確且適合重用的程式才進入 `tcf_utils/`。
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
tcf_utils/
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

### Phase 1：建立最小 `tcf_utils`

- [ ] 建立 `tcf_utils/__init__.py`，不在 package import 時載入大型 optional dependencies 或執行副作用。
- [ ] 將 `model_paths.py` 搬至 `tcf_utils/model_paths.py`，更新測試與 active callers。
- [ ] 將 `torch_compat.py` 搬至 `tcf_utils/torch_compat.py`，更新測試與 active callers。
- [ ] 將 `log_display.py` 搬至 `tcf_utils/console.py`，更新測試與 active callers。
- [ ] 將 `progress_utils.py` 搬至 `tcf_utils/progress.py`，更新 active callers。
- [ ] 確認以上模組可直接由 repository root import，不需要 `PackageImporter.proc()`。
- [ ] 若需要 compatibility shim，加入針對舊 import path 的測試並記錄移除條件。

### Phase 2：拆分路徑、序列化與基礎 helper

- [ ] 從 `utilities_path.py` 盤點純路徑 helper，搬到 `tcf_utils/paths.py`；檔案搬移／刪除函式需另行風險審查。
- [ ] 從 `json_utils.py` 搬移通用 serialization helpers；具資料領域語意的 serializer 留在原領域。
- [ ] 從 `utilities.py` 提取 hashing helpers，建立單元測試後搬到 `tcf_utils/hashing.py`。
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

- [ ] 將 active code 的 `from utils...`／`import utils...` 改為 `from tcf_utils...` 或明確 stage-local import。
- [ ] 移除 active entry points 中的 `PackageImporter.proc()`。
- [ ] 移除 active code 對目前 working directory 深度的 import 假設；不得在 import 階段 `chdir`。
- [ ] 盤點 repository 內所有 `PackageImport.py`，區分 active、vendor、deployment snapshot 後逐一處理。
- [ ] 確認同一程序中不可能從外部 `D:/shared/PythonModule` 或其他相對深度載入同名模組。

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

- `tcf_utils` 只包含責任明確、確實跨 stage 使用的 helper。
- active imports 不再仰賴 `sys.path` 注入或 working-directory 切換。
- `PythonModule/` 已從主程式邊界移除，且沒有未解決的雙份權威實作。
- 既有 CLI、stage handoff、dataset 與結果檔案契約未改變，或任何必要改變已另立 contract migration。
- 輕量測試全數通過；需要模型、資料或外部服務的未執行驗證已明確記錄。

## 非本計畫範圍

- 一次將整個 repository 改為 `src/` layout。
- 同時重寫模型訓練、推論、資料轉換或 Dash UI 行為。
- 未經查證直接刪除第三方原始碼、deployment snapshot、歷史副本或資料 fixture。
- 僅為符合新命名而建立空 package、假測試或 silent fallback。
