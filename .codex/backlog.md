# Backlog

> 類型：Accepted deferred work。這不是 Agent 自動產生的願望清單。

## Accepted Items

| ID | 優先度 | 狀態 | 項目 | 為何延後 | 完成條件 | 相依／阻擋 |
| --- | --- | --- | --- | --- | --- | --- |
| `BL-001` | High | In Progress | 將 `text_category_profiler/` 收斂為職責明確的 application package；詳見 [`text-category-profiler-package-migration.md`](text-category-profiler-package-migration.md) | Application-side path injection、legacy `PackageImport.py` providers、machine-specific `PythonModule` paths與 deployment 邊界已收斂；12 筆 bounded legacy/research manifest 已分流，PR #145 fresh targeted discovery 912 OK（2 SKIP）；PR #146 將 12 個歷史 XLSX 原 Git blob 分流、PR #147 分流 wiki article 研究樣本，本批再將 15 個 TXT 研究輸入原 Git blob 分流並更新手動 caller；本批將 Stage 4 現行使用的 Tulip 實作原 blob 移至 visualization 領域、更新 Test_result_Vis.py imports，並保留舊 tulip_utils lazy facade；13 個剩餘 package-root／巢狀 Dijkstra/Tulip 相容／vendor item 已建立 Git blob 身分 inventory 與 first-party AST import audit；`DB_utils.py` 的手動 entrypoint 舊裸模組匯入已改成 canonical integration path 並有無服務隔離測試；全 package 共 71 個 Git tracked 檔案已以明確 path ownership 清單分為 58 個 domain-owned（僅代表結構）與 13 個保全的 legacy entries，Hosted census 仍待驗證；44 個 canonical Python 模組新增按 first-party workspace/source area 分組的 AST import syntax 證據報告；15 個 bare-import 候選新增同目錄／祖先目錄／沒有附近第一方 provider 的靜態路徑證據，7 個無 scoped-import modules 新增 top-level __main__ guard 分類；`Graph_utils.py` 移除唯一 catch-all `from utilities` fallback 改由 canonical `flattenList` 直接匯入並加 no-service regression；本批 `old_MP_utils.py` 的 `timeNow` bare import 已指向明確 canonical provider 並新增無服務 characterization（Hosted CI／Review 尚待確認）；PR #157 已將 `df_utils.py` 的 4 件 bare imports 明確接到現有 legacy providers 並加入 no-service contract tests（21/21 Hosted checks PASS、正式 Review 無 Findings，已合併）；本批另移除 `core.utilities` 中隱藏 canonical import failure 的 catch-all `.MP_utils` fallback 並新增 AST regression（CI／Review 待驗證）；最近 main 稽核在 205 個第一方 Python 來源中仍有一筆 Stage 4 裸名 `reusable_components`，PR #170 已改為顯式 BertScript provider 且 24/24 PR-head CI 與正式 Codex Review 0 Findings 後合併；本批修正稽核對 `BertScript/migrate_class_table.py` 合法相對匯入的 false unresolved 註記（CI／Review 待驗證）；真實 GUI／CLI、外部及動態 callers 仍需查證 | 達成本計畫的整體完成條件，完成剩餘 package-root 內容分流，且在最新 hosted head 上取得 fresh dependency-light test suite 通過證據 | 先處理 `text_category_profiler/` root 的 residual inventory（tests/experiments/scripts/vendor/legacy），再做最終 lightweight suite；H100/CUDA acceptance 由 `KI-003` 獨立追蹤 |
| `BL-002` | Medium | In Progress | 未來 AI 代理人蒐集分類文本時，產出 ClassTable／TopicTree 分類改進提議 | Notes 四欄已合併；本批另新增候選 CSV 的唯讀 AI provenance preflight（日期／來源／理由／待審狀態、AI新增／AI補充分流、原 CT 防覆寫），但尚未啟動蒐文代理、正文驗證、去重或 TopicTree 關係審核，不自動改寫正式分類 | 待代理流程明確實作：來源與去重證據、AI 新增／補充／理由及審核狀態寫入候選 CSV Notes；分類衝突／TopicTree 關係／既有人工資料防覆寫；經人工 Review/核准才合併正式 CSV，保留 revision history 與驗證報告 | PR #168 唯讀 provenance preflight 已於 2026-10-31 合併（23/23 CI、正式 Review 0 Findings）；本批另加選用新邊／AI新增節點集合一致性驗證（待 CI/Review），仍未核實關係語意；來源去重、實際文章證據、人工審核與 revision history 留待後續；不可將 AI 備註當人工批准 |

### BL-001 結構進度快照｜2026-11-24

- 近期 #323～#334 對 root/Stage 1～4/Work-ID 的生命周期安全與輸入/備份路徑採不覆寫、不自動修復策略；#333 修正 root 階段呼叫共用 mutable `exeTimeDict` 的結構問題。
- #335～#336 將 Stage 4 DataTable 篩選運算抽至 `BertScript/visualization_filter.py`，保留大型 Dash 入口的舊函式介面；這是局部脫鉤，不等於整個 GUI callback 都已重構或 KI-008 已正式驗收。
- `text_category_profiler/` Git tracked 完整清單現為 **77 = 64 canonical domain owned + 13 legacy 保全 + 0 未分類**，比上方歷史紀錄的 71/58 更新。靜態檢查可執行 `python -m scripts.bl001_structural_readiness --output <private-result.json>`，報告中的 PASS 只證明目前 module/manifest boundaries，仍固定明示外部 caller、WorkPool、GUI、GPU、SQLite 全部未由此驗證。
- **維持 `BL-001 In Progress`**：外部與動態 callers 尚未查完、8 個 compatibility entrypoints 仍保留、部分 provider/資料行為及正式環境驗收仍在 Phase 0–3／KI 待辦；不能因 structural gate PASS 而自動更改 Backlog 狀態或刪除舊資產。

### BL-001 收斂路由｜2026-11-25（main `7009222`）

- #338/#339/#341/#342 已合併，Stage 4 回呼狀態、任務選取及分頁政策各有明確 owner；尚未宣稱所有 GUI 回呼重構或使用者實機驗收完成。
- #346/#350 已合併，8 個 legacy facade 受 API／import 契約保護，動態載入僅有 bounded AST evidence；外部 caller 未驗證，不移除保全路徑。
- #347–359 已合併的 WorkPool 防護保持 fail-stop；read-only recovery observation 不構成 resume 或 cleanup 授權。#359 已知目的地碰撞在備份前拒絕；晚到競爭仍可能留下備份。
- #362 已合併，ClassTable strict-order 驗證與分類資料變更的完整輕量 CI 生效；不核准分類 metadata。
- Phase 0–3 的剩餘項目與產品環境 acceptance 分開列於 [遷移收斂盤點](text-category-profiler-package-migration.md#2026-11-25-結構收斂盤點基準-main-7009222)。BL-001 維持 In Progress；不重跑已通過且未受變更影響的驗收，不以 PR 數作完成條件。


### BL-001 新功能開發基準｜2026-11-27（main `8c50da5`）

- #366–#375 中本輪結構改良 PR（#366、#367、#368、#369、#370、#371、#372、#373、#374、#375）均已合併；#376 排序修復亦已合併。#374 結構 Gate 最終 HEAD 全部 3/3 CI PASS、正式 Review 0 Findings；完整輕量測試 1790 項（1750 PASS、40 SKIP、0 FAIL），Windows／Ubuntu 結構 Gate 均 PASS。
- 本輪重大主流程結構安全改良收尾；後續可優先做已接受的新功能，沿用 canonical/stage-local owner 及防回退契約。詳見 [新功能開發基準](text-category-profiler-package-migration.md#2026-11-27-新功能開發基準main-8c50da5)。
- **BL-001 仍為 In Progress**；原始 Phase 0–3 殘餘與五項 external acceptance 未取消，不宣稱部署就緒或所有歷史技術債結案。新功能依賴或具體正確性問題才優先觸發剩餘重構；未核准的外部復原、資料變更、相容入口移除仍禁止。BL-002 狀態及人工分類審核要求不變。

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
