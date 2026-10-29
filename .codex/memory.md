# Project Memory

> 類型：Recent durable context。只保存能讓後續任務少走彎路的 current-state outcomes，不是 PR 流水帳。

## Current Focus

- 初始化狀態：`INITIALIZED`。
- 維護 Python 文字分類、資料集轉換、BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 已有 isolated real-root smoke profiles、activation-free `python TCFMain.py --doctor`；KI-002 已由 root-level WeiTech lifecycle characterization 解決。Application-side PackageImport/path injection 已收斂，`TRV_deploy` 保留為獨立 legacy snapshot；BL-001 仍需完成 package-root residual inventory 的分類／分流與最終 dependency-light suite。新增 bounded 12-file research preservation inventory 測試僅保護已知 Git blobs／原路徑與手動 cwd 呼叫；GitHub code search 受限且外部 caller 尚未確認，研究檔未移動；此外，`切片相似度比對法測試/` 的 27 份歷史文件（12 Excel、15 TXT、824,594 bytes）已建立原位 Git blob 完整性清單與測試，未移動文件、未執行研究流程、外部 caller 仍未確認。最終 discovery 仍未驗收。在 H100 real-model acceptance 完成前，不得宣稱完整 runtime 已驗證。

- PR #121 Elasticsearch credential guard: **MERGED 2026-10-27 19:28 Asia/Taipei** into `main` at merge commit `58c3bddbc2837e202efda98b3bbf30c5902ba458`; final reviewed head `e9bf2cd9ce0bfb27ccd064c570911cef339e898e`. Previous source-time P2 repairs and 271 unittest methods were retained; exact-head Codex review reported no major issues. External Elasticsearch credential rotation remains **KI-006 Open**, since rewriting Git history and revoking the old password are outside that PR.

- PR #122 Dash/comm compatibility: **MERGED 2026-10-27 21:06 Asia/Taipei** into main at `4c0f757f4ed1911f06798edf61774a18683c1e0d` after manual merge-conflict resolution. At exact reviewed integration HEAD `c0bab1b5ca9d`, Stage 4 48, GPUtil 9, ES security 271 hosted tests PASS; exact-head Codex found no issues. User subsequently confirmed Windows Dash **starts successfully** and the Windows classification pipeline completed. Therefore the **KI-007 Dash import/startup blocker is Resolved** based on user real-machine feedback; this does not establish independently inspected final WorkPool/GPU acceptance (`KI-003`) or UI filter/sort/pagination interactions (`KI-008`, Open).

- PR #123 root GPUtil dependency fix: **MERGED 2026-10-27 20:33 Asia/Taipei** at `baec09b9d521be86137d2be18857023b20e51059`; dependency-light hosted contract 9 PASS, ES guard 271 PASS at reviewed PR HEAD. Fresh full root requirements install/repository-wide discovery remains unverified, so `KI-005` remains Open.

- PR #125 Stage 4 Dash idle-loop fix: **MERGED 2026-10-27 23:39 Asia/Taipei** at `9e2be27d629c8496cf3d3768ddff7ea4b9ffa29d`; exact-head Hosted CI and Codex Review PASS. User later confirmed Windows complete classification flow and Dash no longer repeatedly refreshes while idle; real filter/sort/pagination interactions not separately reported, so KI-008 remains open pending that final check.

- KI-009 Windows PyTorch/Transformers backend collision: user observed TensorFlow native DLL failure at `from transformers import BertModel` on another Windows/Anaconda machine. With `USE_TF=0`, `USE_TORCH=1` manually set in the same CMD, `BertModel` import and the full pipeline both ran. A separate PR scopes automatic flags to `TextClassification_transformers.py` (not TF15Bert); Hosted tests and **fresh CMD without manual flags Windows revalidation** are still required.

- PR #127 ClassTable CSV-first metadata 重構：**MERGED 2026-10-28 08:59 Asia/Taipei**，merge commit `513808de4ce7b3fff17f13021aa33c20ce6cead9`；正式 CSV／loader、Dash Explanation、TopicTree validator、遷移驗證與 Hosted CI 已入 main。後續 ClassLabel 更名應同步更新 migration replay 的明確允許修正與 unittest；TopicTree 是 graph authority，仍只以警示呈現既有缺漏。

- PR #128 中國房地產分類更名：**MERGED 2026-10-28 11:27 Asia/Taipei**，main merge commit `38b5e1f4a6950193b31ddd7d59871f58cfaabe5b`。`ClassTable.csv` 兩個正式 ClassLabel 對齊 TopicTree 的 `CN Real Estate Industry`／`CN Government Real Estate Policy`，原 Explanation 保留，1,994 筆不變；Hosted 5 項 CI 與 Codex exact-head Review PASS，merge 後 main 的 5 項 CI 亦 PASS。

- BL-001 Phase 3 RAND corpus 原型分流：既有 `text_category_profiler/utilities_RAND.py` 非生產共享 helper，移至 `experiments/rand_corpus_labeling.py`，舊路徑保留 import-safe 相容入口與既有 lazy helper names；新增 stdlib characterization + Hosted CI。只有明確執行才會觸發 RAND SQLite／資料複製，本批沒有實際跑 RAND corpus；BL-001 維持 In Progress。其他獨立 PR #124 不受變更。

- PR #124 BL-001 Phase 3 timestamp experiment：**MERGED 2026-10-28 16:57 Asia/Taipei**，main merge `fec6e8e24de459d3463dbf337d3529d208526287`。時間戳實驗改在 `experiments/timestamp_generator.py` 由 `main()` 明確觸發；原 CLI 路徑為 import-safe wrapper。衝突整合後 exact-head Codex Review 0 Findings、Hosted CI 5/5 PASS；merge 後 main 5/5 PASS。BL-001 仍 In Progress。

- PR #130 BL-001 ES text ingest 分流：**MERGED 2026-10-28 17:19 Asia/Taipei**，main merge `102bcecdfdbaafed7105a485363ee7b7f0d5deaf`；`CONTRACT-CLI-002` 的正式實作位於 `scripts/ES_ingest_txt_to_es.py`，舊路徑保留 CLI/lazy helpers，修正 bare ES_utils import。專屬契約測試 8/8 PASS、Codex Review 0 Findings，合併後 main 6/6 CI PASS；真實 Elasticsearch acceptance 未執行。BL-001 仍 In Progress。

- BL-001 Phase 3 vendor 與配置分流：PR #131 Dijkstra MIT 範例已合併（`474d28a49847`）、PR #133 修改版 CPython v3.7.17 GBK ZIP 與 PSF LICENSE 已合併（`680608b1f04b`），#133 合併後 Hosted CI 7/7 PASS。當前一批獨立整理 legacy `ArtCluESJobTemplate.py`：權威設定搬至 `text_category_profiler/integrations/es_job_template.py`，完整保留原始 Git blob／每次執行模組的環境變數 snapshot／可變 dict 與舊 import，僅驗證 import 及設定，不驗證真實 ES。BL-001 仍 In Progress。

- BL-001 Phase 3 CLI selector 分流：將 `text_category_profiler/selector.py` 的原始 source（Git blob `136a4caea6f9`）完整搬至 `text_category_profiler/cli/selector.py`，舊 import 保留三個 class 與 `Fore`/`Back`/`Style` 相容 re-export。使用 stdlib mock colorama/curses 與 input 驗證單選、多選、default、重試及 explicit curses，未使用真實終端、未改原有 mutable defaults。package-root 的研究資料及最終 dependency-light suite 仍待另外處理，BL-001 In Progress。

- BL-001 Phase 3 Kaggle CSV sample fixtures：保留 `text_category_profiler/KaggleExtraction/` 兩個相同內容的 CSV 範例與 `text_category_profiler/csvSample/` 24 個輸出 txt 的完整 Git blob，共 26 檔、1,182 bytes，移至 `experiments/fixtures/kaggle_csv_sample/`。內附 JSON manifest 記錄每個歷史路徑、SHA、大小；stdlib tests/CI 做完整性、重複內容與 source path 引用檢查；Hosted CI 首輪發現 `pipeline/DataConverter_utils.py` 的 `__main__` 手動 CSV 範例仍用舊 Windows 絕對路徑，已改為依 `__file__` 定位遷移後的 fixture 並新增回歸檢查，原迴圈仍保留。歷史原路徑移除、不建立 Windows symlink；外部手動腳本須改路徑。根資料中的 `Similarity.tsv`、`RAGTest.json`、Excel、相似度測試文檔等仍待分批分類；獨立的 MoodleDocs locale PDF 已按原 Git blob 移至 `docs/references/`，BL-001 不標 Done。

## Durable Outcomes

1. Root configuration 已由 frozen `PipelinePlan` 與明確 runtime activation 隔離，import 不解析 process argv 或啟動 filesystem/process runtime。
2. Root execution 由 `LegacyShellProcessRunner` 保留 `shell=True` invocation，只有 root-owned `RootFailFastPolicy` 套用 fail-fast；Stage 2／4 call-site policies 刻意不同。
3. `TCFMain.py` 是 compatibility composition root；dependency-light `PipelineOrchestrator` 只經 injected ports 擁有四 stage、可選 SDSMS merge 與 delivery 的順序。
4. WorkPool lifecycle 由 `WorkPoolManager`／`DeliveryManager` 經 `LegacyFileSystem` 擁有；KI-002 Phase 1 已以 temporary filesystem 從 `TCFMain.main()` 證明同一 WeiTech work ID 經 acquire、canonical test stages、offered-output delivery 與 processed completion，但 child stages 仍是隔離 stub，並非 real-model integration。
5. DatasetConverter 以 `StagePlan`／`StageContext`、typed immutable config、`core`／`sources`／`adapters` boundaries 保留 canonical converter 行為與 dependency-light planning。
6. Stage 2 以 `ClassifierPlan`／lifecycle boundary 擁有 activation、authoritative command rendering、call-site failure policy 與成功 handoff；ML computation 留在 compatibility entrypoint。
7. Stage 3 以 `ResultCombinationPlan`／lifecycle boundary 擁有 canonical inputs、activation 與成功 handoff；pandas/SQLite computation 留在 compatibility entrypoint。
8. Stage 4 以 `VisualizationPlan`／dependency-light lifecycle boundary 擁有 ready→running、hosted decision 與成功 running→spike-ready handoff；Dash layouts、callbacks 與 algorithms 留在 compatibility entrypoint。
9. AST architecture guards保護 shared boundaries 不反向 import stage implementations、stages 不控制後續 stage、DatasetConverter split 與五個 legacy entrypoint paths；application tree 另禁止 bare `utils`／`tcf_utils`、legacy `PythonModule` path、deployment snapshot imports、`PackageImporter` consumers 與 import-time `os.chdir()`。Repository 中剩餘 `PackageImport.py`／`PythonModule/` 均侷限於 `TRV_deploy` snapshot。
10. Production default model 是 dependency-light `DEFAULT_MODEL_TYPE=PytorchMMBERT`；Layer B model discovery 同時傳遞 model type／TRVPort。Doctor 與 `--self-test {isolated,real}` 都在 activation 前分流；production-owned full-pipeline runner 將預期 setup／model-facade／process-launch failures 轉為 structured FAIL 並清除已配置的 temporary runtime，且提供明確 classifier device evidence；KI-002 已解決，Layer A PASS、Layer B NOT YET ACCEPTED 與 `KI-003` 維持 Open。
