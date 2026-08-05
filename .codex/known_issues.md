# Known Issues

> 類型：Verified open problems。只保存已證實、尚未解決，而且可能影響後續開發或使用的問題。

## Open Issues

| ID | 嚴重度 | 問題 | 影響範圍 | Workaround | 證據 | 狀態 |
| --- | --- | --- | --- | --- | --- | --- |
| `KI-001` | Medium | 根目錄沒有已確認的安裝、lint、test 或 smoke test 命令 | 驗證與 onboarding | 對文件變更使用 `git diff --check`；程式變更前先建立/確認 fixture 與依賴 | 根目錄 manifest/CI 盤點未找到 canonical command；`.codex/workflows.md` 保留待確認 | Open |
| `KI-002` | Medium | 主流程可能搬移、備份或刪除工作池資料，不適合未隔離執行 | Runtime 驗證、資料安全 | 只在隔離 fixture/workpool 中執行；未確認前做靜態 contract 檢查 | `TCFMain.py` 的 `BackupAndClean()` 與 workID 搬移流程 | Open |

## Issue Details

### `KI-001` — 缺少 canonical 自動化驗證命令

- 首次確認日期與環境：2026-08-05，branch `work` 初始化盤點。
- 最小重現方式或證據位置：根目錄未找到 package manifest、CI 或測試設定；`BertScript/requirements.txt` 僅列 TensorFlow。
- 預期與實際行為：預期有安全 smoke test；實際只能做文件／靜態一致性檢查。
- 影響、嚴重度與受影響範圍：Medium；影響所有程式變更的完成定義。
- 已知 workaround 及其不足：純文件執行 `git diff --check`；不能證明 runtime 行為。
- 修復條件：建立最小 fixture、依賴安裝方式與 smoke test command，並更新 `.codex/workflows.md`。
- 狀態：Open。

### `KI-002` — 主流程驗證有資料搬移／刪除風險

- 首次確認日期與環境：2026-08-05，branch `work` 初始化盤點。
- 最小重現方式或證據位置：`TCFMain.py` 會根據 WeiTech/workpool args 搬移任務目錄、備份輸出並可移除暫存資料。
- 預期與實際行為：預期 smoke test 無副作用；實際主流程與工作池 state 緊密耦合。
- 影響、嚴重度與受影響範圍：Medium；影響 `TCFMain.py`、DatasetConverter、RunClassfier 與備份清理流程驗證。
- 已知 workaround 及其不足：使用隔離 fixture/workpool；目前 fixture 待確認。
- 修復條件：定義可安全重建與清理的測試工作池。
- 狀態：Open。

## Recently Resolved

| ID | 解決摘要 | 驗證 | 日期 | 相關變更／決策 |
| --- | --- | --- | --- | --- |
| 目前無已確認項目 | — | — | — | — |

## 記錄準則

適合記錄：

- 可重現的產品 bug、資料限制或相容性缺陷。
- 持續影響驗證的環境／工具限制。
- 第三方服務已確認且會再次影響工作的限制。

不適合記錄：

- 單次網路抖動、打錯命令、尚未重現的猜測。
- 已立即修好且不影響未來工作的瑣碎問題。
- 沒有證據的風險清單；風險若形成設計取捨應放 `decisions.md`。
- 只屬於願望或改善方向的項目；已接受後放 `backlog.md`。
