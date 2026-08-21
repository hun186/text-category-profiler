# Project Memory

> 類型：Recent durable context。不是聊天紀錄或完整 changelog；只保存能讓後續任務少走彎路的近期成果。

## Current Focus

- 初始化狀態：`INITIALIZED`
- 目前工作焦點：維護 Python 文字分類／資料集轉換／BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 最近確認可工作的路徑：文件與靜態盤點；runtime smoke test 尚未確認。
- 需要延續的相容性／限制：未確認 fixture、模型、工作池與依賴前，不執行會搬移／刪除／批次寫入資料的流程命令。
- README 判定：`NEEDS_UPDATE`；原文件有實質內容但描述另一個 FastAPI/Elasticsearch RAG agent，已局部改寫為目前 repo 可查證狀態。

## Recent Outcomes

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

### 2026-08-14 — DatasetConverter entrypoint configuration boundary

- 目標：推進 Phase 1／2，解除 canonical entrypoint 對 application／converter parameter bootstrap與import-time resource probe的耦合。
- 結果：dependency-light `DatasetConverter.config`提供path/static defaults、frozen split及fresh nested reader settings；process counts
  在`main()` bootstrap後計算，entrypoint不再import兩個legacy parameter modules；下一blocker為extraction的`tqdm` integration。
- 驗證：config characterization、AST/subprocess import gates、完整輕量 unittest、`py_compile`與`git diff --check`。

### 2026-08-14 — DatasetConverter taxonomy config／validation boundary

- 目標：推進 Phase 2／3，將 taxonomy label normalization／InfoScore validation 從 legacy settings wrapper 抽離。
- 結果：immutable `TaxonomyConfig` 集中 namespace mapping，injected loader與 frozen validation固定 adapter／label契約；
  `loadLabels()`移除 mutable default、複製 caller settings且保留 legacy CLI/output/error gate。
- 驗證：taxonomy config/fake-loader isolated tests、AST wrapper gate、完整輕量 unittest、`py_compile`與`git diff --check`。

### 2026-08-14 — DatasetConverter functional package layout

- 目標：依重構指引降低 DatasetConverter root 的 Python module 平鋪數量，同時維持已固定的 import／行為契約。
- 結果：16 個已抽離 modules 分流至 `core/`、`sources/`、`adapters/`；所有 repository callers 與 regression tests 使用新路徑，子套件不 eager import optional dependencies。
- 驗證：完整輕量 unittest、targeted DatasetConverter suites、`py_compile`、import-path search 與 `git diff --check`。
### 2026-08-14 — DatasetConverter entrypoint DataFrame constructor boundary

- 目標：推進 Phase 1，移除 canonical entrypoint的 direct pandas import與無 caller的 pandas.io/Plotly/colorama imports。
- 結果：`dataframe_source`以 function-local pandas import集中 from-dict、empty與 concat contracts；conversion仍使用真實
  pandas objects，CLI、split、output與 handoff行為未改。
- 驗證：fake-pandas forwarding與 AST import gates、完整輕量 unittest；isolated import下一 blocker收斂為
  `TCFParameters -> core.utilities -> psutil`。

### 2026-08-13 — DatasetConverter legacy CZJ corpus fan-out removal

- 目標：推進 Phase 1/4，移除 reader 中非 canonical、pandas-backed 的整庫 corpus fan-out。
- 結果：canonical generator title jobs與 `read_czj_corpus_document()` flow保留；刪除未 return、會輸出 raw data且遺失 reader
  policies 的 nested-reader branch，reader 不再 import `dfFromSQLite3`。
- 驗證：AST dataframe/fan-out gates、CZJ source/source-role targeted suites、完整輕量 unittest、`py_compile`、`git diff --check`。

### 2026-08-13 — DatasetConverter reader cwd/path-injector removal

- 目標：推進 Phase 1，停止 reader import 修改 `sys.path`、process cwd 與 console。
- 結果：移除 `PackageImporter.proc()` 與 directory-name-based `os.chdir("../")`；DataConverter direct script 繼續以
  `__file__` bootstrap repository root，reader API/path semantics 不變。
- 驗證：AST path-injector/chdir gates、entrypoint/package-layout targeted suites、完整輕量 unittest、`py_compile`、
  `git diff --check`；isolated import 仍受缺少 `psutil` 阻擋。
