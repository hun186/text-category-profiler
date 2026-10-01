# Known Issues

> 類型：Verified open problems。只保存已證實、尚未解決，而且可能影響後續開發或使用的問題。

## Open Issues

| ID | 嚴重度 | 問題 | 影響範圍 | Workaround | 證據 | 狀態 |
| --- | --- | --- | --- | --- | --- | --- |
| `KI-003` | Medium | 已有隔離 root smoke，但尚缺 post-merge real-model/GPU acceptance evidence | 完整 runtime 驗證 | Layer A 啟用時必須 PASS；Layer B 留待明確 real-runtime inputs 與 H100/CUDA acceptance | `tests/test_full_pipeline_smoke.py`、`tests/test_full_pipeline_real_runtime.py`、`.codex/workflows.md` | Open |
| `KI-005` | Low | 乾淨環境僅安裝根 `requirements.txt` 時，repository-wide unittest discovery 會因缺少 `GPUtil` 產生 2 個 dependency errors | lightweight repository-wide validation | 先跑與變更範圍相符的 targeted tests；不得把 full discovery 宣稱為 clean PASS gate | `tests/test_df_utils.py` → `text_category_profiler.data.df_utils` → `text_category_profiler.core.utilities`；Codex review of PR #119 | Open |
| `KI-006` | High | Elasticsearch credential 曾硬編碼於 repository source；current source 已改為 `TCP_ELASTIC_PASSWORD`，但既有 Git 歷史仍可能包含舊值，外部輪替狀態尚未確認 | 仍接受舊 credential 的 Elasticsearch 環境 | 立即在 Elasticsearch 端輪替該 credential，部署時以 `TCP_ELASTIC_PASSWORD` 注入；不要把新 secret commit 到 Git | `text_category_profiler/ArtCluESJobTemplate.py`、`DatasetConverter/ESDataConfigFile.py` 的 current-source remediation；Git history 未重寫 | Open |

## Issue Details

### `KI-006` — Elasticsearch credential 曾進入 Git history

- 首次確認日期與環境：2026-10-02，BL-001 residual inventory 盤點。
- 證據位置：`text_category_profiler/ArtCluESJobTemplate.py` 與 `DatasetConverter/ESDataConfigFile.py` 的 hosted `main` current source 曾包含硬編碼 Elasticsearch password。
- Current-source remediation：兩個 config 保留既有 `es_tokens["password"]` contract，但值改由 `TCP_ELASTIC_PASSWORD` 環境變數提供；未設定時為 `None`，不再以 repository source 提供 secret fallback。
- 剩餘風險：本批不改寫 Git history，因此舊 revision 仍可能含有已曝光的 credential；若 Elasticsearch 端仍接受舊值，風險仍存在。
- 修復條件：在 Elasticsearch 端完成 credential rotation，確認舊 credential 已失效，部署改用 secret/environment injection，之後可將本項標記 Resolved。
- 狀態：Open。

### `KI-005` — lightweight discovery 缺少 GPUtil dependency

- 首次確認日期與環境：2026-10-01，PR #119 Codex review 的乾淨安裝環境。
- 最小重現方式或證據位置：依根 `requirements.txt` 建立環境後執行 `python -m unittest discover -s tests`；`tests/test_df_utils.py` 載入 `text_category_profiler.data.df_utils`，再到 `text_category_profiler.core.utilities` 的 unconditional `import GPUtil`。
- 預期與實際行為：repository-wide lightweight discovery 原先被文件描述為可直接使用的 dependency-light gate；實際目前產生 2 個 `ModuleNotFoundError: No module named 'GPUtil'`。
- 影響、嚴重度與受影響範圍：Low；不代表本次 PackageImport/path migration 回歸，但會阻止以乾淨 `requirements.txt` 環境取得 repository-wide clean PASS evidence。
- 已知 workaround 及其不足：先執行與修改範圍一致的 targeted tests（例如 `tests.test_package_layout`、`tests.test_project_docs`）；這不能取代最後的 repository-wide clean PASS。
- 修復條件：明確決定並實作 dependency policy（例如補齊 `GPUtil` dependency，或把不需要 GPU probe 的 lightweight import path 解耦），並取得 fresh repository-wide discovery PASS。
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
| `KI-002` | PR #98 已以 temporary filesystem 的 root-level WeiTech lifecycle characterization 覆蓋 queue acquisition、canonical test stages、offered-output delivery 與 processed completion；不再列為 current open issue | `tests/test_tcf_workpool_characterization.py` | 2026-09-22 | PR #98 |
| `KI-001` | 已確認根目錄有 lightweight discovery command；其 clean-environment dependency gap 目前另由 `KI-005` 追蹤 | `python -m unittest discover -s tests` | 2026-09-15 | `.codex/workflows.md`、`tests/test_project_docs.py` |
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
