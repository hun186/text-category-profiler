# text-category-profiler

`text-category-profiler` 是一個以 Python 腳本組成的文字分類、資料集轉換與分類結果分析工具集。Repository 目前呈現為開發／研究型工作區：根入口 `TCFMain.py` 會串接資料轉換、BERT／XLM 分類器執行，以及分類結果合併與視覺化分析；多數命令需要本機資料、模型與工作目錄設定後才能安全執行。

## 目前狀態

- 階段：待確認；目前程式與樣本顯示為內部資料處理與模型實驗工作區。
- 已具備：資料集轉換、BERTScript 分類流程、分類結果合併、Dash/Plotly 視覺化相關腳本、Class tree 工具與共用 Python utilities。
- 主要限制：根目錄沒有已確認的 package manifest、lockfile 或 CI；模型、資料集、工作池與部分外部路徑需由使用者提供。

## 快速開始

### 前置需求

- Python runtime：版本待確認；程式使用 Python 腳本與 `argparse`，並在 `BertScript/requirements.txt` 宣告 TensorFlow `>= 1.11.0`。
- 依賴安裝：待確認；根目錄沒有已確認的 requirements／lockfile。
- 本機資料與模型：多數流程依賴 `WorkPool`、資料集目錄、模型目錄或固定測試資料路徑。

### 執行

根入口由 `TCFMain.py` 提供，範例註解顯示可用於 WeiTech／SDSMS 工作池流程；實際參數需依本機資料與模型調整：

```bash
python TCFMain.py --WeiTechworkIDPath <path-to-work-id-root> --WeiTechWorkPoolPATH <path-to-work-pool> -p 8099999 -TRVHost False -task SDSMS_Prediction
```

> 注意：以上命令會讀寫工作池與輸出資料，初始化時未執行。請先確認資料、模型與輸出路徑。

### 驗證

目前沒有已確認的自動化測試命令。對純文件變更，最小檢查為確認 Markdown 與專案記憶文件一致；對程式變更，需先查證相關腳本能否在目前資料與依賴環境中安全執行。

## Repository 結構

| 路徑 | 用途 |
| --- | --- |
| `TCFMain.py` | 根流程入口；串接 DataConverter、RunClassfier、CombineTestResult 與 Test_result_Vis。 |
| `TCF_Params/` | 分類流程參數、工作池根目錄、BERTScript 路徑與任務預設值。 |
| `DatasetConverter/` | 將原始文本／資料來源轉換為分類器使用的資料集、SQLite 與記錄檔。 |
| `BertScript/` | BERT／XLM 分類、訓練／推論、結果合併與 Dash/Plotly 視覺化腳本；包含部分第三方 BERT/Dash 範例內容。 |
| `ClassesTree/` | 類別樹、標籤工具與視覺化實驗。 |
| `PythonModule/utils/` | 共用工具函式，透過 `PackageImport.py` 加入 `sys.path` 後供其他模組匯入。 |
| `TCF_Params/` | 流程預設參數與入口設定。 |
| `.codex/` | Codex 專案記憶、工作流、架構、契約與初始化狀態文件。 |

## 輸入、輸出與資料邊界

- 主要輸入：文字資料集、固定測試資料、工作池任務目錄與已訓練模型目錄。
- 主要輸出：分類器資料集、SQLite 中間資料庫、預測結果、合併後分析資料與視覺化輸出。
- 不應提交 Git：真實工作池資料、模型 checkpoint、大型資料集、logs、outputs、秘密、憑證與內部連線設定。
- 最小測試資料：待確認；repository 內含若干 sample 檔案，但尚未確認可作為完整 smoke fixture。

## 文件

- Codex 專案概況：`.codex/project.md`
- 開發與驗證流程：`.codex/workflows.md`
- 架構導覽：`.codex/architecture.md`
- 介面契約：`.codex/contracts.md`
- 已知問題與待確認事項：`.codex/known_issues.md`

## 已知限制

- 根 README 先前描述 FastAPI／Elasticsearch RAG 代理人，但目前根目錄盤點未找到對應 `api/`、`agent/`、FastAPI manifest 或 RAG runtime；本 README 已改為反映目前可由程式碼查證的文字分類工作區。
- 根目錄沒有已確認的安裝、lint、type check、build 或 test 命令。
- 多數 runnable 腳本可能讀寫本機資料、工作池或模型產物；未確認資料邊界前不要當作無副作用測試執行。
