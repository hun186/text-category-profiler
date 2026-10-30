# Known Issues

> 類型：Verified open problems。只保存已證實、尚未解決，而且可能影響後續開發或使用的問題。

## Open Issues

| ID | 嚴重度 | 問題 | 影響範圍 | Workaround | 證據 | 狀態 |
| --- | --- | --- | --- | --- | --- | --- |
| `KI-003` | Medium | 已有隔離 root smoke，但尚缺 post-merge real-model/GPU acceptance evidence | 完整 runtime 驗證 | Layer A 啟用時必須 PASS；Layer B 留待明確 real-runtime inputs 與 H100/CUDA acceptance | `tests/test_full_pipeline_smoke.py`、`tests/test_full_pipeline_real_runtime.py`、`.codex/workflows.md` | Open |
| `KI-005` | Low | 過去根 `requirements.txt` 未宣告 `GPUtil`，repository-wide discovery 因而產生 2 個 dependency errors；根 GPUtil 已宣告；PR #145 fresh targeted lightweight discovery 912 OK（2 SKIP），但仍待完整 root requirements 環境驗證 | lightweight repository-wide validation | CI 已針對所需套件安裝 GPUtil/pymongo/elasticsearch/pytz 並獲 PASS；完整 root requirements 安裝仍未驗證，不能等同完整 runtime acceptance | `tests/test_df_utils.py` → `text_category_profiler.data.df_utils` → `text_category_profiler.core.utilities`；Codex review of PR #119 | Open |
| `KI-009` | Medium | Windows/Anaconda 安裝 TensorFlow 但其原生 DLL 無法初始化時，PyTorch 的 `from transformers import BertModel` 仍可能間接匯入 TensorFlow 而中止 | Stage 2 `PytorchMMBERT`、`PytorchXLM` 等 transformers 分類入口 | Windows CMD 以 `set "USE_TF=0"`、`set "USE_TORCH=1"` 在同個終端機啟動；本 PR 在 PyTorch 專用入口先設兩旗標 | 使用者 2026-10-28 Windows 實機：未設 env 發生 `_pywrap_tensorflow_internal` DLL 錯誤；設 env 後 BertModel import 及完整流程 PASS | Open（自動設定待 Windows 實機驗收） |
| `KI-008` | Medium | Stage 4 Dash 空閒狀態持續執行 table→filter→chart callbacks；表格重新掛載的空 derived filter 造成重複輸出與洗版 | Windows Dash 前端、輸出磁碟及 CPU | 在未修正版本可先停止 Stage 4 服務避免繼續重複寫檔；本 PR 加入空事件防護與斷開 DataTable 自我 data Input | 2026-10-27 使用者實機輸出；`BertScript/Test_result_Vis.py` callback graph；`tests/test_visualization_stage.py` | Open（Windows 閒置洗版已改善；待篩選／排序／翻頁互動驗收） |
| `KI-006` | High | Elasticsearch credential 曾硬編碼於 repository source/sample config/setup notes；current source 已移除 tracked credential literals，runtime config 改由 `TCP_ELASTIC_PASSWORD` 注入，但既有 Git 歷史仍可能包含舊值，外部輪替狀態尚未確認 | 仍接受舊 credential 的 Elasticsearch 環境 | 立即在 Elasticsearch 端輪替該 credential，部署時以 `TCP_ELASTIC_PASSWORD` 注入；不要把新 secret commit 到 Git | `tests/test_es_secret_config.py` 掃描 current tracked ES surfaces；Git history 未重寫 | Open |

## Issue Details

### `KI-009` — PyTorch 分類入口間接載入無法初始化的 TensorFlow DLL

- 實機故障：Windows/Anaconda `TextClassification_transformers.py` 在 `from transformers import BertModel` → `transformers.image_transforms` → `import tensorflow` 時，`_pywrap_tensorflow_internal` 初始化失敗；尚無證據可歸因 CPU AVX 或 VC++ runtime。
- 已驗證 workaround：使用者在同一 Windows CMD 執行 `set "USE_TF=0"`、`set "USE_TORCH=1"` 後，`BertModel` 匯入正常，完整分類流程跑完；這只驗證手動設定，不等於本 PR 的自動設定已實機驗收。
- 專案側修正：`TextClassification_transformers.py` 屬 PyTorch 專用執行入口，在 `torch` / `transformers` 匯入之前呼叫 dependency-light `configure_pytorch_transformers_backend`，將本程序 `USE_TF=0`、`USE_TORCH=1`；`TF15Bert` 的 batch/runtime 路徑未修改。
- 關閉條件：Windows/Anaconda **全新 CMD、不手動設兩旗標**，確認 `USE_TF`／`USE_TORCH` 非預設 workaround，再實際執行 `TCFMain.py` 的 PyTorch 分類流程直到 Stage 2／後續 handoff 成功；TF15Bert 可用性另行按原有流程驗證。Hosted CI 的 AST/helper/runtime isolation tests 不能取代 Windows TensorFlow DLL 現場驗證。

### `KI-008` — Stage 4 Dash 閒置時 callback 反覆觸發

- 2026-10-27 Windows 實機現象：未操作 UI 時重複出現 `table_update`、`FilteredDF_update`（空 `derived_filter_query_structure=None`、無 query/sort）、`ChunkDF_update`，每回又輸出 `FilteredPreambleCols_df`；畫面與 console 反覆洗版。
- 已確認的程式路徑：`table_update` 每次重建 `VisDatatableCard` 內的 DataTable，原本又將自身重建的 `VisDatatable.data` 作為 Input；table mount 亦可重設 derived filter，造成無操作的 filter→chart→table 回授。
- 修正分支：僅在 **單一** `VisDatatable.derived_filter_query_structure=None` 事件、前次/本次 filter 皆 None、query 與 sort 均空白時，在任何磁碟輸出及 log 前 `PreventUpdate`；真正排序、設定/清除非空 filter、label/keyword input 仍交由原 callback；另外把沒被使用的 table `data` 自我 Input 降為 State，保留 page_current、page size、cut range、顏色與篩選真正互動入口。
- 驗證：dependency-light callback helper 行為測試、以 AST 載入 `FilteredDF_update` 證明假事件不觸發檔案/log、以及宣告端的回授保護；Hosted CI 不代表 Windows 瀏覽器長時間 idle 驗收。
- 關閉條件：使用者 Windows/Anaconda 修正版啟動 Dash，無操作持續觀察至少 1 分鐘不再連續執行 `FilteredDF_update`／`table_update` 或重寫 filtered SQLite/Excel；再操作排序、篩選、翻頁各一次，確認能正常更新且不進入循環。


### `KI-006` — Elasticsearch credential 曾進入 Git history

- 首次確認日期與環境：2026-10-02，BL-001 residual inventory 盤點。
- 證據位置：hosted source 曾在 `text_category_profiler/ArtCluESJobTemplate.py`、`DatasetConverter/ESDataConfigFile.py`、`DatasetConverter/elasticsearch/sampleBuilder.py`、sample INI 與 setup notes 中包含 Elasticsearch password / enrollment token 類 credential。
- Current-source remediation：runtime config 保留既有 `es_tokens["password"]` contract，但值改由 `TCP_ELASTIC_PASSWORD` 環境變數提供；sample INI 與 setup notes 僅保留安全 placeholder/操作說明，current tracked ES surfaces 不再提供 credential fallback 或 enrollment token literal。`tests/test_es_secret_config.py` 會掃描相關 tracked source/config/documentation 防止回歸。
- 剩餘風險：本批不改寫 Git history，因此舊 revision 仍可能含有已曝光的 credential；若 Elasticsearch 端仍接受舊值，風險仍存在。
- 修復條件：在 Elasticsearch 端完成 credential rotation，確認舊 credential 已失效，部署改用 secret/environment injection，之後可將本項標記 Resolved。
- 狀態：Open。

### `KI-005` — GPUtil 根依賴宣告已補齊，待 full discovery 驗證

- 首次確認日期與環境：2026-10-01，PR #119 Codex review 的乾淨安裝環境。
- 最小重現方式或證據位置：修正前依根 `requirements.txt` 建立環境後執行 `python -m unittest discover -s tests`；`tests/test_df_utils.py` 載入 `text_category_profiler.data.df_utils`，再到 `text_category_profiler.core.utilities` 的 unconditional `import GPUtil`。
- 預期與實際行為：repository-wide lightweight discovery 原先被文件描述為可直接使用的 dependency-light gate；實際修正前產生 2 個 `ModuleNotFoundError: No module named 'GPUtil'`；根依賴已補 GPUtil；PR #145 的 fresh Python 3.11 targeted deps Hosted run `41024022467` 完整執行 912 tests OK（skipped=2），但沒有安裝全 root requirements。為重現可移除該 run 已顯示的 `GPUtil`、`pymongo`、`pytz` 等套件，兩個 DataFrame 測試會出 dependency errors。
- 影響、嚴重度與受影響範圍：Low；不代表本次 PackageImport/path migration 回歸，但會阻止以乾淨 `requirements.txt` 環境取得 repository-wide clean PASS evidence。
- 已知 workaround 及其不足：已有 Hosted targeted dependency set 的完整 unittest discovery 912 OK（2 opt-in SKIP）與 artifact `12963076869`；仍不能取代全 root requirements 安裝、模型/GPU runtime 或最後合併後最新 main 的獨立驗收。
- 修復條件：明確決定並實作 dependency policy（根依賴宣告已補上 `GPUtil`；另外可評估是否解耦不需要 GPU probe 的 lightweight import path），並取得 fresh repository-wide discovery PASS。
- 狀態：Open（fresh targeted env full unittest discovery 已 PASS；完整 root requirements 安裝及 postmerge latest main gate 仍待確認）。

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
| `KI-007` | Windows Anaconda Dash import 的舊 `comm` 阻擋已處理；PR #122 補齊 `comm>=0.2.3` 與精確診斷，後續實機確認 Dash 能啟動、分類流程可跑完。KI-003 與 KI-008 的獨立驗收未被此結果取代 | PR #122 exact-head Hosted/Review PASS；2026-10-28 使用者 Windows 實機回報 | 2026-10-28 | PR #122、`BertScript/visualization_stage.py` |
| `KI-002` | PR #98 已以 temporary filesystem 的 root-level WeiTech lifecycle characterization 覆蓋 queue acquisition、canonical test stages、offered-output delivery 與 processed completion；不再列為 current open issue | `tests/test_tcf_workpool_characterization.py` | 2026-09-22 | PR #98 |
| `KI-001` | 已確認根目錄有 lightweight discovery command；其 clean-environment dependency gap 目前另由 `KI-005` 追蹤 | `python -m unittest discover -s tests` | 2026-09-15 | `.codex/workflows.md`、`tests/test_project_docs.py` |
| `KI-004` | 修正 Python mapping 語法與部署範例 placeholder；將 CSS 與資料片段以真實副檔名重新分類，而非偽裝成 Python；移除 legacy FTP 範例的連線資料與 import-time 行為，改為明確拒絕網路操作的 inert compatibility stubs，未建立新網路功能 | `python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler` exits 0；`python -m unittest tests.test_repository_compile_gate` | 2026-09-17 | `tests/test_repository_compile_gate.py` 與 KI-004 blocker corrections |

### `KI-007` — Windows/Anaconda Dash 匯入時的舊 comm 相容性

- 觀測：2026-10-27 Windows Anaconda 實機完整流程，RunClassfier 與 CombineTestResult 成功；Stage 4 於 `import dash` → `dash._jupyter` → `comm.create_comm(target_name="dash")` 因舊 `comm` 的 `NotImplementedError("Cannot ")` 中斷。
- 根因界線：`comm` 的舊預設實作沒有無 kernel 的 DummyComm 支援；根 `requirements.txt` 原未明列版本下限。不能因此推斷模型分類 0/7 或 GPU free 0MB 的原因。
- 專案側：新增 `comm>=0.2.3` 需求與針對該已知錯誤的 import 診斷；不 monkeypatch Jupyter／Dash，亦不吞掉其他 `NotImplementedError`。測試證明依賴錯誤被正確辨識；後續 Windows 實機已確認 Dash 可啟動。
- 修復／驗收：在啟動 `TCFMain.py` 的同一 Python 環境升級 `comm`，驗證 `python -c "import dash; print(dash.__version__)"`，並以原 Stage 4 命令及工作池 handoff 驗證恢復。
- 2026-10-28 後續使用者實機回報：Windows 分類流程可完整執行、Dash 已能啟動；故本項 **Dash 匯入阻擋** 結案。未提供逐一列示的 final WorkPool directory／交接 artifact，因此不得以此替代 KI-003 的獨立完整 runtime/GPU acceptance。Dash 篩選／排序／翻頁互動未證實，仍屬 KI-008 Open。
- 狀態：Resolved（Dash/comm import blocker）。


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
