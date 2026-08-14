# Project Memory

> 類型：Recent durable context。不是聊天紀錄或完整 changelog；只保存能讓後續任務少走彎路的近期成果。

## Current Focus

- 初始化狀態：`INITIALIZED`
- 目前工作焦點：維護 Python 文字分類／資料集轉換／BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 最近確認可工作的路徑：文件與靜態盤點；runtime smoke test 尚未確認。
- 需要延續的相容性／限制：未確認 fixture、模型、工作池與依賴前，不執行會搬移／刪除／批次寫入資料的流程命令。
- README 判定：`NEEDS_UPDATE`；原文件有實質內容但描述另一個 FastAPI/Elasticsearch RAG agent，已局部改寫為目前 repo 可查證狀態。

## Recent Outcomes

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

### 2026-08-13 — DatasetConverter reader maintenance probe removal

- 目標：推進 Phase 1，移除 reader module 中無外部 caller 的 tokenizer maintenance script 與其 CLI coupling。
- 結果：刪除 `tokenization_wrap_Test()`、內嵌長文本及 `__main__` block；reader 不再 import CLI parser/model checkpoint helper，
  production tokenizer wrapper 與 reader API 不變。
- 驗證：AST probe/CLI/main gates、tokenizer/package-layout targeted suites、完整輕量 unittest、`py_compile`、`git diff --check`。

### 2026-08-13 — DatasetConverter tokenizer word-analysis boundary

- 目標：延續 Phase 1/4，移除 production wrapper 中未回傳的 tokenizer debug mapping 工作。
- 結果：immutable `TokenWordAnalysis` 與純 `analyze_token_word_mapping()` 固定 legacy word/span/token mapping；wrapper 保留
  `word_analysis` keyword 與 dict shape，且只在 debug 可觀察時執行分析。
- 驗證：fake encoding word/multi-token/repeated-space tests、tokenizer targeted suites、完整輕量 unittest、`py_compile` 與
  `git diff --check`。

### 2026-08-13 — DatasetConverter OpenCC integration boundary

- 目標：推進 Phase 1，讓不使用文字轉碼的 reader paths 不再因 module-scope OpenCC import 依賴 optional runtime。
- 結果：`opencc_source.convert_text()` 以 function-local import 集中 legacy conversion contract；reader 注入 adapter，保留 conversion-before-length、special-label bypass 與每 segment 建立 converter 的既有行為。
- 驗證：isolated fake-module factory test、reader/adapter module-scope import AST gates、sample pipeline 與 package-layout targeted tests。

### 2026-08-13 — DatasetConverter tokenizer integration and slicing boundaries

- 目標：推進 Phase 1，讓非 tokenizer reader paths 不再因 module-scope Transformers import 依賴 optional runtime。
- 結果：`tokenizer_source.load_auto_tokenizer()` 以 function-local import 集中 legacy factory contract；後續新增 immutable
  `TokenizedChunks` 與 dependency-free `split_tokenized_context()`，固定 token reserve/group/span slicing、boundary 去重與
  optional retokenization；`TokenizerModel`／`resolve_tokenizer_model()` 另隔離 local/fallback/nested-checkpoint discovery，
  legacy wrapper 保留 dict API、warning 與既有 encoding reuse。
- 驗證：isolated factory/model-resolution、fake-tokenizer slicing/empty/budget tests、module-scope import AST gates、完整
  輕量 unittest、相關 `py_compile` 與 `git diff --check`。

### 2026-08-13 — DatasetConverter pipeline/dataset config isolation

- 目標：推進 Phase 2，消除 active pipeline function 與 dataset generator mutable defaults／caller config leakage。
- 結果：`BuildSamplesDfFromPaths()`、`DatasetGenerator.__init__()` 改以 `None` defaults 並逐 call/instance copy source、split、
  ES 與 DC settings；保留 keyword、empty default、split/output contracts。
- 驗證：AST gates、fixture integration/split/source-role targeted tests、完整輕量 unittest、`py_compile`、`git diff --check`。
