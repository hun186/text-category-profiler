# text-category-profiler Architecture Refactoring Design v1

## 1. Document Control

| Item                                     | Value                                                                                                           |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Repository                               | `hun186/text-category-profiler`                                                                                 |
| Branch                                   | `main`                                                                                                          |
| Hosted source baseline                   | `aac3453a15faa06e1d9415c2c127a15f7af35092`                                                                      |
| Design version                           | Architecture Refactoring Design v1                                                                              |
| Supersedes                               | None                                                                                                            |
| Status                                   | Proposed                                                                                                        |
| Refactoring strategy                     | Behavior-preserving incremental refactor                                                                        |
| Primary compatibility goal               | Existing CLI, input formats, output paths/names, stage order and observable pipeline behavior remain compatible |
| Source authority                         | Hosted GitHub source at the baseline above                                                                      |
| Runtime verification in this design pass | Not performed; this is a source-level architecture design                                                       |

---

# 2. Purpose

`text-category-profiler` 已由早期 Python script 型專案逐步發展成包含資料轉換、模型推論／訓練、結果整合及視覺化分析的完整 pipeline。現有功能可運作，但部分程式仍保留早期 script-oriented 架構特徵，例如 global configuration、import-time initialization、command string assembly、subprocess execution、filesystem mutation、logging 與 orchestration 混合於相同模組。

本次重構不以重新設計產品、不以改變模型、不以更換 ML framework 為目標，而是：

> 在保持既有外部行為相容的前提下，將現有程式整理成具有明確 stage boundary、configuration boundary、execution boundary 與 filesystem boundary 的可維護架構。

現有 `.codex/architecture.md` 已明確定義 root flow 由 `TCFMain.py` 串接 DataConverter、classifier、result combination 與 visualization，而 CLI 與 handoff file/directory naming 目前都屬於需要維持相容的既有契約。

---

# 3. Primary Design Constraints

本次重構有三項最高優先設計約束。

| Constraint                      | Requirement                                                                                                       |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Four-stage mental model         | 保留資料轉換、分類、結果整合、視覺化／輸出的主要 pipeline 階段，作為開發者閱讀與維護系統的主要心智模型                                                          |
| External compatibility          | 不任意修改現有 CLI option、CLI default、輸入格式、主要輸出檔名、handoff directory naming、stage ordering、主要 script invocation path      |
| Internal boundary modernization | 將 configuration、process execution、filesystem、logging、timing、work-pool lifecycle 等橫切責任由 stage implementation 中逐步抽離 |

此設計不要求第一輪重新排列 repository 目錄。

特別是現有：

```text
TCFMain.py
DatasetConverter/DataConverter.py
BertScript/RunClassfier.py
BertScript/CombineTestResult.py
BertScript/Test_result_Vis.py
```

應先視為 compatibility entrypoints。

目前 root workflow 也仍正式記錄以上四個 canonical stage command。

---

# 4. Current Architecture Diagnosis

## 4.1 Root orchestrator responsibility overload

目前 `TCFMain.py` 不只負責 stage sequencing。

它同時包含工作池選取與搬移、command string 組裝、subprocess execution、dataset existence validation、計時、logging、backup、cleanup、Linux ownership adjustment 及 stage-specific control flow。

例如 `DataConvert()` 同時處理 work ID、filesystem mutation、command assembly、process execution 與 output validation；`RunClassfier()`、`CombineTestResult()`、`TestResultVis()` 則重複 command assembly + subprocess invocation 模式。

因此目前最大的架構問題不是 stage 數量，而是：

```text
orchestration
+
infrastructure
+
business/stage logic
```

尚未完全分離。

---

# 5. Configuration Boundary Problem

目前 CLI 的 canonical parser 為：

```python
ClassfierOptionParser(argv=None)
```

其本身已具備可注入 `argv` 的能力，這對測試相當有利。

但 `TCF_Params/TCFParameters.py` 在 module import 時又直接呼叫：

```python
args = ClassfierOptionParser()
```

並依據 `args.debugMode`、`args.TrainDRNDataOnly`、OS platform 等條件建立 global runtime state。

另外 `setArguments()` 還會執行 filesystem rename、建立目錄相關動作、修改 `FinalOfferedOutputFNrePatList`、計算 multiprocessing 數量等。

因此 Configuration 在設計上需要分成：

```text
Parse
  ↓
Normalize
  ↓
Validate
  ↓
Plan
  ↓
Activate runtime side effects
```

而不能繼續把這些步驟視為同一件事。

---

# 6. Existing Good Pattern: DatasetConverter

本設計不重新發明 DatasetConverter 的架構。

目前 `DatasetConverter/stage.py` 已建立：

```text
CLI / legacy settings
        ↓
normalize_stage_plan()
        ↓
     StagePlan
        ↓
activate_stage_context()
        ↓
    StageContext
```

其中 `StagePlan` 為 frozen dataclass，先完成 configuration normalization；真正建立 directory、logger 與 timing state 則延後到 activation。並且保留 `setArguments()` compatibility wrapper 給 legacy caller。

這個模式應成為其他 stage 以及 root orchestration modernization 的主要參考模式。

原則是：

> Adopt the architectural pattern, not necessarily copy the exact implementation.

也就是其他 stage 不必機械式複製 DatasetConverter 所有 class，但應遵守「先描述執行意圖，再產生 side effect」的相同理念。

---

# 7. Target Conceptual Architecture

目標架構採 **Stage-oriented architecture with shared internal boundaries**。

```text
                         CLI
                          │
                          ▼
                 Compatibility Root
                    TCFMain.py
                          │
                          ▼
                 Pipeline Orchestrator
                          │
          ┌───────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
       Stage 1          Stage 2         Stage 3          Stage 4
      Dataset         Classifier       Result          Visualization /
     Conversion                       Combination        Delivery
          │               │                │                │
          └───────────────┴───────────────┴────────────────┘
                                  │
                                  ▼
                       Shared Runtime Boundaries
                        ┌────────────────────┐
                        │ Configuration      │
                        │ Process Execution  │
                        │ Filesystem         │
                        │ Logging / Timing   │
                        │ WorkPool Lifecycle │
                        └────────────────────┘
```

最重要的是 dependency direction。

Stage 1 不應藉由 import Stage 2 implementation 來控制下一階段；Stage 2 也不應直接操作 Stage 3。

Pipeline sequencing 屬於 Orchestrator。

Stage 本身只負責：

```text
receive input/config
→ perform one stage
→ verify its own output contract
→ return/report result
```

---

# 8. Four Canonical Stages

| Stage   | Responsibility           | Existing canonical entrypoint       | Main contract                                      |
| ------- | ------------------------ | ----------------------------------- | -------------------------------------------------- |
| Stage 1 | Dataset Conversion       | `DatasetConverter/DataConverter.py` | 原始資料 → classifier-ready dataset                    |
| Stage 2 | Classification           | `BertScript/RunClassfier.py`        | dataset/model → prediction/model artifacts         |
| Stage 3 | Result Combination       | `BertScript/CombineTestResult.py`   | prediction + source/index → combined analysis data |
| Stage 4 | Visualization / Delivery | `BertScript/Test_result_Vis.py`     | combined result → visualization/delivery artifacts |

目前 Stage 2–4 在實體 repository 上仍大量集中於 `BertScript/`，因此「四階段」在本 Design 中首先是一個**正式 logical architecture boundary**，不強迫第一輪立即變成四個新的實體 package。

---

# 9. Compatibility Entrypoint Strategy

第一輪禁止因架構美化而任意改掉 legacy invocation。

例如這些命令必須保持成立：

```bash
python TCFMain.py ...
python DatasetConverter/DataConverter.py ...
python BertScript/RunClassfier.py ...
python BertScript/CombineTestResult.py ...
python BertScript/Test_result_Vis.py ...
```

未來 legacy script 可以逐步瘦身，例如：

```python
from internal_stage_package import main

if __name__ == "__main__":
    main()
```

因此 transition architecture 為：

```text
Existing CLI
    ↓
Existing file path
    ↓
Compatibility wrapper
    ↓
Refactored implementation
```

這種方式允許內部架構大幅改善，但不要求外部 operator、batch script 或 TCFMain 同時改寫。

---

# 10. Pipeline Orchestrator Boundary

未來 `TCFMain.py` 最終應收斂成 composition root，而非所有 runtime behavior 的實作位置。

Conceptually：

```python
def main(argv=None):
    config = build_application_config(argv)
    runtime = build_runtime(config)
    pipeline = build_pipeline(runtime)
    return pipeline.run()
```

Pipeline orchestrator 負責：

```text
Stage order
conditional stage execution
stage failure propagation
whole-run timing
top-level lifecycle
```

而不應負責：

```text
shell quoting details
shutil implementation
chown implementation
directory traversal
classifier-specific option logic
visualization-specific filesystem logic
```

這些責任應分派至明確 boundary。

---

# 11. Process Execution Boundary

這是本次重構的高優先項目。

目前 root flow 會建立完整 command string，例如：

```python
CMD = "python DatasetConverter/DataConverter.py"
CMD += convert_to_args_str(args)
run_stage_command(CMD, ...)
```

並透過：

```python
subprocess.run(CMD, shell=True, ...)
```

執行。

第一輪**不可直接把 shell execution 全面改成 argv-list execution**，因為 shell quoting、boolean representation、path handling 等可能已形成隱性 compatibility behavior。

因此應先引入：

```text
ProcessRunner interface
        ↓
LegacyShellProcessRunner
```

讓第一版 implementation 完全複製現有 subprocess semantics。

只有 characterization test 證明 parity 後，後續才可考慮：

```text
ArgumentListProcessRunner
```

這使 execution security / portability modernization 與 architecture refactor 分成兩個可獨立驗證的問題。

---

# 12. Command Specification Boundary

Stage 不應直接自行拼字 command string。

應逐步引入 conceptual command specification：

```python
StageCommand(
    stage="classifier",
    executable=...,
    script=...,
    forwarded_args=...,
)
```

Command specification 應能被單獨測試：

```text
input config
    ↓
expected command representation
```

而完全不啟動模型。

這將讓 classifier、result combination 與 visualization 的 orchestration tests 不必依賴 GPU、TensorFlow、PyTorch、模型 checkpoint 或真實資料。

---

# 13. Configuration Model

現有 `argparse.Namespace` 在 compatibility boundary 繼續存在。

本 Design 不要求一次把所有 CLI args 改為 dataclass。

目標 transition 應為：

```text
argparse Namespace
       │
       ├──────────── legacy scripts
       │
       ▼
normalized internal configs
```

內部 config 可依責任逐步拆成：

```text
RuntimeConfig
DatasetConfig
ClassifierConfig
WorkPoolConfig
VisualizationConfig
TaskModeConfig
```

但不得因內部 config 重構改變：

```text
CLI option names
aliases
defaults
boolean semantics
task semantics
```

尤其目前 `ClassfierOptionParser()` 有一個既有行為：

```python
if args.train is False and args.test is False:
    args.test = True
```

這是 observable behavior，重構時必須先由 characterization test 鎖住。

---

# 14. Stage Handoff Contracts

Stage 之間目前主要透過 filesystem artifact 溝通。

這在 batch / ML pipeline 中本身沒有問題，不要求改成 in-memory object pipeline。

現有重要 contract 包括：

```text
train.tsv
dev.tsv
test.tsv
dataset_total_with_filename_FixedTest.sql3
test.sql3
DFPreambleCols_df_ALL*
SDSMS.*
```

以及工作目錄狀態 suffix，例如：

```text
_is_running_DataConverter
_rdy_for_RunClassfier
```

這些目前已在 `.codex/contracts.md` 與 `.codex/architecture.md` 被識別為 compatibility boundary。

重構後可以增加 internal typed result，例如：

```python
DatasetStageResult(...)
ClassifierStageResult(...)
```

但它們只是程式內部 description。

真正 filesystem artifact contract 第一輪不得因此被取代或改名。

---

# 15. Filesystem Boundary

目前 directory rename、move、backup、delete、mkdir、walk、chown 分散於 root 與 utilities。

本 Design 要求逐步建立明確 filesystem boundary，例如：

```text
FileSystem
WorkPoolManager
ArtifactBackup
OwnershipManager
```

但第一輪 adapter 必須繼續執行相同 filesystem semantics。

特別是工作池操作具有資料破壞風險；現有 known issue 也明確指出 `TCFMain.py` 的 backup/move/cleanup 不適合直接使用真實工作池作 smoke test。

因此 filesystem refactor 必須優先使用 isolated temporary fixture。

---

# 16. Error Handling

現有 `run_stage_command()` 已比單純 `os.system()` 更進一步，會讀取 subprocess return code，非零時 raise `RuntimeError`，並停止後續 stage。

此行為屬於重要 compatibility improvement，後續不可弱化。

目標模型為：

```text
stage failure
    ↓
structured stage exception
    ↓
orchestrator aborts following dependent stages
    ↓
existing user-visible logging retained
```

第一輪不要求建立複雜 retry framework。

尤其 filesystem retry、model retry 與 pipeline retry 不應混成同一政策。

---

# 17. Test Strategy

這次重構採：

```text
Characterize first
→ refactor
→ prove parity
```

而不是：

```text
refactor everything
→ run it once
→ hope outputs look correct
```

測試應分為四個層次。

| Layer                          | Purpose                                                      |
| ------------------------------ | ------------------------------------------------------------ |
| CLI contract tests             | 驗證 option、alias、default、train/test normalization 不變          |
| Command characterization tests | 驗證每個 stage 接相同 args 時建立相同 command semantics                  |
| Stage boundary tests           | 使用 fake runner / temporary filesystem 驗證 stage orchestration |
| Dataset integration fixture    | 保留既有 DatasetConverter small fixture，驗證實際 source→split→TSV 行為 |

目前 `.codex/workflows.md` 已記錄：

```bash
python -m unittest discover -s tests
```

以及：

```bash
python -m unittest tests.test_dataconverter_fixture_integration
```

作為目前可安全執行的輕量與 DatasetConverter integration 驗證。

完整模型 pipeline 則仍需要實際模型與工作池，因此不應成為每個小型 refactor PR 的唯一驗證手段。

---

# 18. Characterization Targets Before Refactoring

以下行為在修改前應被固定成測試或明確 observation：

| Behavior                                  | Why it matters                               |
| ----------------------------------------- | -------------------------------------------- |
| CLI aliases/defaults                      | 外部 script compatibility                      |
| `train=False`, `test=False` normalization | Existing parser behavior                     |
| `convert_to_args_str()` output semantics  | 所有 subprocess stage 共用                       |
| Canonical stage ordering                  | Pipeline behavior                            |
| Stage abort on non-zero return code       | Error contract                               |
| Dataset handoff naming                    | Stage interoperability                       |
| WeiTech workID selection/movement         | Production workflow compatibility            |
| `FinalOfferedOutputFNrePatList` behavior  | Delivery artifact compatibility              |
| `TestResultVis()` double invocation       | 必須先判定是 intentional behavior 還是 legacy defect |
| Backup/Clean conditions                   | 避免資料遺失                                       |

其中 `TestResultVis()` 現在會先執行 base command，再加入 WeiTech options 後執行第二次。

Design v1 不判定這是 bug。

在 characterization 前不得因「看起來重複」直接移除。

---

# 19. Internal Dependency Rules

重構後遵守以下 dependency model：

```text
TCFMain / Orchestrator
        ↓
Stage API
        ↓
Stage implementation
        ↓
Shared boundaries / adapters
```

禁止形成：

```text
Stage 1 → Stage 2 implementation
Stage 2 → Stage 3 implementation
Stage 3 → Stage 1 internals
```

Shared module 也不得反向 import specific stage implementation。

換言之：

```text
shared → stage
```

應被視為 dependency inversion violation。

---

# 20. Utility Decomposition Policy

本 Design 不要求建立一個新的巨大：

```text
shared/utils.py
```

來取代現有巨大 utilities。

新 boundary 應按責任命名，例如：

```text
execution
filesystem
workpool
configuration
logging
timing
```

只有 truly generic、pure、dependency-light function 才適合稱為 utility。

這也是避免幾年後重新形成第二個 `TCF_utils.py` 的主要規則。

---

# 21. Repository Layout Policy

第一輪不把 directory reorganization 當成功條件。

可能的長期內部結構可以是：

```text
text_category_profiler/
    pipeline/
    stages/
    execution/
    filesystem/
    config/
```

也可以繼續讓：

```text
DatasetConverter/
BertScript/
```

成為主要 feature/stage package。

真正成功條件不是目錄長得像哪一種 textbook architecture，而是：

```text
responsibility is clear
dependency direction is controlled
side effects are isolated
behavior can be tested
```

因此實體目錄 relocation 屬於後續可選改善，而非 Design v1 必做事項。

---

# 22. Migration Strategy

重構採 strangler-style incremental migration。

```text
Existing implementation
        ↓
Characterization coverage
        ↓
Introduce boundary
        ↓
Move one responsibility behind boundary
        ↓
Run parity tests
        ↓
Keep legacy entrypoint
        ↓
Next responsibility
```

同一個 PR 不應同時：

```text
大量搬檔
+ CLI redesign
+ ML library upgrade
+ stage logic rewrite
+ output schema change
```

這會讓 regression 無法定位。

---

# 23. Recommended Architectural Migration Order

Architecture Design v1 建議的優先順序為：

```text
Safety / characterization
        ↓
Configuration boundary
        ↓
Process execution boundary
        ↓
TCFMain orchestration extraction
        ↓
WorkPool / filesystem lifecycle boundary
        ↓
Classifier stage internal cleanup
        ↓
Result combination cleanup
        ↓
Visualization cleanup
        ↓
Repository/package hygiene
```

這只是 architectural sequencing。

具體要修改哪些檔案、每個 task 如何 RED/GREEN、各 PR 範圍與驗證命令，留給 Implementation Plan v1 定義。

---

# 24. Explicit Non-Goals

Design v1 不包含 ML model 更換、TensorFlow/PyTorch framework migration、tokenization behavior 改寫、分類演算法調整、taxonomy redesign、輸出 schema redesign、CLI redesign、HTTP/API 化、LangGraph 化、全面 async 化、全部 package relocation。

這些工作如果未來需要，應在 architecture refactor 穩定後以獨立 Design 處理。

---

# 25. Documentation Consistency

目前 `.codex/workflows.md` 已有 canonical lightweight smoke test：

```bash
python -m unittest discover -s tests
```

但 `.codex/known_issues.md` 的 `KI-001` 仍描述「根目錄沒有已確認的 test/smoke command」。

兩份 current-state 文件因此存在輕微落差。

這不是本次 Architecture blocker，但 Implementation Plan 應把 current-state documentation reconciliation 納入 housekeeping task。

---

# 26. Acceptance Criteria for the Refactoring Program

當整體 Architecture Refactoring 完成時，至少應滿足以下狀態：

| Area             | Acceptance condition                                                                |
| ---------------- | ----------------------------------------------------------------------------------- |
| CLI              | 既有 canonical commands 仍可接受原有 arguments                                              |
| Pipeline         | canonical stage order與 conditional behavior 維持                                      |
| Files            | 既有 handoff/output names 與主要 directory conventions 維持                                |
| Orchestration    | `TCFMain.py` 主要負責組裝與流程控制，不再承擔大量 implementation detail                               |
| Config           | import configuration module 不應任意產生不可控制的 runtime side effect                         |
| Execution        | subprocess invocation 由可替換、可測試 boundary 控制                                          |
| Filesystem       | destructive work-pool actions 可在 isolated adapter/fixture 中驗證                       |
| Stage boundary   | 各 stage 不直接控制下一 stage implementation                                                |
| Tests            | CLI、command assembly、stage sequencing、error propagation 有 characterization coverage |
| DatasetConverter | 現有已重構 architecture 不因整體 modernization 被倒退或重新打散                                      |
| Compatibility    | 無經批准的 observable behavior change                                                    |

---

# 27. Primary Architectural Decision

Architecture Refactoring Design v1 最核心的決策為：

> `text-category-profiler` 將保留既有四階段 workflow 作為主要 navigational 與 conceptual architecture，而不是改成純 layer-first repository。

同時：

> configuration、process execution、filesystem/work-pool lifecycle、logging/timing 等 cross-cutting concerns 將逐步由各 stage 與 root script 抽出，形成明確且可測試的 shared boundaries。

因此本次重構不是：

```text
舊四階段架構
        ↓
推翻
        ↓
新企業式分層架構
```

而是：

```text
既有四階段
        ↓
保留
        ↓
切乾淨 stage boundary
        ↓
抽離 cross-cutting infrastructure
        ↓
建立 characterization tests
        ↓
逐步替換 legacy internals
```

這同時保留原系統多年累積的 operational behavior，以及未來持續維護與測試所需要的架構清晰度。

---

## Design v1 Result

**Recommendation: APPROVE FOR IMPLEMENTATION PLANNING**

目前從 hosted source 檢查未看到需要推翻「四階段 + behavior-preserving incremental refactor」方向的 architectural blocker。

下一 gate 應為：

```text
Architecture Refactoring Design v1
                ↓
Implementation Plan v1
                ↓
Codex Prompt / Execution Contract
                ↓
Implementation PR(s)
                ↓
Hosted source Implementation Review
```
