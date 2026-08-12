# Development Workflows

> 類型：Current state。保存可重現的安裝、執行與驗證方式。Codex 不得執行尚未查證的占位命令。

## 環境前提

| 項目 | 要求 | 查證來源 |
| --- | --- | --- |
| 作業系統 | 待確認；程式含 Windows 與 Linux 分支 | `TCFMain.py`, `TCF_Params/TCFParameters.py` |
| Runtime 版本 | Python 版本待確認；BertScript 要求 TensorFlow >= 1.11.0 | `BertScript/requirements.txt` |
| 套件管理器 | `pip` 可讀取根目錄 `requirements.txt`；尚無 lockfile | `requirements.txt`, `rg --files` 盤點 |
| 必要本機服務 | 主要流程需要本機資料／模型／工作池；Elasticsearch 只在部分工具中出現 | `TCFMain.py`, `text_category_profiler/ES_ingest_txt_to_es.py` |
| 必要環境變數 | 目前無根流程已確認必要環境變數；路徑多由 CLI args 傳入 | `text_category_profiler/TCF_utils.py` |

## Canonical Commands

| 用途 | 命令 | 工作目錄 | 狀態／最後查證 |
| --- | --- | --- | --- |
| 安裝／同步依賴 | `python -m pip install -r requirements.txt` | repository root | Command documented；未在容器執行，因會下載/安裝大量 ML dependencies |
| 啟動主流程 | `python TCFMain.py --WeiTechworkIDPath <path> --WeiTechWorkPoolPATH <path> -p 8099999 -TRVHost False -task SDSMS_Prediction` | repository root | Command shape verified from `TCFMain.py` comments；會讀寫資料，初始化未執行 |
| 單獨資料轉換 | `python DatasetConverter/DataConverter.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| 單獨分類 | `python BertScript/RunClassfier.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| 單獨結果合併 | `python BertScript/CombineTestResult.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| 單獨視覺化分析 | `python BertScript/Test_result_Vis.py ...` | repository root | Verified as stage command assembled by `TCFMain.py`；未 smoke test |
| Format | 待確認，禁止執行 | repository root | Unverified |
| Lint | 待確認，禁止執行 | repository root | Unverified |
| Type check | 待確認，禁止執行 | repository root | Unverified |
| 最小 smoke test | `python -m unittest discover -s tests` | repository root | Verified for lightweight tests that do not require model/data/GPU |
| 完整 test suite | 待確認，禁止執行 | repository root | Unverified：未找到 CI 或 canonical test command |

## 驗證矩陣

| 變更類型 | 最小必要檢查 | 需要擴大驗證的條件 |
| --- | --- | --- |
| 純文件 | `python -m unittest discover -s tests`；`git diff --check`；交叉閱讀 README、AGENTS Quickstart 與 `.codex/*.md` 一致性 | 文件新增可執行命令或改變資料邊界 |
| CLI parser／參數 | 檢查 `text_category_profiler/TCF_utils.py` 與 `TCFMain.py` stage command 組裝一致 | 參數影響工作池、模型、輸出路徑或外部服務 |
| 資料轉換 | `python -m unittest tests.test_dataconverter_fixture_integration`；使用 repository 小型 fixture、process workers 與 temporary output，不接觸真實工作池 | 變更 pandas／SQLite output adapter、完整 CLI bootstrap、fixed-test／ES 或 handoff 時仍需擴大驗證 |
| 分類器 | 需要已確認模型／fixture 後執行 RunClassfier smoke test；目前待確認 | 影響模型格式、GPU/CPU resource gate 或 output contract |
| 視覺化 | 靜態檢查＋若可執行再做 browser/screenshot；目前待確認 | layout、Dash callback 或部署設定改變 |
| 匯入外部服務 | 先以 dry-run 或 mock 明確標示；不得把真實 DB/ES 寫入當 smoke test | 會連線 SQL Server、Elasticsearch 或批次寫入資料 |

## 測試資料與外部服務

- 最小 fixture：`tests/fixtures/dataconverter_small/`；目前涵蓋兩個 labels、三個純文字來源、worker read、split bounds 與 temporary TSV artifacts。
- 測試是否允許網路：待確認；預設不讓測試依賴網路成功。
- 外部服務替代方式：待確認；mock 必須明確揭露，不得冒充正式成功。
- 測試產物位置與清理方式：待確認；`WorkPool*`、`logs`、模型與 output 目錄需先視為可能有狀態。

## 常見失敗與替代驗證

| 限制 | 首選驗證 | 安全替代 | 不足之處 |
| --- | --- | --- | --- |
| 缺少 pandas／模型等完整 runtime 依賴 | `python -m unittest tests.test_dataconverter_fixture_integration` | `python -m unittest discover -s tests` | 可證明隔離的 source → worker → split → TSV 契約，但不能證明完整 legacy CLI、pandas／SQLite 或工作池 handoff |
| 流程命令可能搬移／刪除工作池資料 | 在隔離 fixture 中執行 | 僅檢查 command assembly 與 contract 文件 | 不能覆蓋 I/O side effects |

## 完成前檢查

- 使用的是此 repo 已確認的 runtime 與 package manager；若未確認，不猜測安裝命令。
- 先跑最相關檢查，再依風險擴大；不為小改動無條件重裝全部依賴。
- 不把資料庫、雲端、寄信、發布、刪除或 migration 當成無副作用測試。
- 所有未執行或失敗的檢查都在最終回報中明確區分。
