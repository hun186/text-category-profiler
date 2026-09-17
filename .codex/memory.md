# Project Memory

> 類型：Recent durable context。只保存能讓後續任務少走彎路的 current-state outcomes，不是 PR 流水帳。

## Current Focus

- 初始化狀態：`INITIALIZED`。
- 維護 Python 文字分類、資料集轉換、BERTScript 結果分析工作區；不要沿用舊 README 的 FastAPI RAG 假設。
- 已有 isolated real-root smoke profiles；在 post-merge real-model/H100 acceptance 完成前，不得宣稱完整 runtime 已驗證。

## Durable Outcomes

1. Root configuration 已由 frozen `PipelinePlan` 與明確 runtime activation 隔離，import 不解析 process argv 或啟動 filesystem/process runtime。
2. Root execution 由 `LegacyShellProcessRunner` 保留 `shell=True` invocation，只有 root-owned `RootFailFastPolicy` 套用 fail-fast；Stage 2／4 call-site policies 刻意不同。
3. `TCFMain.py` 是 compatibility composition root；dependency-light `PipelineOrchestrator` 只經 injected ports 擁有四 stage、可選 SDSMS merge 與 delivery 的順序。
4. WorkPool lifecycle 由 `WorkPoolManager`／`DeliveryManager` 經 `LegacyFileSystem` 擁有；recording filesystem tests 不等於完整 root/model integration，`KI-002` 維持 Open。
5. DatasetConverter 以 `StagePlan`／`StageContext`、typed immutable config、`core`／`sources`／`adapters` boundaries 保留 canonical converter 行為與 dependency-light planning。
6. Stage 2 以 `ClassifierPlan`／lifecycle boundary 擁有 activation、authoritative command rendering、call-site failure policy 與成功 handoff；ML computation 留在 compatibility entrypoint。
7. Stage 3 以 `ResultCombinationPlan`／lifecycle boundary 擁有 canonical inputs、activation 與成功 handoff；pandas/SQLite computation 留在 compatibility entrypoint。
8. Stage 4 以 `VisualizationPlan`／dependency-light lifecycle boundary 擁有 ready→running、hosted decision 與成功 running→spike-ready handoff；Dash layouts、callbacks 與 algorithms 留在 compatibility entrypoint。
9. AST architecture guards保護 shared boundaries 不反向 import stage implementations、stages 不控制後續 stage、DatasetConverter split 與五個 legacy entrypoint paths。
10. Repository-wide Python compile gate (`python -m compileall TCFMain.py TCF_Params DatasetConverter BertScript text_category_profiler`) 維持 restored，isolated root smoke 已建立；`KI-003` 等待 post-merge real-runtime acceptance，且不涵蓋 WeiTech acquisition/delivery 的 `KI-002` 仍為 Open。
