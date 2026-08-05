# Project Memory

> 類型：Recent durable context。不是聊天紀錄或完整 changelog；只保存能讓後續任務少走彎路的近期成果。

## Current Focus

- 初始化狀態：`INITIALIZED`
- 目前工作焦點：維護 Python 文字分類／資料集轉換／BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 最近確認可工作的路徑：文件與靜態盤點；runtime smoke test 尚未確認。
- 需要延續的相容性／限制：未確認 fixture、模型、工作池與依賴前，不執行會搬移／刪除／批次寫入資料的流程命令。
- README 判定：`NEEDS_UPDATE`；原文件有實質內容但描述另一個 FastAPI/Elasticsearch RAG agent，已局部改寫為目前 repo 可查證狀態。

## Recent Outcomes

### 2026-08-05 — Codex 指示檔案系統初始化

- 目標：依根目錄 `AGENTS.md` 與 `CODEX_BOOTSTRAP.md` 初始化 Quickstart、`.codex/*.md` 與根 README。
- 結果：根 Quickstart 與 `.codex/project.md`、`workflows.md`、`architecture.md`、`contracts.md` 已改為 current-state；README 已從錯置的 SRA/RAG 說明改為 Python text classification profiler summary。
- 重要範圍：Codex 指示文件、README、專案工作流與 contract routing。
- 驗證：靜態盤點 `rg --files`、閱讀入口／parser／requirements；執行 `git diff --check`。
- 未驗證／限制：未執行 runtime smoke test，因根目錄無 canonical install/test command，且主流程需真實資料、模型與工作池。
- 後續：請人工確認 Python 版本、完整依賴、可安全 smoke fixture、資料提交邊界與是否仍需保留舊 SRA/RAG 內容。

### 2026-08-05 — Pytorch transformer training progress clarity

- 目標：釐清 PytorchXLM/PytorchRBTL3 執行時「載入資料慢」的觀感，並避免 train-only 呼叫被強制接續 prediction。
- 結果：`TextClassification_transformers.py` 在資料載入/斷詞完成後明確印出樣本數，標示下一個 tqdm 是 Hugging Face Trainer 訓練/評估；Trainer batch size 改用程式估算值並避免 logging_steps 為 0；移除 main 內無條件 `args.test = True`。
- 驗證：`python -m py_compile BertScript/TextClassification_transformers.py`、`git diff --check`。
- 未驗證／限制：未執行完整訓練流程，因需模型、依賴與工作池資料；py_compile 顯示既有 regex escape SyntaxWarning。

## Open Handoffs

- 需要使用者確認可安全執行的最小 fixture 與依賴安裝方式後，才能把 workflows 中的 smoke test 從待確認改成 canonical command。
- 若舊 README 的 SRA/RAG 描述其實屬於本 repo 未盤點到的子專案，需指出位置並更新 project/contracts。

## Archive Index

- 詳細索引見 `.codex/archive/README.md`。
- 一般任務不讀 archive，除非 Current Focus／Recent Outcomes 明確引用或使用者要求追溯。

## 記錄準則

值得記錄：

- 任務的可觀察結果與重要範圍。
- 實際通過的驗證，或具體未驗證原因。
- 後續修改會用到的相容性、不變條件或教訓。
- 尚未完成但已存在的交接。

不要記錄：

- 完整命令輸出、聊天逐字稿與每一步操作。
- 可直接從 Git diff 得知的瑣碎檔名清單。
- 已失效的猜測、一次性 typo、無後續價值的失敗命令。
- 尚未接受的改善靈感。
- 秘密、個資、真實連線資料或敏感 payload。

### 2026-08-05 — Topic tree boundary refactor

- 目標：支援將分類 taxonomy CSV 從 legacy `../TACA` 隱含位置切出，改由本專案顯式指定來源目錄。
- 結果：新增 `--TopicTreeDir` 與 `--TopicTreeFiles` CLI；DatasetConverter 會把參數傳給 `ClassesTree` 載入與備份 tree CSV；指定 `--TopicTreeDir` 時找不到檔案會直接失敗並提示專案邊界設定。
- 重要範圍：`PythonModule/utils/TCF_utils.py`、`DatasetConverter/DataConverter.py`、`ClassesTree/ClassesTree_utils.py`、`.codex/architecture.md`、`.codex/contracts.md`。
- 驗證：`python -m py_compile ...`；以最小 TopicTree fixture 搭配 stubbed heavy dependencies 驗證 `LoadTree(..., TreeSourceDir=...)` 與 missing-file 錯誤。
- 未驗證／限制：未執行完整 `TCFMain.py` 流程，因目前環境缺少 pandas/psutil 等 runtime dependency，且完整流程需真實資料與模型。

### 2026-08-05 — Default in-repo topic tree data lookup

- 目標：讓未傳 `--TopicTreeDir` 的主流程可自動找到使用者放在 `ClassesTree/data` 的 `TopicTree.csv` 與 `TopicTree_AK4.csv`。
- 結果：`ClassesTree.GetTreeFilePath()` 在 legacy `../TACA` fallback 前先檢查 `ClassesTree/data`，仍保留顯式 `--TopicTreeDir` 的高優先權與失敗訊息。
- 驗證：`python -m py_compile ...`、AST-isolated `GetTreeFilePath()` lookup 檢查、`git diff --check`。

### 2026-08-05 — Train-only DataConverter zero-test guard

- 目標：修正 `python TCFMain.py -tr y` 在只產生 train/dev、沒有 test/fixed-test/ES 樣本時，DataConverter 誤判「all samples ZERO」並中止後續訓練的問題。
- 結果：DataConverter 改以 train+validation+test/fixed-test/ES 的總轉換量判斷是否完全無樣本；只有 `args.test == True` 且 test 總量為 0 時才維持測試模式中止。
- 驗證：`python -m py_compile DatasetConverter/DataConverter.py`、`git diff --check`。
- 未驗證／限制：未執行完整 `TCFMain.py -tr y`，因流程需本機完整依賴、模型與工作池資料；py_compile 仍顯示既有 regex/path escape SyntaxWarning。

### 2026-08-05 — RunClassfier train label list materialization

- 目標：修正 `python TCFMain.py -tr y` 進入 `RunClassfier` 後，因 dataset 根目錄缺少 `TopicAnalysis_LabelList.txt` 而在複製模型相關檔案時中止。
- 結果：`RunClassfier` train mode 現在不再依賴 `DataAugmentationGoal > 100` 才產生 root `TopicAnalysis_LabelList.txt`；每次訓練都從 `train.sql3` 的 `sampleSrc.OutLabel` 產生 occurring-label list，讓 classifier head 與實際訓練類別一致，並在只有 0/1 個訓練 label 時中止。`DataConverter` 仍會在 `OnlyForRecord/TopicAnalysis_LabelList_Including_NonOccuring.txt` 保留完整 taxonomy 參考檔。
- 驗證：AST-isolated `WriteOccurringLabelList` SQLite smoke test、`python -m py_compile BertScript/RunClassfier.py`、`git diff --check`。
- 未驗證／限制：未執行完整 `TCFMain.py -tr y`，因本環境沒有使用者本機模型、完整依賴與 Windows 工作池狀態。

### 2026-08-05 — Train split label coverage before classifier handoff

- 目標：把 label-list mismatch 的根因前移到 DataConverter 切分階段處理，避免 DataAugmentationGoal 較小時某 label 被 random split 全部切到 dev/test。
- 結果：`DatasetGenerator.run()` 在切 train/dev/test 前呼叫 `EnsureTrainCoversLabels()`；當 train slot 足以覆蓋所有目前資料中的 label 時，會將每個 label 的第一筆樣本優先放進 train 前段，降低後續 `TopicAnalysis_LabelList.txt` 與 dev/test label 不一致的風險。若 label 數超過 train slot，會警告無法保證覆蓋。
- 驗證：`python -m py_compile DatasetConverter/DataConverter.py`、`git diff --check`。
- 未驗證／限制：本容器缺少 pandas，無法執行 DataFrame helper 的 isolated runtime smoke test；未執行完整 `TCFMain.py -tr y`。

### 2026-08-05 — Main pipeline console readability pass 1

- 目標：降低 `TCFMain.py -ts y` 訓練／部署流程中主階段 handoff 訊息的視覺疲勞，同時保留可複製的完整 command 以利除錯。
- 結果：新增 `utils.log_display` 作為輕量 console display helper；`TCFMain.py` 的 DataConverter、RunClassfier、CombineTestResult、Test_result_Vis 與部分 backup/error 訊息改用階段 banner、摘要化參數、縮排 command、成功／失敗圖示。
- 驗證：`python -m py_compile TCFMain.py PythonModule/utils/log_display.py`、`PYTHONPATH=PythonModule python - <<'PY' ...` 手動預覽 display helper、`git diff --check`。
- 未驗證／限制：未執行完整 `python TCFMain.py -ts y`，因流程需使用者本機資料、模型、GPU/CPU 狀態與會產生工作池副作用。

### 2026-08-05 — Stage console readability pass 2

- 目標：延續主流程訊息美化，將最常出現在 `TCFMain.py -ts y` 輸出中的 stage 內部噪音改為較容易掃讀的摘要格式。
- 結果：`DataConverter`、`RunClassfier`、`CombineTestResult`、`Test_result_Vis` 與共用 `MP_utils`、`TCF_utils`、`df_utils` 開始共用 `utils.log_display`；DataFrame 輸出改為 shape/columns/head 摘要，多程序任務與 dataset/model directory picking 改為分段 key-value 顯示，任務 bins 與 sample counts 改為 compact summary。
- 驗證：`python -m py_compile ...`、`PYTHONPATH=PythonModule python - <<'PY' ...` 預覽顯示 helper、`git diff --check`。
- 未驗證／限制：未執行完整 `python TCFMain.py -ts y`，因流程需使用者本機資料、模型、GPU/CPU 狀態與會產生工作池副作用；py_compile 仍顯示既有 regex/path escape SyntaxWarning。


### 2026-08-05 — Root requirements, GitHub README, and lightweight tests

- 目標：補上根目錄模組需求、GitHub 專案頁面說明與可無副作用執行的功能測試。
- 結果：新增 `requirements.txt` 作為目前盤點的共用 runtime/test 依賴；README 改為記載安裝、輕量測試與完整流程資料/模型限制；新增 `tests/` 以 unittest 驗證 `utils.log_display` 與 README/requirements 基本契約。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile PythonModule/utils/log_display.py`、`git diff --check`。
- 未驗證／限制：未執行 `python -m pip install -r requirements.txt`，因會下載/安裝大量 ML dependencies；未執行完整 `TCFMain.py`，因需本機資料、模型與工作池。
