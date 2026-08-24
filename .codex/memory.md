# Project Memory

> 類型：Recent durable context。不是聊天紀錄或完整 changelog；只保存能讓後續任務少走彎路的近期成果。

## Current Focus

- 初始化狀態：`INITIALIZED`
- 目前工作焦點：維護 Python 文字分類／資料集轉換／BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 最近確認可工作的路徑：文件與靜態盤點；runtime smoke test 尚未確認。
- 需要延續的相容性／限制：未確認 fixture、模型、工作池與依賴前，不執行會搬移／刪除／批次寫入資料的流程命令。
- README 判定：`NEEDS_UPDATE`；原文件有實質內容但描述另一個 FastAPI/Elasticsearch RAG agent，已局部改寫為目前 repo 可查證狀態。

## Recent Outcomes

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

### 2026-08-21 — DatasetConverter conversion runtime activation boundary

- 目標：推進 Phase 1，解除 canonical entrypoint 對 numpy／pandas-backed conversion runtime 的 module-scope coupling。
- 結果：`runtime_source` 以 function-local imports 轉接 logger、multiprocessing、DataFrame output／rows 與 ES fetch contracts；
  `DatasetConverter.DataConverter` 已可在缺少 numpy 的目前環境 isolated import，下一步是收斂 bootstrap／stage globals。
- 驗證：fake-module forwarding、AST／rejecting-finder activation gates、isolated import、完整輕量 unittest、`py_compile` 與 `git diff --check`。

### 2026-08-21 — DatasetConverter class-tree activation boundary

- 目標：推進 Phase 1，避免 canonical entrypoint 在未使用 taxonomy tree 行為時載入 legacy class-tree runtime。
- 結果：`tree_source` 以 function-local imports 轉接 tree-file、node、subtopic 與 closest-parent contracts；isolated import 下一 blocker 收斂為 `df_utils -> numpy`。
- 驗證：fake-module forwarding、AST activation gate、完整輕量 unittest、`py_compile` 與 `git diff --check`。

### 2026-08-14 — DatasetConverter shared pipeline activation boundary

- 目標：推進Phase 1，避免canonical module import為shared CLI/path/handoff policies載入`MP_utils`、numpy與pandas runtime。
- 結果：`pipeline_source`以function-local imports轉接parser、directory/model/label/FixedTest與TaskConnector contracts；下一個
  isolated import blocker收斂為`ClassesTree_utils -> pandas`。
- 驗證：fake-module forwarding、AST activation gates、完整輕量unittest、`py_compile`、`git diff --check`。

### 2026-08-14 — DatasetConverter dependency-light stage utilities

- 目標：推進Phase 1，移除canonical entrypoint對含`psutil`等重型依賴的generic utilities module-scope coupling。
- 結果：`core/stage_utils`集中stage filesystem、chunk、hash、sampling、augmentation與timing contracts；maintenance imports改為
  function-local，isolated import下一blocker收斂為`TCF_utils -> MP_utils -> numpy`。
- 驗證：temporary filesystem/hash、seeded random、timing、AST gates、完整輕量unittest、`py_compile`、`git diff --check`。

### 2026-08-14 — DatasetConverter extraction activation boundary

- 目標：推進Phase 1，讓未啟用extraction／WeiTech corpus conversion的流程不載入有副作用且依賴`tqdm`的EXTConverter modules。
- 結果：`extraction_source`以function-local imports固定rule identity、extractor keywords與builder transform contracts；canonical
  entrypoint不再eager import三個legacy modules，isolated import下一blocker收斂為generic utilities的`psutil`。
- 驗證：fake-module adapter/AST activation gates、targeted與完整輕量unittest、`py_compile`、`git diff --check`。
