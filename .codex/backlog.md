# Backlog

> 類型：Accepted deferred work。這不是 Agent 自動產生的願望清單。

## Accepted Items

| ID | 優先度 | 狀態 | 項目 | 為何延後 | 完成條件 | 相依／阻擋 |
| --- | --- | --- | --- | --- | --- | --- |
| `BL-001` | High | In Progress | 將 `text_category_profiler/` 收斂為職責明確的 application package；詳見 [`text-category-profiler-package-migration.md`](text-category-profiler-package-migration.md) | Application-side path injection、legacy `PackageImport.py` providers、machine-specific `PythonModule` paths與 deployment 邊界已收斂；12 筆 bounded legacy/research manifest 已分流，PR #145 fresh targeted discovery 912 OK（2 SKIP）；PR #146 將 12 個歷史 XLSX 原 Git blob 分流、PR #147 分流 wiki article 研究樣本，本批再將 15 個 TXT 研究輸入原 Git blob 分流並更新手動 caller；本批將 Stage 4 現行使用的 Tulip 實作原 blob 移至 visualization 領域、更新 Test_result_Vis.py imports，並保留舊 tulip_utils lazy facade；13 個剩餘 package-root／巢狀 Dijkstra/Tulip 相容／vendor item 已建立 Git blob 身分 inventory 與 first-party AST import audit；`DB_utils.py` 的手動 entrypoint 舊裸模組匯入已改成 canonical integration path 並有無服務隔離測試；全 package 共 71 個 Git tracked 檔案已以明確 path ownership 清單分為 58 個 domain-owned（僅代表結構）與 13 個保全的 legacy entries，Hosted census 仍待驗證；44 個 canonical Python 模組新增按 first-party workspace/source area 分組的 AST import syntax 證據報告；實際運行／動態／repo 外 callers 和 Phase 0–3 其他功能分類仍需查證 | 達成本計畫的整體完成條件，完成剩餘 package-root 內容分流，且在最新 hosted head 上取得 fresh dependency-light test suite 通過證據 | 先處理 `text_category_profiler/` root 的 residual inventory（tests/experiments/scripts/vendor/legacy），再做最終 lightweight suite；H100/CUDA acceptance 由 `KI-003` 獨立追蹤 |

## Candidate Ideas

只有使用者希望先保存、但尚未承諾實作的構想放這裡；Agent 在一般任務中不得自行累積建議。

| ID | 構想 | 需要先回答的問題 | 提出來源 |
| --- | --- | --- | --- |
| 目前無項目 | — | — | — |

## Backlog Item 格式

- 穩定 ID：`BL-001` 起，不重用。
- 優先度：`P0 | P1 | P2 | P3`，需反映專案實際定義；若未定義，使用 `High | Medium | Low`。
- 狀態：`Accepted | Ready | In Progress | Blocked | Done | Dropped`。
- 範圍：指出相關模組或 contract。
- 原因：說明為何不是目前任務的一部分。
- 完成條件：必須可驗證，不只寫「優化」或「改善」。
- 關聯：可連到 `KI-*`、`ADR-*`、issue tracker 或文件。

## 收錄規則

可以加入：

- 使用者明確接受的延後工作。
- 目前變更無法安全完成、但為正確性或相容性所必需的後續。
- 已存在且能以證據說明的技術債。
- 明確標記的暫時 stub，其完成條件已知。

不要加入：

- Agent 隨手想到的所有改善可能。
- 沒有問題敘述、價值或完成條件的項目。
- 已在外部 issue tracker 管理、且本檔不需作為工作路由的完整副本。
- 當前任務範圍內本應完成、卻只為提早結束而延後的工作。
