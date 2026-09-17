# Known Issues

> 類型：Verified open problems。只保存已證實、尚未解決，而且可能影響後續開發或使用的問題。

## Open Issues

| ID | 嚴重度 | 問題 | 影響範圍 | Workaround | 證據 | 狀態 |
| --- | --- | --- | --- | --- | --- | --- |
| `KI-002` | Medium | 主流程可能搬移、備份或刪除工作池資料，不適合未隔離執行 | Runtime 驗證、資料安全 | 使用 recording filesystem／temporary fixture 與 isolated smoke WorkPool；smoke profiles 不涵蓋 WeiTech queue acquisition／processed delivery | `tests/test_workpool_manager.py`、`tests/test_tcf_workpool_characterization.py`、full-pipeline smoke scope | Open |
| `KI-003` | Medium | 已有隔離 root smoke，但尚缺 post-merge real-model/GPU acceptance evidence | 完整 runtime 驗證 | Layer A 啟用時必須 PASS；Layer B 留待明確 real-runtime inputs 與 H100/CUDA acceptance | `tests/test_full_pipeline_smoke.py`、`tests/test_full_pipeline_real_runtime.py`、`.codex/workflows.md` | Open |

## Issue Details

### `KI-002` — 主流程驗證有資料搬移／刪除風險

- 首次確認日期與環境：2026-08-05，branch `work` 初始化盤點。
- 最小重現方式或證據位置：`TCFMain.py` 會根據 WeiTech/workpool args 搬移任務目錄、備份輸出並可移除暫存資料。
- 預期與實際行為：預期 smoke test 無副作用；實際主流程與工作池 state 緊密耦合。
- 影響、嚴重度與受影響範圍：Medium；影響 `TCFMain.py`、DatasetConverter、RunClassfier 與備份清理流程驗證。
- 已知 workaround 及其不足：以 recording filesystem、temporary fixture 與 isolated smoke WorkPool 執行；full-pipeline smoke profiles 不會 exercise WeiTech queue acquisition 或 processed delivery，因此不能關閉本 issue。
- 修復條件：建立 Plan v1.1 要求的可安全重建、清理且涵蓋完整 root integration 的測試工作池。
- 狀態：Open。

### `KI-003` — 缺少完整 pipeline smoke test

- 首次確認日期與環境：2026-09-15，Phase 0 current-state reconciliation。
- 最小重現方式或證據位置：Layer A (`TCP_RUN_FULL_PIPELINE_SMOKE=1`) 已建立並在啟用時必須 PASS；Layer B (`TCP_RUN_REAL_PIPELINE_SMOKE=1`) 已建立但尚需 post-merge real model/GPU acceptance evidence。
- 預期與實際行為：一般 `python -m unittest discover -s tests` 會明確 SKIP opt-in profiles；Layer A 提供 temporary WorkPool 的 real-root coverage，但不能代表 production model/GPU PASS。
- 影響、嚴重度與受影響範圍：Medium；在真實 classifier 與目標 GPU 的 acceptance evidence 尚未審查前，完整 runtime 仍未獲證明。
- 已知 workaround 及其不足：依 `.codex/workflows.md` 執行 Layer A；它刻意替代 inference child，所以不涵蓋 real model/GPU runtime。
- 修復條件：經 review/merge 的 Layer A PASS，加上 Layer B PASS、temporary WorkPool isolation、final `*_rdy_for_Spike` handoff，以及預定 H100 acceptance 的 CUDA available/selected evidence。
- 狀態：Open。

## Recently Resolved

| ID | 解決摘要 | 驗證 | 日期 | 相關變更／決策 |
| --- | --- | --- | --- | --- |
| `KI-001` | 已確認根目錄有 dependency-light smoke command | `python -m unittest discover -s tests` | 2026-09-15 | `.codex/workflows.md`、`tests/test_project_docs.py` |
| `KI-004` | 修正 Python mapping 語法與部署範例 placeholder；將 CSS 與資料片段以真實副檔名重新分類，而非偽裝成 Python；移除 legacy FTP 範例的連線資料與 import-time 行為，改為明確拒絕網路操作的 inert compatibility stubs，未建立新網路功能 | `python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler` exits 0；`python -m unittest tests.test_repository_compile_gate` | 2026-09-17 | `tests/test_repository_compile_gate.py` 與 KI-004 blocker corrections |

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
