# Project Memory

> 類型：Recent durable context。只保存能讓後續任務少走彎路的 current-state outcomes，不是 PR 流水帳。

## Current Focus

- 初始化狀態：`INITIALIZED`。
- 維護 Python 文字分類、資料集轉換、BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 已有 isolated real-root smoke profiles、activation-free `python TCFMain.py --doctor`；KI-002 已由 root-level WeiTech lifecycle characterization 解決。Application-side PackageImport/path injection 已收斂，`TRV_deploy` 保留為獨立 legacy snapshot；BL-001 仍需完成 package-root residual inventory 的分類／分流與最終 dependency-light suite。在 H100 real-model acceptance 完成前，不得宣稱完整 runtime 已驗證。

- PR #121 (Elasticsearch credential guard): 2026-10-25 在原分支修正 Codex P2 的條件式／動態 RHS `|=` 替代狀態，以及 eager iterable alias／直接 comprehension 的來源時間解析；程式 commit `cd5ff77616cd111dc44e20b4ee66c9ea70ecf7aa`，新增 14 組正反向 subTest（unittest methods 維持 271）。精確程式 HEAD 的 Push CI #40166810161 與 PR CI #40166819528 均 SUCCESS。**此為 CI 驗證結果，不是正式 Codex Review 清零；下一步須以更新後 HEAD 完成 CI 與新一輪正式 @codex review，核對 receipt、頂層 findings、inline threads、reactions。不得自行 Merge。**

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
