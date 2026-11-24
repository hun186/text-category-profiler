# BL-001｜新功能前的結構驗證 Gate（不等於正式驗收）

## 用途與目前結構狀態

本報告為 **Git 追蹤檔案與 Python AST 的可重現靜態證據**，
目標是在進行新功能開發前驗證核心架構並防止向 legacy 入口倒退。

現行 `text_category_profiler/` 由兩份已有 CI 驗證的 manifest
完整分類：77 個 tracked 檔案＝64 個 canonical/domain-owned
＋13 個原位保留的 legacy 相容入口、vendor 資產與 package marker
＋0 個未知。這不能推論 64 個檔案都經實機驗證或是跨 stage
真正共用的程式，也不能證明 8 個 legacy shim 已經沒有外部使用者。

## 唯讀／無實機執行方法

從更新後的 repository root 執行：

```bash
python -m unittest -v tests.test_bl001_structural_readiness tests.test_bl001_package_census tests.test_package_layout
python -m scripts.bl001_structural_readiness --output bl001-readiness.json
```

程式只對 Git 追蹤的 repo 路徑、原始碼 AST、現有 manifest
進行檢查；不會 import Stage 1～4 的 GUI、模型或服務，
不讀正式 WorkPool／SQLite、不載入模型或 GPU。
CI 的 Windows/Ubuntu jobs 會輸出 machine-readable JSON artifact。
因需讀取 Git tracked manifest，應在 Git clone/工作樹執行。

狀態說明：

- `PASS_STRUCTURAL_BOUNDARIES_EXTERNAL_GATES_PENDING`：目前檢查到的
  入口、各 StagePlan、共用 WorkPool/Process 邊界、Stage 4 filter
  分流、模組實作歸屬和 manifest 均相容，**不等於 BL-001 Done**。
- `BLOCKED_STRUCTURAL_BOUNDARIES`：缺少預期入口或 module owner、
  不可解析的 Python 程式、出現未分類／被改寫的 legacy artifact、
  Stage 4 filter 重新塞回大入口或 root timing default 退步等；
  程式以非 0 exit 拒絕。
- 結果中 `deployment_authorized`、
  `production_workpool_verified`、`real_gui_verified`、
  `model_gpu_verified`、`external_callers_verified` 與
  `bl001_formally_done` 固定為 false；全部外部項目
  `UNVERIFIED`，不能靠重跑此工具改成 true。

## 新功能如何選擇結構歸屬

| 新需求 | 應修改的主要模組 | 不應採取的做法 |
| --- | --- | --- |
| 跨 Stage 命令或排程條件 | `pipeline/commands.py`、`pipeline/orchestrator.py` 和受注入的 root ports | 在 `TCFMain.py` 繼續塞無法隔離測試的業務實作 |
| 啟動參數、root 資源或 WeiTech 輸入 | `pipeline/configuration.py`；跨階段資料移交用 `pipeline/workpool.py` + `filesystem/` | 在 Stage script 直接改 WorkPool 目錄或使用可覆寫 rename |
| 原始文本、清校、資料集切割 | `DatasetConverter/core/`、`sources/`、`adapters/`；以 StagePlan/StageContext 注入 | 反向讓 `DatasetConverter` 匯入 GUI 或引入 import-time 資料寫入 |
| 分類與模型執行方式 | `BertScript/classifier_stage.py` 的無重依賴 boundary + 明確模型 adapter | 把 Stage 2 model runtime 隱式 import 進共用 package |
| Stage 4 篩選、查詢與表格資料套用 | `BertScript/visualization_filter.py`；callback wiring 留在 `Test_result_Vis.py` | 將純篩選演算法再複製回 4,000 行的 GUI 入口 |
| Stage 4 執行狀態與檔案交接 | `BertScript/visualization_stage.py` | 將 callback 渲染、OS rename 和業務結果合併成單一函式 |
| CSV taxonomy、AI 改版建議 | 以 ClassTable/TopicTree 的受審來源及 BL-002 候選流為準 | 未經人工 Review 直接覆寫權威 ClassLabel、TopicTree |
| SQLite stage-local 輸出 | `text_category_profiler/data/stage_sql.py` 及既有兩份 stage adapter | 自行新建第 4 套 `sampleSrc`、索引或隱式 replace 策略 |

## 尚未完成，不能逕行宣布結案的 Gate

1. **Legacy 外部／動態 callers**：13 個保留資產（其中 8 個相容入口）的
   原位保全與 in-repo AST import 靜態清單完成，不能證明 repo 外
   手動 script、動態 import、第三方工具或舊 deployment snapshot 不使用它們。
   因此先不刪，也不允許新功能依賴 legacy 路徑。
2. **KI-008 Stage 4 真正 GUI 互動**：需 Windows Anaconda/Dash 實機
   0 筆／非 0 筆篩選、排序、翻頁與閒置觀察，確認不會 callback 循環、
   重複寫 SQLite/XLS。
3. **KI-012 SQLite 正式環境與復原**：原子寫入修復在私有 Windows SQLite
   已有通過證據，但正式 WorkPool 大資料、網路磁碟、並行與候選表
   清理策略仍需獨立核准；不拿正式 DB 做中斷注入。
4. **KI-003 模型/GPU 全流程**：Hosted lightweight discovery 和
   PyTorch smoke 不等於所有模型、H100/CUDA 或內網 E2E。
5. **跨 Stage 完整重試／復原**：備份、SQLite commit 與 WorkPool
   最後 move 非單一原子交易，不得因結構靜態 PASS 就自動清理、
   續跑或交付中斷的資料夾。
6. **Jaal independent repo／上游權威同步**：見 Issue #208，
   新 viewer 工作避免同時維護兩份相互分歧的實作。

以上 Gate 與現有 `.codex/backlog.md` 的 BL-001
`In Progress` 一致。這一批只完成**程式化的靜態結構
驗證與可重用模組邊界**，並未取得使用者尚未提供的實機資料。
