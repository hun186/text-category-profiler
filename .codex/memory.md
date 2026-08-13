# Project Memory

> 類型：Recent durable context。不是聊天紀錄或完整 changelog；只保存能讓後續任務少走彎路的近期成果。

## Current Focus

- 初始化狀態：`INITIALIZED`
- 目前工作焦點：維護 Python 文字分類／資料集轉換／BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 最近確認可工作的路徑：文件與靜態盤點；runtime smoke test 尚未確認。
- 需要延續的相容性／限制：未確認 fixture、模型、工作池與依賴前，不執行會搬移／刪除／批次寫入資料的流程命令。
- README 判定：`NEEDS_UPDATE`；原文件有實質內容但描述另一個 FastAPI/Elasticsearch RAG agent，已局部改寫為目前 repo 可查證狀態。

## Recent Outcomes

### 2026-08-13 — DatasetConverter reader transformation boundaries

- 目標：延續 Phase 4，隔離 reader 的 sampling、Elasticsearch provenance，以及一般 segment 轉碼／長度 eligibility。
- 結果：`select_document_samples()` 保留 shuffle/slice 契約；`build_elasticsearch_provenance()` 集中 ES path 與日期診斷並支援非字串無效日期；`prepare_sample_text()` 以 injected converter 固定 conversion-before-length 與 `len >= LenLBD` 契約。
- 延伸：`transform_sample_segment()` 以 immutable `SegmentResult` 收斂 layout、special/regex label、轉碼、長度、mapping 與 row assembly，明確區分 accepted、special-label 與 below-minimum drop，並保留 special bypass 與 missing mapping `KeyError`。
- 來源：`sample_sources.read_regular_text_document()` 以 immutable `SourceDocument` 固定 `.txt`／`.ai2` label routing 與 UTF-8 read adapter，保留 unlabelled txt skip 與 AI2 `Scrap` fallback。
- 清整：`apply_regular_cleaning_rules()` 隔離 label-aware regex cleaning，保留 exemption、mapping order 與累積 rules 重複套用的 legacy 契約。
- 文件：`prepare_document_segments()` 以 immutable `PreparedDocument` 固定各文字來源 normalization-before-slicing、labels 與 ordered segments 契約，production cleaner/divider 維持 injected adapters。
- CZJ：`read_czj_corpus_document()` 隔離 parameterized SQLite title lookup、null label `Scrap` fallback 與具診斷的 missing/malformed rows，並保證所有 fetch 路徑關閉 connection。
- 驗證：sample pipeline targeted tests、conversion fixture、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter regex input-label selection boundary

- 目標：延續 Phase 4，隔離 reader 的 regex interval matching 與 InfoScore label override。
- 結果：`select_rule_based_input_label()` 固定 lower-case matching、inclusive interval、最高分、同分後規則勝出與無命中 fallback；matcher 可注入，reader 保留薄呼叫。
- 驗證：sample pipeline targeted tests、conversion fixture、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter malformed-segment label boundary

- 目標：延續 Phase 4，隔離 reader 對數字、句點與重複字元異常 segment 的特殊輸出 label 判定。
- 結果：`detect_special_output_label()` 固定 legacy priority、strict 90% thresholds 與 residual-text gate；reader 保留長度／啟用 gate，不改其餘 label、OpenCC 或 sampling 行為。
- 驗證：sample pipeline targeted tests、conversion fixture、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter segment layout normalization boundary

- 目標：延續 Phase 4，隔離 reader 對 excessive newline 的文字排版清整規則。
- 結果：`normalize_segment_layout()` 固定大於 10% 才取代換行、恰好 10% 不變與空字串安全行為；reader 保留薄呼叫，不改 label、OpenCC、sampling 或 schema。
- 驗證：sample pipeline targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter sliced-text row assembly boundary

- 目標：延續 Phase 4，將 `SampleReader.textSegsToSamples()` 的共同 row assembly 與重型 reader adapters 分離。
- 結果：`assemble_sample_row()` 統一一般與 rule-based label 的 canonical sample mapping，不改 slicing、label、OpenCC 或 sampling 語意。
- 驗證：sample pipeline targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter reader row schema validation boundary

- 目標：延續 Phase 4，在 DataFrame／artifact 副作用前固定 reader rows 的共同 schema。
- 結果：`validate_sample_rows()` 以 source stage 與 row index 診斷非 mapping 或缺少 `file`／`InLabel`／`OutLabel`／`text`；保留 external rows 可省略 `PartNO` 並由既有 adapter 補零的相容契約。
- 驗證：sample pipeline 與 fixture targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter source metadata assembly and path-policy boundaries

- 目標：延續 Phase 4，隔離 `GetDataSRC()` 的 DataFrame adapter 與逐列 provenance metadata 組裝。
- 結果：`collect_source_metadata()` 以 immutable results 驗證 resolver shape；`GetDataSRC()` 保留薄 pandas adapter，移除會吞掉整批錯誤的 bare `except`。後續將 production path policy 搬到 dependency-free `source_metadata.py`，固定一般／Books／multi-label／unknown-label 行為並保留舊 import 與 keyword API。
- 驗證：source metadata、sample pipeline、entrypoint/source-role targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`；完整 CLI 仍受其他 runtime dependencies 與工作池需求限制。

### 2026-08-12 — DatasetConverter multi-label aggregation boundary

- 目標：延續 Phase 4，將 reader multi-label counters 的彙總規則從 stage helper 抽成純轉換。
- 結果：`aggregate_multi_label_counts()` 集中 label-set 正規化與跨 worker 累加，保留 `MultiLabCt()` 薄相容層與 `None` 行為，malformed payload 會指出 result index。
- 驗證：sample pipeline targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter reader result assembly boundary

- 目標：開始 Phase 4，將 process reader jobs 的結果組裝從 DataFrame 與輸出流程分離。
- 結果：`collect_reader_results()` 純函式以 `CollectedSamples` 回傳有序 sample rows 與 multi-label counters；空結果不再需要 `zip(*)` 分支，malformed adapter result 會在副作用前帶 index 失敗。
- 驗證：sample pipeline、source collection/source role、fixture integration 與 split targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter content-hash selection boundary

- 目標：延續 Phase 3，將 filesystem discovery 後的 content hash 去重規則與 process/hash adapter 分離。
- 結果：`select_unique_content_paths()` 純函式集中 worker mappings 合併與同 hash 保留最後 path 的既有規則；`DataConvertJobGenerater` 保留 SHA-1、前 100 MB 與 multiprocessing 行為，並新增跨 batch duplicate 與空結果測試。
- 驗證：source collection/source-role/fixture targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-12 — DatasetConverter typed source discovery boundary

- 目標：延續 Phase 3，讓 filesystem source 的用途與探索政策不再隱含於 caller，且讓 FixedTest 探索採用同一個可隔離測試的邊界。
- 結果：`SourceSpec`／`SourceRole` 描述 regular、fixed-test、CZJ corpus 的 roots、extensions、regex 與排除政策；regular/CZJ job generation 和 FixedTest discovery 共用 injected-walker adapter，同時保留 FixedTest 不排除 `UnTagged`／`UnSpec` 的舊行為。既有 dependency-free fixture 仍涵蓋 source → worker → split → TSV slice。
- 驗證：source collection、entrypoint/source-role、fixture integration 與 split targeted tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`。

### 2026-08-11 — Test-only conversion with no regular source rows

- 目標：讓只提供 FixedTest／Elasticsearch 測試來源、沒有一般輸入 root 的轉換流程能繼續載入外部測試樣本，而不是在 split 規劃時因空 DataFrame 缺少 `OutLabel` 而中止。
- 結果：一般來源沒有資料時以 `DataFrame(columns=...)` 建立標準 sample schema，避免 pandas 對零欄 DataFrame 直接改名所產生的 `Length mismatch`，也避免 split 階段缺少 `OutLabel`；探索、reader job、row collection 與 conversion 摘要會分別標示 `Regular Source`、`Fixed Test Source` 或 `Elasticsearch Source`，FixedTest 另列遞迴探索數量與 preview，清楚區分預期為零的普通來源和已找到的固定測試檔案。
- 驗證：dataset split regression tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check`；完整 Windows FixedTest／模型推論仍需使用者環境驗證。

### 2026-08-11 — Optional Hugging Face optimizer checkpoints

- 目標：避免訓練 checkpoint 預設保留體積較大的 `optimizer.pt`，同時讓需要續訓狀態的使用者可明確開啟。
- 結果：新增 `--SaveOptimizer`／`-SaveOptimizer` boolean CLI，預設 `false` 並映射到 Hugging Face `save_only_model=True`；訓練開始前會顯示 `optimizer.pt` 是否保留及相反設定的命令提示。
- 修正：Hugging Face `TrainingArguments` 實例使用 `training_args` 命名，避免遮蔽 module-scope CLI `args` 並在讀取 `args.SaveOptimizer` 時觸發 `UnboundLocalError`；加入 symbol-table regression test。
- 驗證：optimizer checkpoint 設定、提示與 CLI namespace scope 的 isolated unittest、相關檔案 `py_compile`、`git diff --check`；完整輕量 suite 有一個既有 Windows path separator assertion 失敗，且未執行完整模型訓練。

### 2026-08-11 — README core capability diagrams and information architecture

- 目標：在 GitHub README 清楚介紹模型基礎的訓練集覆蓋調優，以及下游文本切片、算分與推薦兩項核心能力。
- 結果：README 依「核心能力 → 專案全景 → 快速開始」重新編排；新增 AI 代理人連結當前議題、taxonomy／來源設計、正文爬取、品質閘門與訓練回饋的 SVG；方法控制點和特色圖均直接展開，無需點擊才能閱讀。
- 驗證：兩張方法論 SVG XML 解析、README 文件契約測試、完整輕量 unittest 與 `git diff --check`。

### 2026-08-11 — DatasetConverter split planning and deduplication refactor

- 目標：將 `DataConverter.py` 的 train/dev/test 切分責任抽離成可獨立測試邏輯，消除 split 邊界重疊與跨 split 重複；同時確保少類樣本擴增不會污染 dev/test。
- 結果：`dataset_split.py` 集中切分前去重、split plan、train label 覆蓋與 positional slicing；augmentation 改為切分完成後只補足 train label，並保留來源 metadata，避免擴增變體被隨機分配到評估集。
- 驗證：新增 ratio、去重、split coverage 與 train-only augmentation tests；當容器缺少 pandas 時，純 plan tests 仍會執行，DataFrame tests 會明確 skip。

### 2026-08-11 — PyTorch Transformers path injector cleanup

- 目標：繼續淘汰 active classifier code 對 legacy `PackageImporter` 與機器特定搜尋路徑的依賴。
- 結果：`TextClassification_transformers.py` 直接執行時只加入由 `__file__` 推導的 repository root；package layout test 將此 backend 納入防退步邊界。
- 驗證：`python -m unittest tests.test_package_layout`、`python -m unittest discover -s tests`、相關檔案 `py_compile`、`git diff --check`；未執行完整模型訓練／推論，因需要本機模型、資料與 ML runtime。

### 2026-08-11 — Test result visualization residual console cleanup

- 目標：整理 Dash layout 與 callback 中殘留的 start/finished、PID、raw row data、filtered result 更新雜訊與 Windows `taskkill` 找不到行程訊息。
- 結果：上傳、已完成任務、label/mission/filter selection 與 chart refresh 改為分段 key-value 摘要；資料表建置細節、使用者連線資料與 prediction query 進度只保留在 log file；callback 改顯示各自耗時，不再重複顯示整個 server uptime；清理不存在的舊 server 時不再顯示工具原始錯誤，也不再無條件等待 5 秒。
- 驗證：`python -m unittest discover -s tests`、相關檔案 `py_compile`、`git diff --check`；完整 Dash 流程仍需使用者的 Windows 工作池與 runtime 驗證。

### 2026-08-11 — Test result visualization console readability

- 目標：整理 Test_result_Vis 啟動時的 graph、InfoScore、Dash table 與 prediction chart 雜訊。
- 結果：graph/table/chart 訊息改為 section 與 key-value 摘要，移除 raw DataFrame/JSON/plugin parameter dumps；修正零值 timer 印出 epoch 秒數、字典記憶體量測目標與 Tulip deprecated `input property` key。
- 驗證：`python -m unittest discover -s tests`、相關檔案 `py_compile`、`git diff --check`；完整 Dash/Tulip 流程仍需使用者的 Windows 工作池與 runtime 驗證。


### 2026-08-06 — Package 內部 path injector 淘汰

- 目標：繼續 `text_category_profiler` package 遷移，先移除 package 自身與 root orchestration/parameter layer 對 legacy `PackageImporter` 的依賴。
- 結果：`text_category_profiler/`、`TCFMain.py` 與 `TCF_Params/` 不再匯入 `PackageImport`；package layout characterization test 會掃描 AST 防止這些邊界退回 path injection。
- 邊界：各 stage 直接執行仍使用既有 bootstrap，相容行為留待後續批次處理，因此尚未勾選「所有 active entry points」完成。

### 2026-08-06 — Python namespace aligned with `text-category-profiler`

- 目標：移除沿用舊 TopicClassification 名稱的 `tcf` 縮寫，讓 Python package 可直接對應目前 repository 名稱。
- 結果：根目錄 package 改名為 `text_category_profiler/`，active application code 與 tests 統一使用 `text_category_profiler.<domain>.<module>`；README 與 current-state、decision、backlog、migration 文件已同步。
- 相容邊界：本批不改名 `TCFMain.py`、`TCF_Params/`、`TCF_utils.py`、CLI options 或 stage handoff；`BertScript/TRV_deploy/` deployment snapshot 也保持獨立。

### 2026-08-06 — `tcf_utils` namespace rename alignment

- 目標：在共用工具目錄改名為根目錄 `tcf_utils/` 後，消除程式與 current-state 文件中殘留的 `utils` import 與 `PythonModule/utils` 路徑。
- 結果：active application code 與輕量測試統一改用 `tcf_utils.<domain>.<module>`；README、project、architecture、contracts、decision 與 migration/backlog 說明也同步新邊界。
- 保留邊界：`BertScript/TRV_deploy/` 是獨立 deployment snapshot，本批不將其內部舊 package 誤改為尚未佈署的根目錄 package。

### 2026-08-06 — PythonModule utilities domain migration

- 目標：將 `PythonModule/utils/` 的共用模組依責任分流，降低所有 helper 平放在單一 package root 的耦合。
- 結果：production utilities 搬入 `core`、`data`、`concurrency`、`pipeline`、`text`、`visualization`、`integrations` 七個 package，並同步更新 repository 內 imports；新增 layout contract test 防止已遷移模組回流根目錄或使用舊 import。
- 驗證：`python -m unittest discover -s tests`、針對遷移檔案的 `py_compile`、`git diff --check`。



### 2026-08-06 — Windows ModernBERT eager fallback

- 目標：修正 mmBERT／ModernBERT 在 Windows 匯入時因 `@torch.compile` 觸發「Windows not yet supported」而無法開始訓練。
- 結果：Windows 上會在載入 Transformers 前將 `torch.compile` 降級為 eager no-op；同時移除完整 tokenized sample dump，並將模型路徑探測濃縮為單一 checkpoint 訊息。
- 驗證：`python -m unittest discover -s tests`、相關檔案 `py_compile`、`git diff --check`；完整訓練仍需 Windows 模型／資料／GPU 環境驗證。


### 2026-08-05 — README workflow and feature SVGs

- 目標：在 GitHub README 頁面加入工作流程圖與特色介紹圖。
- 結果：新增 `docs/assets/workflow.svg` 與 `docs/assets/features.svg`，並在 README 目前狀態後插入「工作流程與特色」區塊引用兩張 SVG。
- 驗證：`python -m unittest discover -s tests`、`git diff --check`。

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


### 2026-08-05 — PytorchMMBERT model type and configurable transformer max length

- 目標：讓 Hugging Face transformer 分類流程可用本機 `mmBERT-base` 作為新 base model，並把 tokenizer truncation 長度抽成參數但維持預設 `180`。
- 結果：新增 `PytorchMMBERT` 對應 `mmBERT-base`，同步 PyTorch checkpoint/result path 分支、RunClassfier 指令傳遞與 DataConverter tokenizer fallback；新增 `-MaxSeqLen/--MaxSeqLength`。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile PythonModule/utils/TCF_utils.py BertScript/TextClassification_transformers.py DatasetConverter/sampleHandler.py DatasetConverter/DataConverter.py BertScript/RunClassfier.py`、`git diff --check`。
- 未驗證／限制：未執行完整 mmBERT 訓練，因需本機模型、依賴、GPU 與工作池資料。


### 2026-08-05 — DataConverter max length logging and elapsed timer fallback

- 目標：修正 FixedTest conversion 呼叫未傳 `start_time` 時的 elapsed time TypeError，並在轉換階段顯示 `MaxSeqLength`。
- 結果：`BuildSamplesDfFromPaths` 會在 `start_time is None` 時自行初始化時間；設定摘要與 tokenizer model directory log 都會顯示 `MaxSeqLength`。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile DatasetConverter/DataConverter.py PythonModule/utils/log_display.py`、`git diff --check`。
- 未驗證／限制：容器缺少 `numpy`，無法用 runtime snippet 匯入 `utils.TCF_utils` 驗證 argparse 實際輸出；未執行完整 DataConverter，因會讀寫工作池資料。

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

### 2026-08-05 — Compact stage command logging

- 目標：讓 `TCFMain.py` 階段 handoff command 不再每個參數各佔一行，減少 DataConverter/RunClassfier 等長命令輸出佔用空間。
- 結果：`utils.log_display.print_command()` 改為依終端寬度將多個 shell-quoted 參數合併到同一列，仍用反斜線續行保留可複製執行性；新增 unittest 覆蓋長命令分組。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile PythonModule/utils/log_display.py`、`git diff --check`。

### 2026-08-05 — Suppress repeated multiprocessing startup messages

- 目標：避免 multiprocessing spawn/import 導致 `cwd`、Python `istarmap` 選擇、`ROOTPATHList` 與 process count 說明在每個 worker 或重複計算時洗板。
- 結果：新增 `utils.log_display.print_once()`，預設只在主程序輸出同 key 訊息一次；DataConverter cwd、TCFParameters ROOTPATHList 與 MP_utils Python version banner 改用一次性輸出；`ComputeSPCNProcess()` 不再為取得 basic process 上限重印 basic process 提醒。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile PythonModule/utils/log_display.py PythonModule/utils/MP_utils.py TCF_Params/TCFParameters.py DatasetConverter/DataConverter.py`、`git diff --check`。

### 2026-08-05 — Tidy DataConverter topic tree output

- 目標：整理 DataConverter 產生 InfoScoreTable 與 topic tree labels 時過於雜亂的 console 輸出。
- 結果：`dfOutputer` 改為只輸出 output path、shape、columns 摘要，不再直接印 DataFrame head；移除 `ListDiff()` 的 `List1[0:15]` debug print；topic tree file/label 訊息改為短 key-value 摘要；import-time `ConverterParameters` 與 TSV helper 的 process-count 估算改走 quiet mode，避免在這段輸出中插入 process 提醒。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile PythonModule/utils/df_utils.py PythonModule/utils/utilities.py PythonModule/utils/MP_utils.py DatasetConverter/DataConverter.py DatasetConverter/ConverterParameters.py ClassesTree/ClassesTree_utils.py`、`git diff --check`。

### 2026-08-05 — Consolidate duplicate-removal console output

- 目標：整理 DataConverter 產製資料集檔案與移除重複文章時舊式 `print`、分隔線、multicore preview 與 PID log 交錯造成的雜亂輸出。
- 結果：dataset generation 改用 section/key-value；DataConverter job、file discovery、duplicate-removal start/result 與 tokenizer modelDir 改為摘要；空檔案清單時不再建立 hash worker；single-process multicore job 不再印 queue banner、job preview 與 pretest 訊息；FileHashDictBuilder preview 改為單行。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile DatasetConverter/DataConverter.py PythonModule/utils/MP_utils.py PythonModule/utils/utilities.py`、`git diff --check`。

### 2026-08-05 — Consolidate directory picking and sample loading output

- 目標：整理 dataset/model directory picker、LabelConvertDict 與 sample loading 階段的新舊混雜輸出。
- 結果：directory picker 改為 roots/candidates/selection 三個 key-value 區塊，不再以 PID log 重印選到的 modelDir；LabelConvertDict 只在 console 印 mode/count/converted 摘要，完整 mapping 仍寫入 dataset.txt；sample loading 與 rows-to-DataFrame 改為單一摘要，移除多段 start/finished、elapsed 與 row preview 分隔線。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile PythonModule/utils/TCF_utils.py DatasetConverter/DataConverter.py PythonModule/utils/df_utils.py`、`git diff --check`。

### 2026-08-05 — Consolidate empty row-list and DataFrame conversion output

- 目標：整理 Row_List 建構完成、空 row list、DataFrame 去重、空 DataFrame warning 與零樣本結果的舊式分隔線/print 輸出。
- 結果：空 row list 改為 warning；Src/type columns、dataset conversion result 與 duplicate rows 改為 key-value 摘要；移除空 DataFrame dump、columns dump、row preview 與重複 elapsed；零樣本詳細路徑仍寫入 dataset count file。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile DatasetConverter/DataConverter.py PythonModule/utils/df_utils.py`、`git diff --check`。

### 2026-08-05 — Consolidate DataFrame output handoff and SQLite index logs

- 目標：整理 DataFrame output job preview、SQLite index creation、Excel column width 與 dataset generation handoff 中殘留的舊式 print/PID log。
- 結果：dfOutputer/show、DatasetGenerator/show 與 DataFrame filter job 改為 key-value；SQLite index SQL/debug print 改為只寫 log file 不印 console；Excel 欄寬提示改為 key-value；Generate dataset files 後的 elapsed、FixedTestPATHList、OUTPUTMAIN 改為單一 handoff 摘要。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile DatasetConverter/DataConverter.py PythonModule/utils/df_utils.py PythonModule/utils/DB_utils.py`、`git diff --check`。

### 2026-08-05 — Consolidate dataset split generation output

- 目標：整理 Generate dataset files 階段中 train/validation/test set generation、fixed-test/es sample handoff 與 split dedup 的舊式 PID log/分隔線輸出。
- 結果：新增 Dataset split plan、Generate dataset split、Fixed test samples、Dataset split dedup 與 Dataset split source counts 摘要；移除 `Generating ... set` PID log、fixed-test/es ad-hoc print 與 dedup 分隔線；保留實際 dfOutputer 輸出行為。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile DatasetConverter/DataConverter.py`、`git diff --check`。

### 2026-08-05 — Consolidate sample reader preview and elapsed warnings

- 目標：整理 fixed-test sample reader job preview 中 FileName、LabelList[:20]、width/mode 等舊式輸出，並移除缺少 start_time 時的 ShowElapsedTime warning 噪音。
- 結果：`SampleReader.show()` 改為 Sample reader job key-value 摘要，label preview 縮短並顯示 label count；`ShowElapsedTime(None)` 改為安靜返回 None；DataConverter stage done 不再額外 `print(ShowElapsedTime(...))`。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile DatasetConverter/sampleHandler.py PythonModule/utils/utilities.py DatasetConverter/DataConverter.py`、`git diff --check`。

### 2026-08-05 — Consolidate DataFrame parallel and TSV check output

- 目標：整理 fixed-test dataset output 後殘留的 DataFrame parallel apply 中文 print、TSV null-byte PID log 與 exeTimeDict dump。
- 結果：DataFrame parallel apply 改為 key-value，Windows fallback 改為 warning；TSV null-byte check 改為 console 摘要且詳細訊息只寫 log；DataConverter timing 改為 key-value，不再 print raw exeTimeDict。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile PythonModule/utils/MP_utils.py DatasetConverter/DataConverter.py`、`git diff --check`。

### 2026-08-05 — Consolidate RunClassfier startup and resource logs

- 目標：整理 RunClassfier stage startup、CPU/GPU hybrid resource check、missing sql3 count 與 prediction output files 中殘留的 PID log/長路徑輸出。
- 結果：RunClassfier workspace、resource check/result、missing dataset count source 與 prediction output files 改為 key-value/warning 摘要；RunClassfier started 與 resource OK 詳細訊息改為只寫 log file；prediction file list 使用 summarize_sequence 縮短。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile BertScript/RunClassfier.py PythonModule/utils/conformer.py`、`git diff --check`。

### 2026-08-05 — RunClassfier command noise redirected to logs

- 目標：避免 RunClassfier 呼叫 `TextClassification_transformers.py` 時，TensorFlow／bitsandbytes／transformers 的 stderr warning 因子程序與平行化重複輸出而洗板。
- 結果：RunClassfier 的模型命令現在統一將 stdout/stderr 導入 `logs/RunClassfier.log`；console 只顯示精簡的 command/log path 摘要與 handoff，不再印舊式 `BatCMD` 分隔線、`Check ... log` 或 `RC Line 262` debug 訊息。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile BertScript/RunClassfier.py`、`git diff --check`。

### 2026-08-05 — Consolidate CombineTestResult verification logs

- 目標：整理 CombineTestResult 開始、來源查詢、verification dataframe、match count 與 handoff 段落中殘留的 PID log、debug sample text、大型 DataFrame sample 與重複 multiprocessing banner。
- 結果：CombineTestResult workspace/source DB/source lookup/sort/match/handoff 改為 key-value 摘要；移除固定長文本查詢與 `df_map_result.sample` debug 輸出；process count 採 quiet mode；`print_once()` 透過環境旗標讓 Windows spawn workers 繼承一次性訊息狀態，降低 `MP_utils.py` Python version banner 洗板。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile BertScript/CombineTestResult.py PythonModule/utils/log_display.py`、`git diff --check`。

### 2026-08-06 — DataConverter multiprocessing console noise

- 目標：避免 Windows spawn worker 重複輸出訓練模式、工作目錄與 Dash 相依套件棄用警告。
- 結果：訓練模式提示只由 `MainProcess` 顯示；EXTConverter import 不再無條件印出 cwd；DataConverter 將 Dash 視覺化依賴延遲到實際建立視覺化 job 時載入。
- 驗證：`python -m unittest discover -s tests`、相關檔案 `py_compile`、`git diff --check`；未執行完整 Windows DataConverter，因需本機資料、模型與完整依賴。

### 2026-08-06 — CombineTestResult PytorchMMBERT support

- 目標：修正 PytorchMMBERT prediction 已完成後，CombineTestResult 因未建立 `df_map_result` 而發生 NameError。
- 結果：CombineTestResult 的 PyTorch result mapping 改用共用 `PYTORCH_MODEL_TYPES`，因此涵蓋 PytorchMMBERT；未知 ModelType 會在 mapping 階段回報明確 ValueError。
- 驗證：`python -m unittest discover -s tests`、`python -m py_compile BertScript/CombineTestResult.py`、`git diff --check`；完整 Windows pipeline 仍需本機資料與模型驗證。
