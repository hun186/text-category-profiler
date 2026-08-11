# Architecture

> 類型：Current state。描述目前有效的系統模型；不要追加按日期排列的改動紀錄。

## 系統邊界

- 系統負責：文字資料整理、分類器資料集產生、BERT／XLM 訓練或推論、分類結果合併與視覺化分析。
- 系統不負責：目前未證實提供常駐 HTTP API、RAG agent runtime、正式部署或套件發布。
- 上游：文字檔、工作池任務、固定測試資料、模型目錄、可選 Elasticsearch／外部資料匯入來源。
- 下游：分類結果 SQLite／TSV／log／視覺化輸出與工作池交付目錄。

## 高階元件

| 元件／模組 | 責任 | 輸入 | 輸出 | 主要位置 |
| --- | --- | --- | --- | --- |
| Flow orchestrator | 串接資料轉換、分類、結果合併、視覺化與清理 | CLI args、工作池路徑、模型／資料設定 | Stage commands、工作目錄狀態、最終輸出 | `TCFMain.py` |
| Parameter layer | 定義 CLI args、預設工作池與任務模式 | command-line args、平台資訊 | argparse namespace、常數 | `text_category_profiler/pipeline/TCF_utils.py`, `TCF_Params/TCFParameters.py` |
| Dataset converter | 建立分類器需要的 dataset／SQLite；切分前依 label/text 去重，以可測試的 split plan 建立 train/dev/test，再僅對 train 的少類樣本擴增 | 原始文字、固定測試資料、ES job config | `train.tsv`、`dev.tsv`、`test.tsv`、dataset DB | `DatasetConverter/DataConverter.py`, `DatasetConverter/dataset_split.py` |
| Classifier runner | 執行 BERT／XLM 訓練或推論並管理模型／dataset handoff | dataset dir、model dir、resource availability | prediction output、model artifacts、logs | `BertScript/RunClassfier.py`, `BertScript/run_classifier*.py` |
| Result analysis | 合併原文與預測結果，產生分析與視覺化 | prediction result、dataset DB、label list | combined SQLite／分析資料／Dash UI | `BertScript/CombineTestResult.py`, `BertScript/Test_result_Vis.py` |
| Shared utilities | 依領域提供 core、data、concurrency、pipeline、text、visualization 與 integrations 工具 | 跨模組 utility calls | 共用 helper behavior | `text_category_profiler/<domain>/` |
| Class tree tools | label tree 與分類樹視覺化／分析 | topic tree、labels | tree analysis／visualization | `ClassesTree/` |

## 主要資料流

1. `TCFMain.py` 讀取 `ClassfierOptionParser()` 與 `TCF_Params` 預設值，必要時從工作池挑選 workID。
2. `DataConvert()` 組出 `python DatasetConverter/DataConverter.py ...`，建立或定位 `_rdy_for_RunClassfier` handoff dataset。
3. `RunClassfier()` 組出 `python BertScript/RunClassfier.py ...`，分類器讀取 dataset 與模型目錄，輸出預測結果。
4. 若 `args.test == True`，`ArticleAnalysis()` 執行結果合併與視覺化分析。
5. `BackupAndClean()` 依任務模式將輸出搬回工作池、備份或清理暫存資料。

## 依賴方向與模組邊界

- 根流程應由 `TCFMain.py` orchestration；stage scripts 可被單獨呼叫，但其 CLI contract 需與 root flow 保持一致。
- 共用工具位於 repository root 的 `text_category_profiler/`，以 `text_category_profiler.<domain>.<module>` 匯入；舊 `utils` namespace 不再是 active code 的匯入邊界。四個 canonical stage 入口與 PyTorch Transformers classifier backend 以 `__file__` 推導並加入唯一的 repository root，保留直接執行命令相容性，不再透過 `PackageImporter.proc()` 搜尋機器特定或多層相對路徑；其他輔助／legacy stage 仍待分批遷移。
- `text_category_profiler` 的 domain packages 分別承載基礎工具（`core`）、資料/SQLite（`data`）、多程序（`concurrency`）、主流程（`pipeline`）、文字（`text`）、視覺化（`visualization`）與外部整合（`integrations`）；新程式不得再把已分流模組放回 package root。
- Dataset handoff 依賴目錄命名狀態（例如 `_is_running_DataConverter`、`_rdy_for_RunClassfier`）與檔名（例如 `train.tsv`、`test.tsv`、SQLite DB）。
- 禁止在未更新 contracts/workflows 前改名 stage handoff 檔案、目錄狀態 suffix 或主要 CLI option。
- 分類 taxonomy CSV 是本專案的 label/tree metadata；TACA 可作為相鄰的拓撲視覺化／編修工具，但主流程應優先透過明確 `--TopicTreeDir` 讀取本專案邊界內的 CSV，避免硬依賴 `../TACA`。

## 核心資料模型與狀態

| 名稱 | 意義 | 擁有者 | 儲存／生命週期 | 權威定義 |
| --- | --- | --- | --- | --- |
| argparse namespace | 跨 stage 傳遞的流程設定 | `text_category_profiler/pipeline/TCF_utils.py` | 每次命令執行產生 | `ClassfierOptionParser()` |
| WorkPool dataset dir | stage 間 handoff 的工作目錄 | `TCFMain.py` / DatasetConverter / RunClassfier | 會被 rename、搬移、備份或清理 | `datasetDirOutputDirPickers`, `TaskConnector`, stage scripts |
| TSV dataset | BERT classifier input | `DatasetConverter/` | 每次資料轉換產出 | `DataConverter.py`, BERT scripts |
| SQLite dataset/result DB | 樣本、固定測試與結果合併資料 | DatasetConverter / BertScript | 中間與交付產物 | SQL queries and filenames in scripts |
| Label/topic tree | 分類 label 與樹狀結構 | DatasetConverter / ClassesTree | input metadata and record files；新流程可用 `--TopicTreeDir` 將 taxonomy CSV 留在本專案邊界內，未指定時才走 legacy TACA 搜尋 | `TopicAnalysis_LabelList*.txt`, `TopicTree*` |

## 不變條件

- `TCFMain.py` 組出的 stage commands 必須使用同一套 CLI parser 可接受的參數。
- DataConverter 完成後至少需有 `train.tsv`、`dev.tsv` 或 `test.tsv` 之一；否則根流程會中止。
- 來源 DataFrame 應先依 `OutLabel`／`text` 去重，再切分為 train/dev/test；每個唯一來源樣本必須恰好分配一次，且不得跨 split 重複。訓練容量允許時，train split 應至少包含每個 label 一筆；少類樣本擴增只能在切分後作用於 train，不得改動 dev/test。
- 修改工作池搬移／清理邏輯前，必須先確認不會刪除或覆蓋真實任務資料。
- 任何外部服務寫入（SQL/ES）都不能被當成無副作用驗證。

## 錯誤、重試與回復邊界

- 失敗如何傳遞：多數 stage 以 `os.system()` 執行與例外／印出訊息處理；exit code handling 待確認。
- 重試責任：部分檔案 rename/move 有簡單重試；整體 pipeline retry policy 待確認。
- idempotency／去重：部分資料匯入與檔案 copy 有已存在跳過或 hash 去重線索；整體 pipeline idempotency 待確認。
- rollback／補償：工作池備份與搬移流程存在，但安全回復條件待確認。

## 安全與信任邊界

- 身分與權限：本機檔案系統與可能的 DB/ES access；具體權限待確認。
- 敏感資料：原始文本、工作池資料、模型、內部路徑、DB/ES credentials；不得寫入 Codex 文件或測試輸出。
- 外部輸入驗證：CLI args 與資料檔內容驗證待確認。
- 高風險操作：搬移／刪除工作池目錄、批次寫入 DB/ES、訓練／推論模型產物覆寫。

## 效能與營運邊界

- 主要規模假設：待確認；程式含多程序、GPU/CPU resource conformer 與大型資料線索。
- 可能的瓶頸：資料轉換 I/O、SQLite 查詢、模型推論／訓練、Dash 視覺化載入。
- 可觀測性：MPlogger 與 stage_time_cost log 線索；集中式 telemetry 未確認。
- 已知部署限制：未確認正式部署；BertScript 子目錄含 Dash/GCP 範例但不代表根專案 canonical deployment。

## 架構導覽

| 想修改的能力 | 優先查看 | 相關測試／契約 |
| --- | --- | --- |
| CLI args 或預設流程 | `text_category_profiler/pipeline/TCF_utils.py`, `TCF_Params/TCFParameters.py`, `TCFMain.py` | `CONTRACT-CLI-001` |
| 資料轉換 | `DatasetConverter/DataConverter.py`, `DatasetConverter/sampleHandler.py` | `CONTRACT-FILE-001` |
| 分類器執行 | `BertScript/RunClassfier.py`, `BertScript/run_classifier*.py` | `CONTRACT-FILE-001` |
| 結果合併／視覺化 | `BertScript/CombineTestResult.py`, `BertScript/Test_result_Vis.py` | `CONTRACT-FILE-002` |
| 共用工具 | `text_category_profiler/<domain>/` | `tests/test_package_layout.py` |
