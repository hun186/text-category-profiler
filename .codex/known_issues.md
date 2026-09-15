# Known Issues

> 類型：Verified open problems。只保存已證實、尚未解決，而且可能影響後續開發或使用的問題。

## Open Issues

| ID | 嚴重度 | 問題 | 影響範圍 | Workaround | 證據 | 狀態 |
| --- | --- | --- | --- | --- | --- | --- |
| `KI-002` | Medium | 主流程可能搬移、備份或刪除工作池資料，不適合未隔離執行 | Runtime 驗證、資料安全 | 只在隔離 fixture/workpool 中執行；未確認前做靜態 contract 檢查 | `TCFMain.py` 的 `BackupAndClean()` 與 workID 搬移流程 | Open |
| `KI-003` | Medium | 尚無完整模型／GPU／真實 WorkPool pipeline smoke test | 完整 runtime 驗證 | 使用 `python -m unittest discover -s tests` 執行 dependency-light suite；資料轉換另跑隔離 fixture | `.codex/workflows.md` 驗證矩陣；Phase 0 characterization tests | Open |

## Issue Details

### `KI-002` — 主流程驗證有資料搬移／刪除風險

- 首次確認日期與環境：2026-08-05，branch `work` 初始化盤點。
- 最小重現方式或證據位置：`TCFMain.py` 會根據 WeiTech/workpool args 搬移任務目錄、備份輸出並可移除暫存資料。
- 預期與實際行為：預期 smoke test 無副作用；實際主流程與工作池 state 緊密耦合。
- 影響、嚴重度與受影響範圍：Medium；影響 `TCFMain.py`、DatasetConverter、RunClassfier 與備份清理流程驗證。
- 已知 workaround 及其不足：使用隔離 fixture/workpool；目前 fixture 待確認。
- 修復條件：定義可安全重建與清理的測試工作池。
- 狀態：Open。

### `KI-003` — 缺少完整 pipeline smoke test

- 首次確認日期與環境：2026-09-15，Phase 0 current-state reconciliation。
- 最小重現方式或證據位置：`.codex/workflows.md` 已確認 dependency-light unittest 與 DatasetConverter fixture，但完整流程仍需要本機資料、模型、GPU 或 WorkPool。
- 預期與實際行為：輕量測試可用 `python -m unittest discover -s tests` 重複執行；完整 pipeline 尚無安全、無副作用的 canonical smoke test。
- 影響、嚴重度與受影響範圍：Medium；無法由輕量 suite 證明模型推論與真實工作池整合。
- 已知 workaround 及其不足：執行輕量 suite 與隔離的 DatasetConverter fixture；不涵蓋完整模型／GPU runtime。
- 修復條件：建立具隔離資料、模型與 WorkPool lifecycle 的可重現完整 smoke test。
- 狀態：Open。

## Recently Resolved

| ID | 解決摘要 | 驗證 | 日期 | 相關變更／決策 |
| --- | --- | --- | --- | --- |
| `KI-001` | 已確認根目錄有 dependency-light smoke command | `python -m unittest discover -s tests` | 2026-09-15 | `.codex/workflows.md`、`tests/test_project_docs.py` |

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
