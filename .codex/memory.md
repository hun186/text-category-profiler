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
