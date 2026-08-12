# Interface Contracts

> 類型：Current state。記錄需要相容、可被其他模組或系統依賴的介面；不限於 HTTP API。

## 契約範圍

目前已確認需要維持相容的介面是 CLI arguments、stage handoff 檔案／目錄格式，以及部分外部匯入工具 CLI。未確認有根 HTTP API 或 OpenAPI contract。

## 契約索引

| ID | 類型 | 名稱 | Producer／Owner | Consumer | 權威定義 | 穩定性 |
| --- | --- | --- | --- | --- | --- | --- |
| `CONTRACT-CLI-001` | CLI | Text classification flow args | `text_category_profiler/pipeline/TCF_utils.py` | `TCFMain.py`, DatasetConverter, BertScript | `ClassfierOptionParser()` | Draft / currently used |
| `CONTRACT-FILE-001` | File handoff | Classifier dataset directory | `DatasetConverter/` | `BertScript/RunClassfier.py`, `TCFMain.py` | Stage scripts and filename checks | Draft / currently used |
| `CONTRACT-FILE-003` | File input | Topic tree taxonomy CSV files | `ClassesTree/` / project data owner | `DatasetConverter/DataConverter.py`, tree viewers | `--TopicTreeDir`, `--TopicTreeFiles`, `ClassesTree/ClassesTree_utils.py` | Draft / currently used |
| `CONTRACT-FILE-002` | File handoff | Prediction/result analysis artifacts | `BertScript/RunClassfier.py`, `CombineTestResult.py` | `Test_result_Vis.py`, work pool output | Stage scripts and backup filename patterns | Draft / currently used |
| `CONTRACT-CLI-002` | CLI / external service | Elasticsearch text ingestion tool | `text_category_profiler/ES_ingest_txt_to_es.py` | Operators / data import jobs | argparse in script | Optional / unverified in root flow |

## 通用相容性規則

- 新增 CLI option 通常可相容；刪除、改名、改 default 或改型別需同步所有 stage command assembly 與 README/workflows。
- Handoff 檔案新增通常可相容；刪除或改名 `train.tsv`、`dev.tsv`、`test.tsv`、`TopicAnalysis_LabelList.txt`、`dataset_total*` 或 result DB 需先查 consumer。
- 時間、timezone、encoding、locale 與 identifier 規則：待確認；現有程式多以 UTF-8 讀寫文字線索。
- 敏感欄位與遮蔽規則：不得在契約範例中放入真實帳密、內部連線字串、個資或敏感 payload。

## 契約詳細內容

### `CONTRACT-CLI-001` Text classification flow args

- 類型：CLI
- 狀態：Draft
- 權威定義：`text_category_profiler/pipeline/TCF_utils.py` 的 `ClassfierOptionParser(argv=None)`；未傳入 `argv` 時仍解析 process `sys.argv`。
- Producer／Owner：共用 text_category_profiler parser。
- Consumer：`TCFMain.py`、`DatasetConverter/DataConverter.py`、`BertScript/RunClassfier.py`、`BertScript/CombineTestResult.py`、`BertScript/Test_result_Vis.py` 等 stage scripts。
- 輸入：`--train/-tr`、`--test/-ts`、`--task`、`--WorkPoolROOT/-WPRoot`、`--BertDatasetSubDir/-BertDataDir`、`--TopicTreeDir/-TopicTreeDir`、`--TopicTreeFiles/-TopicTreeFiles`、`--modelDir/-mdlDir`、`--FixedTestPATH/-FTPath`、`--SaveOptimizer/-SaveOptimizer`、WeiTech work pool 相關參數、model type 與視覺化參數等。`--SaveOptimizer` 預設為 `false`，因此 Hugging Face checkpoint 不保留 `optimizer.pt`；需要續訓狀態時可傳 `--SaveOptimizer true`。
- 輸出：argparse namespace；`args.train == False and args.test == False` 時 parser 會將 `args.test` 設為 `True`。
- 驗證與約束：修改 parser 後需檢查所有 `convert_to_args_str(args)` consumer 與手動附加參數。
- 錯誤／exit code／失敗語意：argparse 會處理未知／不合法參數；stage script 其他錯誤語意待確認。
- 版本與相容性：無版本化機制；破壞性變更需文件同步與 migration note。
- 安全與敏感資訊：路徑參數可能包含內部資料位置；不要在文件放真實敏感路徑或內容。
- 契約測試：待確認；目前沒有 canonical CLI smoke test。

### `CONTRACT-FILE-001` Classifier dataset directory

- 類型：File / directory handoff
- 狀態：Draft
- 權威定義：`DatasetConverter/DataConverter.py`、`BertScript/RunClassfier.py`、`TCFMain.py` 對檔名與目錄狀態的讀寫。
- Producer／Owner：DatasetConverter stage。
- Consumer：RunClassfier stage 與 root flow。
- 輸入：原始文字資料、固定測試資料、工作池任務與 label/topic metadata。
- 輸出：至少一個 BERT dataset split（`train.tsv`、`dev.tsv`、`test.tsv`）與 `OnlyForRecord/`、`datasetDB/` 中間資料線索。
- 驗證與約束：一般來源樣本在計算 split 比例前依 `OutLabel`／`text` 去重，避免相同分類樣本同時進入 train/dev/test；`DataAugmentationGoal` 在切分完成後只補足 train 中的少類 label，不得產生 dev/test 樣本；`TCFMain.py` 會檢查 dataset files 是否存在；RunClassfier 會查詢 `test.sql3`、`dataset_total_with_filename_FixedTest.sql3`、`dataset_total_with_filename_ES.sql3`。
- 錯誤／失敗語意：若找不到 dataset 或必要檔案，stage 可能 raise exception；完整 exit code 待確認。
- 版本與相容性：無 schema/version marker；改名需同步所有 consumer。
- 安全與敏感資訊：dataset 可能包含真實文本或個資；不可在測試輸出或 Codex 文件中貼全文。
- 契約測試：待建立 fixture。

### `CONTRACT-FILE-002` Prediction/result analysis artifacts

- 類型：File / directory handoff
- 狀態：Draft
- 權威定義：`BertScript/RunClassfier.py`、`BertScript/CombineTestResult.py`、`BertScript/Test_result_Vis.py`、`TCF_Params/TCFParameters.py` 的 output filename patterns。
- Producer／Owner：RunClassfier 與 CombineTestResult stages。
- Consumer：Test_result_Vis、BackupAndClean 與外部工作池 consumer。
- 輸入：模型預測結果、label list、dataset DB。
- 輸出：`DFPreambleCols_df_ALL*`、`dataset_total_with_filename_FixedTest.sql3`、`test.sql3`、`test.tsv`，SDSMS 任務另包含 `SDSMS.*` patterns。
- 驗證與約束：`FinalOfferedOutputFNrePatList` 決定交付／備份檔名；修改需同步外部工作池 consumer。
- 錯誤／失敗語意：備份／搬移失敗目前多為 print/log；完整 rollback 待確認。
- 版本與相容性：無明確版本；破壞性檔名變更需 migration plan。
- 安全與敏感資訊：輸出可能包含原文、預測、分數與內部任務 ID；不得提交真實輸出。
- 契約測試：待建立 fixture。

### `CONTRACT-CLI-002` Elasticsearch text ingestion tool

- 類型：CLI / external service
- 狀態：Draft / optional
- 權威定義：`text_category_profiler/ES_ingest_txt_to_es.py` argparse。
- Producer／Owner：ES ingestion utility。
- Consumer：手動或批次資料匯入操作者。
- 輸入：`--index/-i`、`--dir/-d`、`--host`、`--batch`、`--lang`、`--user`、`--op`、`--dedup-by-content`。
- 輸出：Elasticsearch bulk write side effects。
- 驗證與約束：不得在未隔離 ES instance 前當 smoke test 執行。
- 錯誤／失敗語意：待確認。
- 版本與相容性：待確認。
- 安全與敏感資訊：不要記錄真實 ES host、credentials 或 documents。
- 契約測試：待確認。

### `CONTRACT-FILE-003` Topic tree taxonomy CSV files

- 類型：File input / taxonomy metadata
- 狀態：Draft
- 權威定義：`text_category_profiler/pipeline/TCF_utils.py` 的 `--TopicTreeDir`、`--TopicTreeFiles`，以及 `ClassesTree/ClassesTree_utils.py` 的 `SetTreeFiles()`／`LoadTree()`。
- Producer／Owner：分類專案的 taxonomy/data owner；TACA 可作為外部編修或視覺化工具，不應是唯一隱含位置。
- Consumer：`DatasetConverter/DataConverter.py` 載入 labels 與 info score；`ClassesTree` viewer／analysis 工具載入 topic tree。
- 輸入：預設檔名為 `TopicTree.csv,TopicTree_AK4.csv`；每列至少需有母節點、子節點、加入日期等三欄，程式使用前兩欄作為 edge。
- 邊界規則：主流程應優先傳入 `--TopicTreeDir <dir>`，讓 taxonomy CSV 位於本 repo 或明確資料掛載區；未傳入時仍保留 legacy `./TACA/...`、Windows Documents TACA、`../TACA/...` 搜尋以相容舊環境。
- 輸出／備份：DatasetConverter 會將使用到的 tree CSV 複製到 dataset 的 `OnlyForRecord/`，作為當次分類結果可追溯紀錄。
- 錯誤／失敗語意：指定 `--TopicTreeDir` 但找不到檔案時必須直接失敗並列出檢查路徑，不應靜默跳回 `../TACA`。
- 版本與相容性：目前無 schema version；新增或移除 tree CSV 檔名需透過 `--TopicTreeFiles` 顯式傳遞並同步相關 viewer。
- 安全與敏感資訊：taxonomy label 通常非憑證，但仍可能透露內部分類策略；提交或輸出前需確認可分享範圍。
- 契約測試：可用最小 CSV fixture 測 `LoadTree(..., TreeSourceDir=...)`；完整流程 fixture 待建立。

## Deprecated／Migration

| 舊契約 | 替代契約 | 過渡方式 | 移除條件／日期 |
| --- | --- | --- | --- |
| 目前沒有已確認項目 | — | — | — |
