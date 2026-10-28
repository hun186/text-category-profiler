# Project Memory

> 類型：Recent durable context。只保存能讓後續任務少走彎路的 current-state outcomes，不是 PR 流水帳。

## Current Focus

- 初始化狀態：`INITIALIZED`。
- 維護 Python 文字分類、資料集轉換、BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 已有 isolated real-root smoke profiles、activation-free `python TCFMain.py --doctor`；KI-002 已由 root-level WeiTech lifecycle characterization 解決。Application-side PackageImport/path injection 已收斂，`TRV_deploy` 保留為獨立 legacy snapshot；BL-001 仍需完成 package-root residual inventory 的分類／分流與最終 dependency-light suite。在 H100 real-model acceptance 完成前，不得宣稱完整 runtime 已驗證。

- PR #121 Elasticsearch credential guard: **MERGED 2026-10-27 19:28 Asia/Taipei** into `main` at merge commit `58c3bddbc2837e202efda98b3bbf30c5902ba458`; final reviewed head `e9bf2cd9ce0bfb27ccd064c570911cef339e898e`. Previous source-time P2 repairs and 271 unittest methods were retained; exact-head Codex review reported no major issues. External Elasticsearch credential rotation remains **KI-006 Open**, since rewriting Git history and revoking the old password are outside that PR.

- PR #122 Dash/comm compatibility: **MERGED 2026-10-27 21:06 Asia/Taipei** into main at `4c0f757f4ed1911f06798edf61774a18683c1e0d` after manual merge-conflict resolution. At exact reviewed integration HEAD `c0bab1b5ca9d`, Stage 4 48, GPUtil 9, ES security 271 hosted tests PASS; exact-head Codex found no issues. User subsequently confirmed Windows Dash **starts successfully**, but full WorkPool final handoff is not yet verified, so `KI-007` remains Open.

- PR #123 root GPUtil dependency fix: **MERGED 2026-10-27 20:33 Asia/Taipei** at `baec09b9d521be86137d2be18857023b20e51059`; dependency-light hosted contract 9 PASS, ES guard 271 PASS at reviewed PR HEAD. Fresh full root requirements install/repository-wide discovery remains unverified, so `KI-005` remains Open.

- PR #125 Stage 4 Dash idle-loop fix: **MERGED 2026-10-27 23:39 Asia/Taipei** at `9e2be27d629c8496cf3d3768ddff7ea4b9ffa29d`; exact-head Hosted CI and Codex Review PASS. User later confirmed Windows complete classification flow and Dash no longer repeatedly refreshes while idle; real filter/sort/pagination interactions not separately reported, so KI-008 remains open pending that final check.

- KI-009 Windows PyTorch/Transformers backend collision: user observed TensorFlow native DLL failure at `from transformers import BertModel` on another Windows/Anaconda machine. With `USE_TF=0`, `USE_TORCH=1` manually set in the same CMD, `BertModel` import and the full pipeline both ran. A separate PR scopes automatic flags to `TextClassification_transformers.py` (not TF15Bert); Hosted tests and **fresh CMD without manual flags Windows revalidation** are still required.

- PR #127 ClassTable CSV-first metadata 重構：獨立 branch feat/class-table-csv-metadata，從 `main@ec212fd17835dd939b010a680955f95f12593598` 開始；完整 CSV／loader、Dash Explanation migration、TopicTree／candidate validator、replay migration、unittest 與 Hosted CI。此 PR **OPEN / NOT MERGED**，請每次以 Hosted exact head 的 checks/reviews/threads 重新查證，未取得使用者明確 merge 指令不得合併。現有 ClassTable 1,994 labels 與 TopicTree 2,670 nodes 不等同，差集維持警示不自動補寫。

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
