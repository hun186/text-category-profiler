# Project Memory

> 類型：Recent durable context。只保存能讓後續任務少走彎路的 current-state outcomes，不是 PR 流水帳。

## Current Focus

- **Latest Hosted status 2026-10-31:** `main@4797ed8c608efe1e23f096aa8d7085d3f81a5925` merged PR #170 (main Stage 4 `BertScript.reusable_components` explicit import) after **24/24 PR-head Hosted CI PASS** and exact-head formal Codex Review completed with **0 Findings**. PR #171 consolidated the project memory at merge `bf5fd86f81d5d2b95597773a349a4b552a0229df` after 21/21 PR-head Hosted CI and 0-Finding exact-head formal Review; post-merge main CI must be checked separately. Former PR #53 was closed without merge because it was superseded by newer DatasetConverter boundaries.

- **BL-001 High / In Progress:** latest pre-PR #170 canonical import audit (205 first-party Python files, 44 canonical modules) found one same-directory bare-name candidate in `BertScript/Test_result_Vis.py`; PR #170 fixed it and targeted tests now require zero. This PR additionally resolves the one previously misclassified `BertScript/migrate_class_table.py` conditional relative-import *syntax* using the tracked BertScript package boundary (Hosted CI and Review pending). This verifies bounded AST syntax, **not** dynamic/runtime resolution, external callers, or GUI use. The 71 tracked package paths were structurally assigned (58 domain-owned + 13 legacy compatibility/vendor), with original Git blob fixtures retained; outstanding work remains in `.codex/backlog.md` and `.codex/text-category-profiler-package-migration.md`.

- **BL-002 Medium / In Progress:** AI `ClassTable` Notes metadata and read-only candidate validation (PR #168, merge `498ad6127f3c83cf`) plus optional proposed TopicTree node-set alignment (PR #169, merge `1867ae5f8607e2ff`) are in main; #169 post-merge Hosted checks 23/23 passed. Neither feature crawls/verifies news, deduplicates source documents, approves relations, or changes official CSV. AI proposals must remain **待人工審核** pending a real human gate, source evidence, and revision records.

- **ClassTable/TopicTree ownership:** authoritative `ClassesTree/data/ClassTable.csv` stores 1,994 `ClassLabel,CT,Explanation,Notes` metadata entries; `ClassesTree/data/TopicTree.csv` owns graph edges. The retired `BertScript/ClassTable.py` import must not be revived. Use `BertScript.class_table_metadata.load_class_table()`; active consumers use `Explanation` spelling. Original Notes entries started blank; AI suggestions cannot overwrite existing human entries without approval.

- **Stage 4 Jaal/UI:** PRs #165–#167 merged; the original Jaal vis.js controls (Search/Filter/Color/Size) and lightweight embedded Cytoscape view are separate, visible, lazy same-port capabilities. Original Jaal bounds: >250 nodes requires consent, >3,000 nodes or >5,000 edges rejected, maximum three process-local mounts. Hosted Jaal compatibility tests pass; actual Windows browser behavior and large graph performance are **not yet verified**. See `docs/embedded-class-tree.md`.

- **Windows/Dash known limits:** **KI-007 Dash import/startup blocker is Resolved** based on prior user Windows run; idle redraw was improved, but **KI-008** sort/filter/pagination browser acceptance remains Open. **KI-009** PyTorch/Transformers TensorFlow DLL collision has a staged `USE_TF=0`/`USE_TORCH=1` boundary, but needs fresh CMD execution without manual flags to close.

- **Runtime acceptance:** `KI-003` real-model/H100 CUDA end-to-end verification remains Open; Layer A isolated run does not establish Layer B acceptance. Fresh targeted dependency-light Hosted `python -m unittest discover -s tests` passes on reviewed PR heads, with opt-in full-pipeline tests skipped. `KI-005` full root requirements install validation remains separately Open; do not equate these tests with real WorkPool/model completion.

- **Secrets:** `KI-006` current tracked Elasticsearch credentials were guarded by PR #121, but revocation/rotation of any leaked historical secret remains **unverified** and cannot be completed through a source-only PR. Never write actual credentials into repository, fixtures or logs.

- **History routing:** This Current Focus is bounded to the last decisions and blockers. Older PR-by-PR handoff details formerly in this section are preserved in `.codex/archive/memory-focus-history-2026-10-31.md`; do not reload archive routinely. For live project work use `AGENTS.md`, current `.codex` files, real code and latest Hosted GitHub.

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
