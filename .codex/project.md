# Project Profile

> 類型：Current state。只描述目前有效的專案身份與範圍，不保存工作流水帳。

## Metadata

- 初始化狀態：`INITIALIZED`
- 最後查證日期：`2026-08-05`
- 查證基準：branch `work` at `f1f394d` plus current initialization diff
- 維護責任：待確認

## 一句話目的

以 Python 腳本將文字來源轉為分類器資料集，執行 BERT／XLM 文字分類訓練或推論，並合併與視覺化分類結果。

## 使用者與使用情境

- 主要使用者：需要整理文字資料、執行主題分類與檢視分類結果的資料／NLP 工作者；具體團隊待確認。
- 主要使用情境：批次工作池分類、固定測試資料推論、訓練資料轉換、AI 輔助的 taxonomy／訓練集覆蓋調優、分類結果合併與 Dash/Plotly 視覺化分析。
- 主要輸入：文字資料、工作池任務目錄、固定測試資料、模型目錄與分類參數。
- 主要輸出：BERT dataset 檔案、SQLite 中間資料庫、預測結果、合併分析資料與視覺化輸出。

## 目標

- 提供 `TCFMain.py` 串接的資料轉換 → 分類器執行 → 結果分析流程。
- 保留可單獨使用的資料轉換、分類、類別樹與共用工具腳本。
- 讓 Codex 後續任務能依 current-state 文件選擇正確範圍與驗證方式。

## 非目標

- 目前未證實是 FastAPI／Elasticsearch RAG agent 專案；根 README 先前內容已判定與目前程式碼不一致。
- 目前未確認有可公開部署的 web service、package 發布流程或完整 CI。

## 技術與執行環境

| 面向 | 目前狀態 | 證據位置 |
| --- | --- | --- |
| 主要語言 | Python | `TCFMain.py`, `DatasetConverter/*.py`, `BertScript/*.py` |
| Framework / runtime | Python 腳本；BERTScript requirements 宣告 TensorFlow >= 1.11.0；視覺化腳本使用 Dash/Plotly 線索 | `BertScript/requirements.txt`, `BertScript/Test_result_Vis.py` |
| 套件與 lockfile | 根目錄 `requirements.txt` 列出目前盤點的共用 runtime/test 需求；子目錄 `BertScript/requirements.txt` 保留 TensorFlow 線索；尚無 lockfile | `requirements.txt`, `BertScript/requirements.txt` |
| 儲存與外部服務 | SQLite 中間資料、工作池檔案系統；部分 Elasticsearch 匯入／設定腳本存在但非根流程必然需求 | `BertScript/RunClassfier.py`, `DatasetConverter/elasticsearch/`, `text_category_profiler/ES_ingest_txt_to_es.py` |
| 支援平台 | 待確認；程式含 Windows 與 Linux 路徑／平台分支 | `TCFMain.py`, `TCF_Params/TCFParameters.py` |

## Repository 地圖

| 路徑 | 責任 | 何時優先查看 |
| --- | --- | --- |
| `TCFMain.py` | 根流程 orchestrator | 修改整體流程、入口參數傳遞、階段順序 |
| `TCF_Params/` | 預設參數、工作池根目錄、流程常數 | 修改 CLI 預設、任務模式、工作池／模型路徑 |
| `DatasetConverter/` | 資料集轉換與樣本處理 | 修改輸入資料轉 TSV／SQLite／分類資料集流程 |
| `BertScript/` | BERT／XLM 分類、結果合併、視覺化 | 修改模型訓練／推論、分類結果合併或 Dash 視覺化 |
| `ClassesTree/` | 類別樹與標籤工具 | 修改 taxonomy、label tree、圖形視覺化 |
| `TextClassificationDatasetOptimization/` | AI 代理人提示模板、taxonomy 擴充、來源索引、訓練集 PoC 與正文抓取工具 | 盤點類別缺口、連結當前議題、建立／驗證訓練文本 |
| `text_category_profiler/` | 依 `core`、`data`、`concurrency`、`pipeline`、`text`、`visualization`、`integrations` 分流的共用 utilities | 修改跨模組共用行為、檔案系統、SQLite、多程序或外部整合工具 |
| `tests/` | 不依賴模型/資料的輕量功能測試 | 修改 console helper、README/requirements 契約或可無副作用測試的 utility |
| `.codex/` | Codex current-state 記憶與路由 | 任務前後同步專案事實、流程、架構與契約 |

## 主要入口

| 入口類型 | 路徑／命令 | 用途 | 狀態 |
| --- | --- | --- | --- |
| CLI script | `python TCFMain.py ...` | 串接資料轉換、分類器、結果分析 | 已由程式與註解確認存在；實際執行需資料／模型，未 smoke test |
| Stage script | `python DatasetConverter/DataConverter.py ...` | 將資料轉為分類器資料集 | 已由 `TCFMain.py` 呼叫；未獨立驗證 |
| Stage script | `python BertScript/RunClassfier.py ...` | 執行分類器訓練或推論 | 已由 `TCFMain.py` 呼叫；未獨立驗證 |
| Stage script | `python BertScript/CombineTestResult.py ...` | 合併分類結果 | 已由 `TCFMain.py` 呼叫；未獨立驗證 |
| Stage script | `python BertScript/Test_result_Vis.py ...` | 分析／視覺化分類結果 | 已由 `TCFMain.py` 呼叫；未獨立驗證 |

## 事實來源

1. 可執行 Python 入口與 import/call graph：`TCFMain.py`, `DatasetConverter/DataConverter.py`, `BertScript/RunClassfier.py`。
2. CLI parser：`text_category_profiler/pipeline/TCF_utils.py` 的 `ClassfierOptionParser()`。
3. 流程常數與預設路徑：`TCF_Params/TCFParameters.py`。
4. 子目錄 manifest：`BertScript/requirements.txt`。
5. 根 README 只作 current user-facing summary；若與程式碼衝突，以程式碼與設定為準。

## 資料、模型與產物邊界

- 應提交 Git：程式碼、非敏感範例設定、最小且已審核的 sample／fixture、Codex current-state 文件。
- 不應提交 Git：真實工作池資料、模型 checkpoint、大型 datasets、logs、outputs、秘密、憑證、真實內部連線設定與個資。
- 可供測試的最小 fixture：待確認；repository 內有 sample 檔案但未驗證可支援完整 smoke test。
- 大型／敏感資料位置：`WorkPool*`、模型目錄、`rawData`、`logs`、`outputs` 與本機／網路掛載路徑應先視為不可提交或不可無副作用修改。

## 外部系統與相鄰專案

| 系統／專案 | 本專案依賴方式 | 交接契約 | 可用性／限制 |
| --- | --- | --- | --- |
| TensorFlow BERT runtime | `BertScript` requirements 與分類腳本 | 模型 checkpoint、vocab、TSV dataset | 版本與安裝流程待確認 |
| Elasticsearch | 匯入工具／設定樣本線索 | index、bulk ingestion 參數 | 非根流程必然需求；服務可用性待確認 |
| 工作池檔案系統 | `TCFMain.py` 與參數使用任務目錄 | workID directory、dataset/output files | 真實路徑與資料規則待確認 |

## 重要限制與不變條件

- 不要將根目錄誤判為 FastAPI RAG agent；目前未找到對應程式入口。
- 未確認資料／模型／工作池前，不執行會讀寫大量資料或搬移目錄的流程命令。
- 變更 CLI parser、stage handoff 檔名或工作目錄命名時，需同步 `TCFMain.py`、`TCF_Params/`、相關 stage script 與 `.codex/contracts.md`。

## 待確認事項

- [ ] 實際支援的 Python 版本與完整依賴版本鎖定方式。
- [ ] 可安全執行的最小 smoke test／fixture。
- [ ] 哪些 sample/data 應留在 Git，哪些應移出或加入 ignore。
- [ ] `BertScript/` 中第三方 BERT/Dash 範例內容與本專案維護邊界。
- [ ] 是否仍需要 README 中原本描述的 SRA／RAG 專案資訊，或該內容屬於錯置文件。
