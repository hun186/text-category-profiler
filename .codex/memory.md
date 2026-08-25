# Project Memory

> 類型：Recent durable context。不是聊天紀錄或完整 changelog；只保存能讓後續任務少走彎路的近期成果。

## Current Focus

- 初始化狀態：`INITIALIZED`
- 目前工作焦點：維護 Python 文字分類／資料集轉換／BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 最近確認可工作的路徑：文件與靜態盤點；runtime smoke test 尚未確認。
- 需要延續的相容性／限制：未確認 fixture、模型、工作池與依賴前，不執行會搬移／刪除／批次寫入資料的流程命令。
- README 判定：`NEEDS_UPDATE`；原文件有實質內容但描述另一個 FastAPI/Elasticsearch RAG agent，已局部改寫為目前 repo 可查證狀態。

## Recent Outcomes

### 2026-08-24 — DatasetConverter bounded WeiTech workspace configuration

- 目標：推進 Phase 2，在 copy/rmtree 前正規化 WeiTech work-pool/work-ID path slice。
- 結果：frozen `WorkspaceConfig` 要求 active work ID 有 pool且為單一安全 component，plan/context/main不再自行join mutable args；下一步是 FixedTest/WeiTech-format input paths。
- 驗證：config/stage/entrypoint targeted tests、完整輕量 unittest、`py_compile`、isolated import與`git diff --check`。

### 2026-08-24 — DatasetConverter normalized mode configuration

- 目標：推進 Phase 2，將 source/WeiTech/extraction activation 從 mutable argparse namespace 正規化。
- 結果：frozen `ModeConfig`／`WorkMode` 保留 source priority與ignored extraction-task compatibility，main以context mode啟用WeiTech/extraction；下一步是單一外部 path slice validation。
- 驗證：config/stage/entrypoint targeted tests、完整輕量 unittest、`py_compile`、isolated import與`git diff --check`。

### 2026-08-24 — DatasetConverter normalized runtime process configuration

- 目標：推進 Phase 2，將 runtime discovery 產生的 process counts 正規化後注入 stage context。
- 結果：frozen `RuntimeConfig` 驗證兩種 positive integer counts，activation在filesystem/logger前拒絕 invalid injection，main只從context使用 counts；下一步是 mode validation。
- 驗證：config/stage/entrypoint targeted tests、完整輕量 unittest、`py_compile`、isolated import與`git diff --check`。

### 2026-08-24 — DatasetConverter normalized output configuration

- 目標：推進 Phase 2，停止 main 重複組合 canonical dataset artifact paths。
- 結果：frozen `OutputConfig` 於 activation 前驗證 path components並產生 main/count/fixed-test stems，plan/context共同擁有；下一步是 dependency-light process configuration。
- 驗證：config/stage/entrypoint targeted tests、完整輕量 unittest、`py_compile`、isolated import與`git diff --check`。

### 2026-08-24 — DatasetConverter normalized split configuration

- 目標：推進 Phase 2，讓 split ratios 由 normalized config 擁有並在 activation 前驗證。
- 結果：`SplitConfig` 拒絕非有限、負數與非 unit-sum ratios，`ConverterConfig` 擁有 split slice，main 不再讀 module-level mutable ratio mapping；下一步是最小 typed output config。
- 驗證：config/stage/entrypoint targeted tests、完整輕量 unittest、`py_compile`、isolated import與`git diff --check`。

### 2026-08-24 — DatasetConverter immutable converter configuration

- 目標：推進 Phase 2，停止 plan/context 擁有 mutable nested converter settings。
- 結果：frozen `ConverterConfig` 擁有具名 core fields與 recursively frozen reader policies，legacy mapping每次 fresh thaw；normalization在activation前驗證 width/fixed-test bound；下一步是 split/output config與集中 validation。
- 驗證：round-trip/ownership/validation tests、stage-plan compatibility tests、完整輕量 unittest、`py_compile`、isolated import與`git diff --check`。

### 2026-08-24 — DatasetConverter typed source configuration

- 目標：推進 Phase 2，停止 stage plan/context 直接擁有 mutable root/fixed-test lists。
- 結果：frozen `SourceConfig`／`SourceMode` 集中 source routing state，plan/context 只以 copy properties提供 legacy lists；下一步是最小 typed converter-settings slice 與集中 validation。
- 驗證：typed config immutability/mode tests、plan copy-ownership tests、targeted與完整輕量 unittest、`py_compile`、isolated import與`git diff --check`。

### 2026-08-24 — DatasetConverter dependency-light root paths

- 目標：完成上一批的優先事項，讓 stage plan normalization 不再載入 legacy application parameter bootstrap。
- 結果：debug／DRN／platform／malicious-domain root policy 移至 dependency-light config 並可注入 platform；新增直接執行 normalization 的 side-effect characterization tests；下一步是 typed source config 與隔離 CLI exit-code boundary。
- 驗證：config/plan/entrypoint targeted tests、isolated rejecting-finder import gate、完整輕量 unittest、`py_compile` 與 `git diff --check`。

### 2026-08-24 — DatasetConverter normalization／activation boundary

- 目標：推進 Phase 1，將 CLI/source normalization 與 filesystem、logger、timing activation 分開。
- 結果：frozen `StagePlan` 先承接正規化輸入，`activate_stage_context()` 再建立 `StageContext`；`main()` 明確依序呼叫，legacy `setArguments()` 保留薄 wrapper；下一步是移除 plan 對 legacy root-path bootstrap 的依賴。
- 驗證：entrypoint AST activation gates、isolated import、targeted與完整輕量 unittest、`py_compile`、`git diff --check`。

### 2026-08-21 — DatasetConverter named stage context

- 目標：推進 Phase 1，停止 bootstrap／main 透過 module globals 共享 logger、timing 與 mutable converter settings。
- 結果：frozen `StageContext` 提供具名 bootstrap handoff，`main()` 每次建立 fresh settings並使用 local timing/logger state；
  下一步是把 `setArguments()` 的純 normalization 與 filesystem/logger bootstrap 分開。
- 驗證：AST state-ownership gates、entrypoint/import/runtime targeted tests、完整輕量 unittest、`py_compile` 與 `git diff --check`。
