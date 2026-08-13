# DatasetConverter 漸進式重構指引

本文件提供 `DatasetConverter` 的**逐步重構路線**。目標不是一次重寫，而是在每個階段都維持目前 CLI、資料集檔名、工作目錄 handoff 與資料切分語意，並以小型、可回復、可驗證的變更逐漸降低耦合。

## 1. 現況與重構目標

目前 canonical 入口是 `DatasetConverter/DataConverter.py`。該檔同時負責：

- CLI 與工作目錄初始化；
- taxonomy／label 載入；
- 一般來源、fixed-test、CZJ corpus 與可選 ES 資料的收集；
- 樣本清整、去重、切分與 train-only augmentation；
- TSV、SQLite、Excel／視覺化等輸出；
- multiprocessing、log、計時與下一 stage handoff。

部分純資料集邏輯已抽到 `dataset_split.py`，row schema 判斷已抽到 `sample_schema.py`，這兩個模組可作為後續抽取的範例。重構完成後，希望達到以下可觀察結果：

1. `DataConverter.py` 只負責 composition root 與 stage orchestration。
2. 核心資料轉換可用記憶體內 fixture 測試，不需模型、工作池、multiprocessing 或外部服務。
3. 檔案系統、SQLite、ES 與 process pool 都位於明確的 adapter 邊界。
4. 設定有單一、具型別的內部表示，不再以大型 mutable `dict` 在函式間傳遞。
5. 每一階段失敗時都有明確錯誤、非零退出狀態與足以定位問題的摘要 log。

## 2. 必須維持的不變量

重構期間先保留行為；若要改變下列契約，應另開變更並同步 `.codex/contracts.md`、`.codex/architecture.md` 與呼叫端：

- `TCFMain.py` 組出的 DataConverter command 必須仍可由共用 `ClassfierOptionParser()` 解析。
- 工作目錄狀態仍使用 `_is_running_DataConverter` 與 `_rdy_for_RunClassfier` handoff。
- classifier dataset 仍以 `train.tsv`、`dev.tsv`、`test.tsv` 及其 SQLite 產物交付。
- 來源資料先依 `OutLabel`／`text` 去重，再切分；同一唯一樣本不得跨 split 出現。
- split 容量允許時，train 至少包含每個 label 一筆；augmentation 只能改動 train，不得污染 validation/test。
- test mode 沒有任何 test、fixed-test 或 ES 樣本時仍應失敗；非 test mode 則以所有可用 split 的總數判斷是否為零樣本。
- taxonomy、原始文本、模型、工作池與外部服務都是信任邊界；測試不得讀寫真實工作池或連線正式 ES／資料庫。

## 3. 執行原則

每一步都應是一個可獨立 review 的小 PR，遵循以下順序：

1. 先為現行行為加 characterization test。
2. 只移動一項責任，不同時改演算法與介面。
3. 保留薄相容層，讓既有 import 與 CLI 呼叫先不受影響。
4. 執行最接近變更範圍的測試，再執行 repository 輕量測試。
5. 比較產物 schema、row count、label count 與 split overlap，而不是只比較 console 文字。
6. 確認 `git diff --check`，並人工排除資料、模型、SQLite、log 或其他 generated artifact。

禁止以 catch-all exception、silent fallback、hard-coded output 或 mock success 讓流程表面通過。對舊行為不確定時，先固定 fixture 與預期結果，再決定是否保留。

## 4. 建議的目標邊界

先依責任建立小而具體的模組；不要一開始建立抽象 framework：

```text
DatasetConverter/
├── DataConverter.py          # CLI composition root；保留直接執行相容性
├── config.py                 # argparse namespace -> immutable internal config
├── taxonomy.py               # topic tree 與 label validation
├── source_collection.py      # 建立來源描述，不執行核心轉換
├── sample_pipeline.py        # 純 sample/DataFrame transformation
├── dataset_split.py          # 現有 dedup/split/train augmentation 規則
├── sample_schema.py          # 現有 row schema 規則
├── outputs.py                # TSV/SQLite 與 record artifact 寫出
└── stage.py                  # orchestration、結果摘要與 handoff
```

名稱可隨實作微調；判斷是否值得新增模組的標準是「責任與依賴方向清楚」，不是追求檔案數量。`sampleHandler.py`、`EXTConverter/` 與共用 `text_category_profiler/` utilities 應先由 adapter 包住，再評估是否遷移，避免首輪重構擴散到整個 repository。

依賴方向建議固定為：

```text
DataConverter.py -> stage/config -> domain services -> ports
                                             ^          |
                                             └-- adapters
```

核心轉換不得反向 import CLI、全域 logger、工作池常數或 process pool。

## 5. 分階段路線

### Phase 0：建立安全基線

**目的**：在移動程式前，先把容易被誤改的行為轉成自動檢查。

工作項目：

1. 建立最小文字 fixture，至少涵蓋兩個 labels、重複文本、fixed-test 與空來源。
2. 為 `setArguments()` 與 `loadLabels()` 的可觀察輸出建立 characterization tests；不要 import 執行完整 stage。
3. 為 `DatasetGenerator.run()` 建立 isolated SQLite／temporary-directory integration test，記錄：
   - split row counts；
   - 各 split label sets；
   - `(OutLabel, text)` 是否跨 split 重複；
   - train augmentation 前後筆數；
   - 實際產生的檔名與必要 columns。
4. 對 zero-sample、test-mode-without-test-samples 與 taxonomy label mismatch 建立失敗案例。

**完成閘門**：fixture 不依賴網路、模型或真實工作池；相同 seed 下結果可重現；現有 `tests/test_dataset_split.py` 保持通過。

### Phase 1：讓入口無 import-time 副作用

**目的**：讓模組可安全 import，為後續 unit test 與 dependency injection 鋪路。

工作項目：

1. 新增 `main(argv=None) -> int`，將 `if __name__ == "__main__"` 內流程移入其中。
2. 僅在 `__main__` 使用 `raise SystemExit(main())`。
3. 將 `os.chdir()`、process title、目錄建立與 logger 初始化移到明確的 bootstrap function。
4. 移除依賴 global `args`、`MPLOGGER`、`MPLOGGER_TCFMain`、`exeTimeDict` 的內部函式參照，改為參數傳入。
5. 外部服務與視覺化 import 延遲到對應 adapter 真正啟用時，但不得用 `try/except` 包住 import。

**完成閘門**：`python -c "import DatasetConverter.DataConverter"` 不建立目錄、不變更 cwd、不啟動 process、不讀取資料；CLI 的成功與失敗退出狀態有測試。

### Phase 2：收斂設定與驗證

**目的**：停止讓 argparse namespace、module constants 與 mutable `DCkwargs` 同時成為設定來源。

工作項目：

1. 建立 immutable dataclasses，例如 `ConverterConfig`、`SourceConfig`、`SplitConfig` 與 `OutputConfig`。
2. 寫一個 mapping function 將 argparse namespace 與現有 defaults 轉成內部 config。
3. 集中驗證 ratio、process count、必要路徑、test source、topic tree files 與互斥模式。
4. 將空 list／dict default 改為 `None` 或 `default_factory`，避免跨 instance 共用 mutable state。
5. 在 stage 開始時只輸出非敏感的 normalized config 摘要；不得記錄 token、credential 或原始文本。

**完成閘門**：無效設定在任何檔案寫入前失敗；相同輸入只產生一種 normalized config；既有 CLI option 名稱與預設行為不變。

### Phase 3：拆分 taxonomy 與來源收集

**目的**：把「要讀哪些來源」與「如何把來源轉成樣本」分離。

工作項目：

1. 把 `loadLabels()` 拆為 taxonomy loader 與 validator，回傳具名結果，而非修改 `DCkwargs`。
2. 把 `DataConvertJobGenerater.BuildFileList()` 的 glob／path discovery 抽成純 discovery function；排序結果以確保可重現。
3. 以 `SourceSpec` 描述 regular、fixed-test、CZJ corpus 與 ES source role。
4. 讓來源 adapter 統一回傳 sample rows 或 iterator；核心 pipeline 不判斷來源路徑形式。
5. 保留 `sourceRole` metadata，使 fixed-test 不會因 regular source 為空而被略過。

**完成閘門**：各來源可獨立用 temporary fixture 測試；來源為空有明確、依 mode 區分的結果；不需啟動 multiprocessing 即可驗證 discovery 與 routing。

### Phase 4：建立純 sample transformation pipeline

**目的**：讓清整規則可以逐項測試，並避免 DataFrame 操作與 I/O 交錯。

工作項目：

1. 將 `BuildSamplesDfFromPaths()` 拆成 discover、read、normalize、validate、deduplicate、assemble 等步驟。
2. 將 `GetDataSRC()`、`TextNormalize()` 與 multi-label 計數邏輯改成不讀 global state 的純函式。
3. 每個步驟定義輸入／輸出 columns；schema mismatch 應指出缺少的 column 與來源階段。
4. 保留 provenance columns（例如 `Src`、`file`），避免優化時失去追溯能力。
5. 只有 profiling 證明必要時才加入 chunk／iterator；不得先為理論效能引入複雜抽象。

**完成閘門**：同一 fixture 的 normalized rows、去重鍵與 provenance 與基線一致；純 pipeline 測試不寫檔、不需要 process pool。

### Phase 5：縮小 DatasetGenerator

**目的**：讓 split policy、外部 test sources 與 artifact persistence 各自獨立。

工作項目：

1. 保留 `dataset_split.py` 為 split policy 的單一來源；不要在 `DatasetGenerator` 內重複計算 bounds。
2. 先建立 `DatasetBundle(train, validation, test, fixed_test, elasticsearch)`，再交給 output layer。
3. 將 augmentation seed／random generator 顯式傳入，確保測試與重跑可重現。
4. 將 fixed-test／ES collection 從 `run()` 拆成 adapters，並以一致的 schema 合併或分開輸出。
5. 讓 `run()` 回傳具名 `ConversionResult`，包含 counts、artifacts 與 warnings，取代鬆散 `dict`。

**完成閘門**：所有唯一來源 row 恰好分配一次；train label coverage 規則保持；validation/test 不含 augmented rows；counts 與實際 artifacts 一致。

### Phase 6：隔離輸出與 handoff 副作用

**目的**：集中控制檔案、SQLite 與工作目錄狀態變更。

工作項目：

1. 建立 output manifest，明列每個 artifact 的 path、format、schema、row count 與 producer。
2. 把 `dfOutputer`、SQLite index、record files 與視覺化 jobs 包在 output adapters。
3. 先寫入同 filesystem 的 temporary/staging path，驗證必要產物後再做 atomic rename 或明確 handoff。
4. 將 WeiTech work-pool copy/move/rmtree 邏輯集中到 workspace adapter；預設拒絕刪除不在預期 root 下的路徑。
5. `TaskConnector` 只在所有必要 artifacts 驗證成功後執行。

**完成閘門**：output adapter 可在 temporary directory 完整測試；中途失敗不會宣告 ready；不得覆寫或刪除 fixture root 以外資料。

### Phase 7：收斂 multiprocessing 與錯誤模型

**目的**：讓並行化是可替換的執行策略，而不是 domain logic 的必要條件。

工作項目：

1. 先提供 deterministic sequential executor 作為測試與小資料預設路徑。
2. 把 `multicoreJob` 注入 orchestration；job payload 必須可序列化，worker 不依賴 parent globals。
3. 統一 domain error、input error、external-service error 與 artifact error；在 CLI 邊界轉成訊息與 exit code。
4. worker exception 必須回傳主程序並使 stage 失敗，不得只寫 log 後繼續 handoff。
5. 計時與 log 使用 stage/result metadata，不在純函式中直接 print。

**完成閘門**：sequential 與 multiprocessing 對相同 fixture 產生等價資料；worker failure 的整體退出狀態非零；Windows spawn 路徑不重複執行 bootstrap。

### Phase 8：以量測驅動效能優化

**目的**：功能邊界穩定後，再針對已證實瓶頸調整。

工作項目：

1. 固定小／中型 synthetic fixture，記錄 wall time、peak RSS、輸入／輸出 rows 與 artifact size。
2. 分別量測 file discovery、sample reading、DataFrame normalization、dedup、SQLite/TSV output 與 process startup。
3. 優先消除重複 scan、重複 DataFrame copy、無 index 查詢與過細 multiprocessing jobs。
4. 大型資料才評估 chunked I/O、batched SQLite writes 或 iterator pipeline。
5. 每項效能 PR 同時設 correctness gate；不得只以耗時下降判定成功。

**完成閘門**：benchmark 方法與 fixture 可重現；輸出契約與 baseline 一致；PR 清楚列出改善前後數據及環境，不宣稱未量測的效能提升。

### Phase 9：清理相容層與文件

**目的**：在所有 caller 遷移完成後移除 dead code，而不是提早刪除。

工作項目：

1. 以 `rg` 確認舊 helper、compatibility import 與 global 未再被引用。
2. 將確認不用的 debug helpers（例如會刻意 `raise Exception` 的人工工具）移到明確 maintenance script 或刪除。
3. 判定 `old_*.py`、`*_test.py` 腳本與 duplicate converter 是否仍有使用者；無證據時先標記，不直接猜測用途。
4. 更新 `.codex/architecture.md`、`.codex/contracts.md` 與 `.codex/workflows.md` 的 current state。
5. 若新增子模組專屬命令或風險，再考慮建立精簡的 nested `AGENTS.md`；不要複製 root 規則。

**完成閘門**：canonical path 唯一且有文件；無未使用相容層；所有現行入口與 handoff consumer 通過契約測試。

## 6. 每個 PR 的建議模板

### Scope

- 本次只抽取或修改哪一項責任？
- 哪些相鄰問題明確不在本次範圍？

### Preserved contracts

- CLI options／defaults。
- split、dedup、augmentation 規則。
- output filenames、columns、SQLite tables/indexes。
- workspace state transition 與 handoff 條件。

### Verification

- 新增或更新的 characterization／unit／integration tests。
- `python -m unittest discover -s tests`
- 相關 Python 檔案的 `python -m py_compile ...`
- `git diff --check`
- 若無可用隔離 fixture，明確註明未執行完整 DataConverter 的原因與影響。

### Rollback

- 是否仍保留舊入口或 adapter？
- 回復此 PR 是否會影響已產生的 dataset／workspace state？

## 7. Review checklist

- [ ] 沒有改變 canonical CLI option 或 handoff filename。
- [ ] 沒有新增 import-time filesystem／network／process side effect。
- [ ] 核心函式不讀寫 globals，也不直接依賴 logger 或 argparse namespace。
- [ ] mutable defaults 已避免。
- [ ] 來源角色與 provenance 未遺失。
- [ ] 去重發生於 split 之前。
- [ ] augmentation 僅作用於 train。
- [ ] validation/test 與 train 無 `(OutLabel, text)` leakage。
- [ ] zero-sample 與 test-mode failure 邏輯仍有測試。
- [ ] output counts 與實際 row counts 一致。
- [ ] worker／adapter failure 會阻止 ready handoff。
- [ ] 測試只使用 temporary directory／fixture，不觸碰真實工作池或外部服務。
- [ ] diff 不含 dataset、SQLite、log、模型、credential 或其他產物。

## 8. 建議起手順序

若要立即開始實作，建議前三個 PR 嚴格控制在：

1. **PR 1：Characterization fixtures** — 只補 split、zero-sample、fixed-test 與 artifact contract 測試。
2. **PR 2：Side-effect-free entry point** — 新增 `main(argv=None)` 與 bootstrap boundary，不改資料演算法。
3. **PR 3：Typed config** — 將 argparse／`DCkwargs` 正規化成 immutable config，保留舊函式薄 wrapper。

前三步完成後再拆 source 與 pipeline，能大幅降低「邊搬程式、邊猜現行行為」造成的回歸風險。

## 9. 執行進度

### 2026-08-12 — Phase 1 入口邊界（進行中）

本次完成：

- `DataConverter.py` 已提供 `main(argv=None) -> int`，直接執行時只由
  `raise SystemExit(main())` 進入流程；原有轉換演算法、CLI option、輸出檔名與
  handoff suffix 均未改動。
- cwd 調整與 process title 設定已移入 `bootstrap_runtime()`，import module 時不再
  直接執行 `os.chdir()`；`setproctitle` 也延遲到 bootstrap 才匯入。
- 共用 `ClassfierOptionParser(argv=None)` 可接收明確 argument list，既有無參數
  caller 仍讀取 `sys.argv`，讓後續 CLI exit-code 測試不必修改 process globals。
- 新增 AST regression test，固定 module scope 不改 cwd，以及 `main`／
  `SystemExit` 的入口形狀。
- 後續 Windows test-only 執行揭露 `DataConvertJobGenerater` 仍讀取舊 module-global
  `args`，造成 tokenizer model directory 解析時出現 `NameError`；現已將 CLI namespace
  由 `main()` 經 `BuildSamplesDfFromPaths()`／`DatasetGenerator` 顯式傳入 reader job
  generator，並新增禁止該 class 讀取 global `args` 的 regression test。這是 Phase 1
  「移除內部 global args」的第一個 runtime 驗證修正。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** 此容器缺少 `psutil` 等 optional/runtime
   dependencies，實際執行 `python -c "import DatasetConverter.DataConverter"` 仍會在
   module-scope dependency import 失敗；下一批應依 adapter 使用點逐一延遲外部服務、
   視覺化與重型 runtime imports，不得以 `try/except` 吞掉 import error。
2. `setArguments()` 仍建立目錄、logger 並更新 globals；應把這些動作移入具名
   bootstrap context，讓 argument normalization 本身可單獨測試。
3. 主流程仍讀寫 `MPLOGGER`、`MPLOGGER_TCFMain`、`exeTimeDict` globals；完成 Phase 1
   前需改為顯式參數或 context，但應分批進行，避免同時重寫 orchestration。
4. Phase 0 目前只有 split 與 source-role 等局部測試；`DatasetGenerator.run()` 的
   temporary-directory artifact contract、taxonomy mismatch 與完整 zero-sample
   integration fixture 尚待補齊。

### 2026-08-12 — Phase 3 來源探索邊界（進行中）

本次完成：

- 新增 `source_collection.py`，將 regular／CZJ 來源共用的檔案探索結果過濾與排序
  從 `DataConvertJobGenerater.BuildFileList()` 抽出；現有 `OSWALK` 以參數注入，未改變
  既有 extension 與 filename regex 契約。
- 探索結果現在於去除路徑包含 `UnTagged`／`UnSpec` 的項目後統一排序，避免 filesystem
  enumeration order 使相同輸入在不同平台產生不同 reader job 順序。
- 新增不需 pandas、模型、multiprocessing 或真實工作池的 isolated unit tests，固定
  walker 呼叫契約、排除規則、穩定排序，以及多次呼叫不共用結果。

尚未完成／下次優先事項：

1. **Phase 3 completion gate 尚未達成。** FixedTest 探索仍直接寫在
   `DatasetGenerator.run()`，ES 與 CZJ corpus title routing 仍由 job generator 處理；
   下一批應先以 `SourceSpec` 固定 source role 與 discovery policy，再逐一遷移。
2. `BuildFileList()` 仍負責 hash-based duplicate article removal 與 log／timing；本批刻意
   只抽出 discovery，避免同時改動 dedup 演算法。後續應將 discovery result 與 content
   dedup 分成兩個可測步驟。
3. 本批只驗證 injected walker 的契約，未執行完整 DataConverter；下節已補第一個隔離
   integration slice，但完整 legacy CLI 仍需要 runtime dependencies 與更多 fixture cases。

### 2026-08-12 — Phase 0 小型隔離 fixture（部分完成）

本次完成：

- 新增 `tests/fixtures/dataconverter_small/`，使用三個 UTF-8 小型文字檔涵蓋兩個 labels；
  label 直接沿用 production source path 的 `#T#[label]` 契約，不需要模型或外部服務。
- `test_dataconverter_fixture_integration.py` 會以兩個 process workers 讀取 fixture，使用
  production `dataset_split` plan 產生 non-overlapping train／dev／test bounds，再將三個
  TSV 寫入 `TemporaryDirectory` 並驗證檔名、columns、row count、labels 與無重複 rows。
- 新增窄範圍、只依賴 Python standard library 的 fixture reader 與 TSV contract writer；
  它們是 dependency-free contract probe，不取代 production pandas／SQLite adapters。
- 此測試已可在目前 Codex 容器執行，因此「尚無經確認可安全使用的完整隔離 fixture」
  已縮小為「已有 source → worker → split → TSV 的安全 fixture，但完整 legacy CLI 與
  pandas／SQLite adapter 尚未涵蓋」。

尚未完成／下次優先事項：

1. Phase 0 的 duplicate、fixed-test、empty source、taxonomy mismatch 與 SQLite artifact
   cases 尚待加入；目前 fixture 是第一個安全 integration slice，不應描述為完整 CLI E2E。
2. `python DatasetConverter/DataConverter.py ...` 仍需要 pandas、psutil、Plotly 等 module-scope
   dependencies；Phase 1 應繼續移除 import-time 重型依賴，之後把相同 fixture 接到正式
   stage/bootstrap boundary。

### 2026-08-12 — Phase 3 SourceSpec 與 FixedTest discovery（進行中）

本次完成：

- `source_collection.py` 新增 immutable `SourceSpec` 與 `SourceRole`，讓 regular、fixed-test
  與 CZJ corpus 的來源用途、roots、extensions、filename pattern 與排除規則可由資料描述，
  不再只能由呼叫位置或 log 字串推測。
- regular／CZJ 的 `BuildFileList()` 與 `DatasetGenerator.run()` 的 FixedTest 探索已共用
  `discover_source_spec()`；舊 `discover_source_files()` 保留為 regular source 薄相容層。
- 保留既有 discovery 契約：regular／CZJ 仍排除路徑中的 `UnTagged`／`UnSpec` 並傳入
  filename regex；FixedTest 不傳 regex、也不套用該排除規則。各角色結果皆穩定排序。
- isolated tests 固定 spec immutability、walker keyword、角色資訊、FixedTest policy 與空 roots
  不呼叫 walker；不需 import `DataConverter.py`、pandas 或啟動 multiprocessing。

尚未完成／下次優先事項：

1. **Phase 3 completion gate 尚未達成。** `SourceSpec.role` 目前主要用於 routing metadata；
   `BuildSamplesDfFromPaths()` 仍接收未具型別的 `sourceRole` 字串，後續應以薄 wrapper 將 role
   一路傳到 reader job 與結果摘要，避免重複推導。
2. content hash dedup 仍在 `DataConvertJobGenerater.BuildFileList()`，應抽成接收 discovery
   result 的獨立步驟並以小型重複檔案 fixture 固定行為。
3. ES source 沒有 filesystem roots，尚未建立相對應的 source adapter/spec；不要為了統一形式
   把 ES 偽裝成檔案來源，應先定義一致的 sample-row adapter contract。
4. Phase 0 的 duplicate、FixedTest row conversion、taxonomy mismatch 與 SQLite artifact cases
   仍待補齊；本批只涵蓋 discovery/routing，不代表完整 legacy CLI E2E 已可執行。

### 2026-08-12 — Phase 3 content hash 去重邊界（進行中）

本次完成：

- 將 content hash worker 結果的合併與「同 hash 保留最後一個 path」規則抽到
  `source_collection.select_unique_content_paths()`；`DataConvertJobGenerater` 仍負責 process
  worker 與檔案 hash adapter，因此沒有改變 hash 演算法、前 100 MB 上限或並行策略。
- `BuildFileList()` 現在依序執行 discovery → hash adapter → pure selection，來源探索與內容
  去重不再混成同一段轉換程式；舊有 worker batch 合併順序及衝突規則維持不變。
- isolated tests 固定跨 worker batch duplicate、唯一檔案順序與空結果，不需讀檔、啟動
  multiprocessing 或 import `DataConverter.py`。

尚未完成／下次優先事項：

1. **Phase 3 completion gate 尚未達成。** hash 計算、process executor、摘要 log 與
   FixedTest bound sampling 仍在 `DataConvertJobGenerater`；下一批可先把 hash job 建立與執行
   包成 injected adapter，再用 temporary duplicate files 驗證完整 discovery → hash → selection。
2. Phase 0 的 duplicate fixture 現在只固定 pure selection 契約，尚未涵蓋 production
   `FileHashDictBuilder` 的前 100 MB 讀取或 process failure propagation。
3. `SourceSpec.role` 到 reader/result 的 typed routing、ES row adapter、FixedTest row conversion、
   taxonomy mismatch 與 SQLite artifact contract 仍待完成。

### 2026-08-12 — Phase 4 reader result 組裝邊界（進行中）

本次完成：

- 新增 `sample_pipeline.py`，以 immutable `CollectedSamples` 描述 reader jobs 回傳的 sample
  rows 與 multi-label counters，先將 `BuildSamplesDfFromPaths()` 中不需要 DataFrame 的結果組裝
  抽成純函式 `collect_reader_results()`。
- 保留既有 worker result 順序與一層 rows flatten 契約；空 job results 會得到明確的空 rows／
  counters，不需以 `zip(*)` 分支處理。
- reader adapter 若回傳缺少 `(rows, multi_label_count)` 任一成員，或 rows 不是 list／tuple，
  現在會在 DataFrame 與輸出副作用之前指出失敗的 result index，而非產生難以定位的 unpack
  或 flatten error。
- isolated tests 固定多 worker 排序、空結果與 malformed adapter result；不需 pandas、process
  pool、模型、外部服務或 filesystem。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `SampleReader` 仍同時負責來源格式讀取、文字切片與
   normalize；下一批應先記錄各 reader role 的 row schema，再逐步把 normalize／validate 抽成
   不讀 global state 的純轉換。
2. `GetDataSRC()` 仍以 DataFrame chunk 執行且吞掉所有 metadata 解析錯誤；應先用 fixture 固定
   Books、一般 `#T#` path 與無法解析 path 的契約，再改成可觀察的 row transformation，不能直接
   移除 fallback 而破壞 legacy sources。
3. 本批不變更 reader jobs、multiprocessing 策略、TSV／SQLite schema、split 或 augmentation；
   完整 legacy CLI 仍受 Phase 1 的 module-scope runtime dependencies 限制。

### 2026-08-12 — Phase 4 multi-label 計數邊界（進行中）

本次完成：

- 將 `MultiLabCt()` 的 multi-label worker counter 彙總規則抽到
  `sample_pipeline.aggregate_multi_label_counts()`；`DataConverter.py` 保留原函式作為薄相容層，
  現有 caller、回傳 dictionary 與「忽略無 label set 結果」的契約不變。
- 純函式將 label set 排序後作為 key，確保不同 worker 回傳同一組 labels 時穩定合併；並在
  malformed counter 缺少 labels 或 count 時指出 result index，避免無法定位的 unpack error。
- isolated tests 固定跨 worker 累加、label 順序正規化、`None` 相容行為與 malformed contract；
  不需 import `DataConverter.py`、pandas、process pool、模型、外部服務或 filesystem。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `GetDataSRC()` 仍以 DataFrame chunk 執行且吞掉所有
   metadata 解析錯誤；下一批仍應先固定 Books、一般 `#T#` path 與無法解析 path 的既有契約，
   再抽出具名結果的純 row transformation。
2. `SampleReader` 的來源格式讀取、文字切片與 normalize 仍耦合；應沿 reader role 逐一記錄
   input/output columns 與 provenance，再移動單一責任，避免同時改變 sample schema。
3. 本批不變更 multi-label 的 reader payload、TSV／SQLite schema、split、augmentation 或 handoff；
   完整 legacy CLI 仍需 runtime dependencies 與工作池 fixture 才能驗證。

### 2026-08-12 — Phase 4 source metadata 組裝邊界（進行中）

本次完成：

- 新增 immutable `SourceMetadata` 與純函式 `collect_source_metadata()`，將 provenance path resolver
  的逐列呼叫、結果順序及 `(SrcType, Src)` shape validation 從 pandas adapter 抽離；resolver 以參數
  注入，因此純 pipeline 測試不需載入 pandas 或 legacy stage dependencies。
- `GetDataSRC()` 現在只負責從 DataFrame 取得 `file`／`InLabel`、呼叫 pipeline boundary，並寫回
  `SrcType`／`Src` columns；既有 `getSrcFromFileName()` 仍是 path policy adapter，Books 與一般來源
  的判定演算法未在本批重寫。
- 移除 `GetDataSRC()` 原本吞掉所有例外的 bare `except`。未解析但合法的 path 仍保留既有
  `(None, None)` metadata；resolver exception 或 malformed result 現在會阻止後續輸出／ready handoff，
  malformed result 會帶 row index 與 path。
- tests 固定 Books／一般來源的 injected routing、無法解析 path 的 `None` metadata、malformed result
  診斷，以及 `GetDataSRC()` 不再以 `try` 靜默跳過整批 metadata。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** 本容器未安裝 pandas，無法直接 import legacy
   `DataConverter_utils.getSrcFromFileName()`；Books 與一般 path 的 production parser 結果仍需在完整
   runtime 以 temporary fixture characterization test 固定，本批只固定 injected adapter contract。
2. `getSrcFromFileName()` 所在 module 同時 import pandas、SQLite 與其他 output dependencies；下一批可
   將 path-only policy 移入 dependency-free module，再讓舊位置保留薄相容 import，避免 source metadata
   解析被不相關 runtime dependency 阻擋。
3. `SampleReader` 的來源格式讀取、文字切片與 normalize 仍耦合；應先記錄各 reader role 的 columns
   與 provenance，再逐步抽取 normalize／validate，不在同一批改變 slicing 演算法。

### 2026-08-12 — Phase 4 source path metadata policy（進行中）

本次完成：

- 新增 dependency-free `source_metadata.py`，將 `getSrcFromFileName()` 的 Books／一般來源 path
  判定與 label marker parsing 從同時載入 pandas、SQLite、taxonomy 與 output adapters 的
  `DataConverter_utils.py` 移出；現在可在缺少 pandas 的最小環境直接測試 production path policy。
- `DataConverter.py`、`DataConverter_Combiner.py` 與 `CorpusMetadataManager.py` 直接依賴新的窄邊界；
  舊 `DataConverter_utils.getSrcFromFileName` import 仍以 re-export 保持相容，避免一次要求外部 caller 遷移。
- 保留 legacy camel-case function 與 `FileName`／`LabelList` keyword names，另提供 PEP 8 API；測試固定
  POSIX 一般來源、Windows Books、multi-label marker、unknown label 及舊 keyword caller 契約。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `SampleReader` 仍混合來源 I/O、文字切片與 normalize；下批應先
   以 reader role 固定 row schema，再抽取不改 slicing 演算法的 normalize／validate 純函式。
2. 本批固定 path policy 的代表性合法輸入；label marker 位於 path 邊界、缺少相鄰 metadata directory
   等 malformed path 的 legacy failure behavior 尚未定義。改成具名 domain error 前應先確認實際資料需求。
3. 完整 `DataConverter.py` import 與 CLI 仍被其他 module-scope runtime dependencies 阻擋；本批只移除
   provenance parser 對 pandas 等無關依賴，不代表 Phase 1 completion gate 已達成。

### 2026-08-12 — Phase 4 reader row schema validation（進行中）

本次完成：

- `sample_schema.validate_sample_rows()` 固定 reader → assembly 邊界的必要 columns：`file`、
  `InLabel`、`OutLabel`、`text`；驗證本身不依賴 pandas、process pool、filesystem 或 global state，
  並保留 row 順序與原 mapping。
- `PartNO` 維持 optional，因既有 external source adapter 可能省略，後續 DataFrame adapter 仍依原契約
  補為 `0`；本批未將相容行為誤判為 schema failure。
- `BuildSamplesDfFromPaths()` 在 label counter、DataFrame 與 artifact 副作用前執行驗證。非 mapping row
  或缺少必要 columns 時，錯誤會包含 source role/stage、row index 與所有缺少的 columns。
- isolated tests 固定 standard row、缺少 `PartNO` 的 external row、非 mapping payload 與缺欄診斷；
  完整輕量 suite 保持通過。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** 本批只固定所有 reader role 的共同輸出 schema；
   `SampleReader` 仍混合 filesystem／CZJ／ES I/O、文字切片與 normalize。下一批可先將
   `textSegsToSamples()` 的 row assembly 抽成純函式，但不可同時更改 slicing、rule-based label 或
   random sampling 語意。
2. `text`、labels 與 provenance value 的型別／空值政策尚未集中驗證；應先以現有 regular、fixed-test、
   CZJ 與 ES fixture 確認合法範圍，再收緊契約，避免拒絕 production 目前接受的資料。
3. 完整 legacy CLI 仍受 module-scope runtime dependencies 與工作池／模型需求限制；本批驗證的是
   dependency-free schema boundary，不代表 Phase 1 或完整 CLI E2E gate 已完成。

### 2026-08-12 — Phase 4 sliced-text row assembly（進行中）

本次完成：

- 將 `SampleReader.textSegsToSamples()` 兩條輸出路徑共用的 canonical row 組裝抽到
  `sample_pipeline.assemble_sample_row()`；一般 label mapping 與 rule-based 特殊 label 現在使用同一個
  dependency-free builder，固定輸出 `file`／`InLabel`／`OutLabel`／`text`／`PartNO`。
- builder 不讀取 reader instance、global state、logger、filesystem、tokenizer 或外部服務，也不提前收緊
  value validation；文字切片、rule-based label、OpenCC、random shuffle 與單一文本取樣上限語意均未改動。
- isolated tests 固定 canonical keys/values、與 `validate_sample_rows()` 的契約相容，以及每個 segment 取得
  獨立 row mapping，無需 import 具有重型 runtime dependencies 的 `sampleHandler.py`。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `textSegsToSamples()` 仍同時處理 ES provenance filename/date、
   segment layout cleanup、rule-based label、OpenCC 與 random sampling；下一批可先把不依賴 reader state 的
   segment layout normalization 抽成純函式，並以空值、換行比例邊界 fixture 固定既有語意。
2. 目前只固定 sliced-text 產生的 canonical row；CZJ samples SQLite 會直接回傳 database records，ES/CZJ
   與 FixedTest 的 value type／empty policy 仍需 characterization，不能直接套用更嚴格 validation。
3. 完整 `SampleReader.run()` 與 legacy CLI 仍需要 tokenizer、pandas、ES 等 runtime dependencies 及隔離資料；
   本批不宣稱 Phase 1 import gate 或完整 CLI E2E 已完成。

### 2026-08-12 — Phase 4 segment layout normalization（進行中）

本次完成：

- 依上一批建議，將 `SampleReader.textSegsToSamples()` 的 excessive-newline layout cleanup 抽到
  `sample_pipeline.normalize_segment_layout()`；純函式不讀 reader state、logger、filesystem、tokenizer
  或外部服務。
- 保留 legacy threshold：只有換行字元占 segment 長度**大於** 10% 時才將 `\n` 換成空白，恰好 10%
  不變；reader 原本會先排除空 segment，但純函式本身也安全保留空字串，避免除以零。
- isolated characterization tests 固定高於 threshold、恰好位於 threshold、空字串與單行文字行為；
  rule-based label、OpenCC、random shuffle、取樣上限及 row schema 均未改動。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `textSegsToSamples()` 仍混合 ES provenance filename/date、
   rule-based label、OpenCC 與 sampling；下一批可先將 rule-based 特殊輸出 label 的判定抽成純函式，
   以數字、句點、單一重複字元及 threshold 邊界固定優先順序，不同時改 label 名稱或條件。
2. segment value type 仍沿用 reader 提供字串的既有假設；CZJ samples SQLite 與 ES external rows 的
   type／empty policy 尚未 characterization，收緊 schema 前必須先補對應 fixture。
3. 完整 `SampleReader.run()` 與 legacy CLI 仍受重型 runtime dependencies、模型與工作池隔離資料限制；
   本批只證明 dependency-free layout transformation 與輕量 regression suite。

### 2026-08-12 — Phase 4 rule-based malformed-segment labels（進行中）

本次完成：

- 將 `SampleReader.textSegsToSamples()` 對異常長 segment 的特殊輸出 label 判定抽到 dependency-free
  `sample_pipeline.detect_special_output_label()`；reader 仍保留 `LenSeg > 50` 與 `RBActive` gate。
- 保留 legacy 判定優先順序與 strict thresholds：去除空白後數字比例大於 90%、句點比例大於 90%、
  單一重複字元比例大於 90%；候選仍需通過「ASCII range cleanup 後殘留少於 40 字元」才輸出。
- isolated characterization tests 固定三種 label、恰好 90% 不觸發、residual-text gate、空字串與一般文字；
  並保留全空白長 segment 在 legacy digit-ratio 計算的 `ZeroDivisionError`；label 名稱、row schema、OpenCC、
  regex label matching、random shuffle 與取樣上限均未改動。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** reader 仍混合 ES provenance filename/date、regex-based InLabel
   override、OpenCC 與 sampling；下一批可先抽取 regex label candidates 的排序／選取，透過 injected match
   counts 固定 interval、InfoScore priority 與無命中行為，避免純函式反向依賴 reader state。
2. `detect_special_output_label()` 刻意不包含 caller 的長度與 `RBActive` gate，以維持 helper 單一責任；
   若未來有其他 caller，必須明確套用對應 eligibility policy，不可誤將短文本分類為異常資料。
3. 完整 `SampleReader.run()` 與 legacy CLI 仍受 tokenizer、pandas、ES、模型與工作池 fixture 限制；本批
   僅驗證純判定、既有隔離 conversion fixture 與 repository 輕量測試。

### 2026-08-12 — Phase 4 regex-based input-label selection（進行中）

本次完成：

- 將 `SampleReader.textSegsToSamples()` 的 regex rule matching、interval filtering、InfoScore 排序與
  `InLabel` override 抽到 `sample_pipeline.select_rule_based_input_label()`；reader 只傳入 text、目前 label、
  rules 與 score mapping，不再自行組裝 candidate list。
- 保留 legacy 行為：比對前將 text 轉小寫、interval 兩端皆包含、最高 InfoScore 勝出；同分時依 mapping
  iteration order 維持 stable sort，較後規則勝出，無命中則保留原 `InLabel`。
- match counter 可注入，isolated tests 固定 matcher 收到 lower-case text、interval boundaries、score priority、
  no-match fallback 與 equal-score tie；預設 adapter 仍使用 `re.findall()`，不改既有 regex 語意。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `textSegsToSamples()` 仍處理 ES provenance filename/date、OpenCC、
   minimum-length filter、random shuffle 與 per-document sampling；下一批可先抽取 sampling policy，將 shuffle
   與 `nBound` selection 改由顯式 randomizer／純 slice boundary 驗證，但不可改預設隨機行為。
2. 本批保留 rule 或 score mapping malformed 時的原生 `KeyError`／unpack error；若要改為具名 domain error，
   應先建立 configuration validation boundary，而不是在純選取函式 silent fallback。
3. 完整 reader／CLI 仍需 heavy runtime 與外部資料；本批只驗證純 label selection、隔離 conversion fixture
   與 repository 輕量 suite，不代表 Phase 1 import gate 或完整 E2E 已完成。

### 2026-08-13 — Phase 4 per-document sampling policy（進行中）

本次完成：

- 依上一批建議，將 `SampleReader.textSegsToSamples()` 的隨機排序與單一文本筆數上限抽到
  `sample_pipeline.select_document_samples()`；reader 保留薄呼叫，不改 segment 產生、label mapping、
  OpenCC 或 row schema。
- 保留 legacy 順序與設定規則：啟用 `RandomSample` 時先 shuffle 再 slice；label-specific `nBound` 優先，
  未設定 label 時使用 `default`。缺少必要 `default` 時仍回報 `KeyError`，不加入 silent fallback。
- shuffle strategy 改由 caller 顯式傳入；production 仍傳入 `random.shuffle` 維持預設行為，isolated tests
  則可注入 deterministic strategy，固定 shuffle-before-limit、disabled-shuffle 與輸入 rows 不被原地改動。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** reader 仍處理 ES provenance filename/date、OpenCC 與 minimum-length
   filter；下一批可先抽取 ES provenance filename 組裝或文字轉碼 adapter boundary，但不可同時改輸出命名契約。
2. production random seed／generator 尚未納入 typed config；本批只建立可注入邊界，避免提前改變歷史上使用
   module-level `random` 的非 deterministic 行為。Phase 5 收斂 augmentation 與重跑 reproducibility 時應統一決策。
3. CZJ／ES／FixedTest value type 與 empty policy 仍缺 characterization；在收緊 sample value validation 前需先補
   各來源 fixture。完整 reader／CLI 仍需 tokenizer、pandas、外部資料與工作池隔離環境。

### 2026-08-13 — Phase 4 Elasticsearch provenance 組裝（進行中）

本次完成：

- 將 `SampleReader.textSegsToSamples()` 的 ES subject、Target／NonTarget 與 `itcDT` filename 組裝抽到
  `sample_pipeline.build_elasticsearch_provenance()`，並以 immutable `ElasticsearchProvenance` 同時回傳
  組裝結果與無效日期診斷；純轉換不讀 reader state、不 print，也不直接依賴 logger。
- 保留 legacy path 順序與資料契約：subject 最長 100 字元並位於 document id 前，Target role 位於其外層，
  日期 `YYYYMMDD` 位於最外層；三種既有 timestamp 格式均保持支援，非空無效日期仍產生 `None/` prefix，
  但現在只由 adapter 寫一筆摘要 log，不再為每個候選格式輸出 exception noise。
- filename sanitizer 以參數注入，production 仍使用 `RemoveIlleagalCharForFileName`；isolated tests 固定數字
  subject 轉字串、subject/target/date ordering、fractional／Zulu timestamps、NonTarget fallback、無效日期診斷，
  以及未啟用 subject mode 時不呼叫 sanitizer。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** OpenCC conversion 與 minimum-length eligibility 仍留在 reader；下批可
   將「轉碼後才判斷長度」固定成純 segment-to-row policy，但應以 injected converter 避免純核心依賴 OpenCC。
2. ES adapter 的 network read、`esRetMeta` 建立及 credential-bearing `esJob` 仍在 `SampleReader.run()`；後續應定義
   sample-row adapter contract，且 normalized config/log 絕不可輸出 token。
3. 本批刻意保留無效日期的 `None/` filename 相容行為。若要改為具名 input error，應另開契約變更並確認既有
   artifact consumer，而不是在純函式加入 silent fallback。

### 2026-08-13 — Phase 4 一般 segment 轉碼與長度 eligibility（進行中）

本次完成：

- 將一般 segment 的 optional OpenCC conversion 與 minimum-length gate 抽到
  `sample_pipeline.prepare_sample_text()`；純函式以 converter callback 注入外部轉碼 adapter，因此不直接
  import OpenCC，也不讀取 reader state、設定 dict、logger 或 filesystem。
- 保留 legacy 執行順序與邊界：先完成轉碼，再以轉碼後文字判斷長度；`len(text) >= LenLBD` 才建立 row，
  未設定 conversion 時完全不呼叫 converter。rule-based 特殊輸出 label 仍在此 gate 之前直接輸出，本批未改契約。
- isolated tests 固定 conversion-before-length、恰好等於最小長度可接受、低於門檻被排除，以及未啟用轉碼
  不呼叫 adapter；production reader 仍以薄 lambda 建立既有 OpenCC converter。
- 補強上一批 ES provenance 邊界：非字串但 truthy 的 `itcDT` 在 legacy 會被日期解析視為無效資料；現在同樣
  回傳 `None/` path 與 diagnostic，而不讓 `datetime.strptime()` 的 `TypeError` 越過 adapter boundary。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `textSegsToSamples()` 的 per-segment orchestration 仍混合 special-label、
   regex label、normal text preparation 與 row assembly；下一批應先以具名 `SegmentResult` 表示 accepted／dropped
   與原因，再逐步縮小 loop，但不得改變 special-label bypass minimum-length 的既有順序。
2. OpenCC adapter 仍依既有行為為每個一般 segment 建立 converter；只有 profiling 或 characterization 證明可安全
   reuse 時才調整生命週期，不應在責任抽取同時宣稱效能改善。
3. CZJ／ES／FixedTest 的 value type 與 empty policy、完整 reader／CLI fixture 仍未完成；Phase 4 completion 前仍需
   補來源角色 characterization，且不得用真實 ES、模型或工作池作無副作用測試。

### 2026-08-13 — Phase 4 per-segment orchestration 結果邊界（進行中）

本次完成：

- 新增 immutable `SegmentResult(row, reason)` 與 `sample_pipeline.transform_sample_segment()`，將單一 segment 的
  layout normalization、special-label 判定、regex label override、轉碼、minimum-length gate、label mapping 與
  canonical row assembly 收斂為可獨立測試的純 orchestration boundary。
- `SampleReader.textSegsToSamples()` 的 loop 現在只傳入 reader 設定與 OpenCC adapter，並依 `SegmentResult.row`
  決定是否收集樣本；drop 不再只能由缺少 row 反推，現以 `below-minimum-length` reason 明確表示。
- 保留 legacy branch order：special malformed label 仍優先並略過 regex override、OpenCC、minimum-length 與一般
  label conversion；一般 row 仍依序執行 regex label → 文字轉碼 → 長度 gate → label mapping。非空 label mapping
  缺少 resolved label 時仍拋出 `KeyError`，避免抽取時意外加入 fallback。
- characterization tests 固定 accepted row 的完整 schema、below-minimum drop、special-label bypass 與 missing label
  conversion failure；測試不需 import `sampleHandler.py`、OpenCC、模型、process pool 或外部服務。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** reader loop 已縮小，但整份 `SampleReader.run()` 仍混合 filesystem、ES、
   CZJ SQLite、清整、切片與 multi-label orchestration；下一批應選單一 source role 建立 adapter contract，不應一次
   重寫所有來源分支。
2. `SegmentResult.reason` 目前只有 `accepted`、`special-label`、`below-minimum-length`；只有 stage/result summary
   確實需要統計時才擴充或彙總，不要在純函式直接 log/print。
3. Phase 4 尚缺 CZJ／ES／FixedTest value type 與 empty policy characterization；Phase 5 的 `DatasetBundle`、
   reproducible augmentation 與 output counts 尚未開始，不能因 per-segment loop 縮小就宣稱 Phase 4 完成。

### 2026-08-13 — Phase 4 regular filesystem source adapter（進行中）

本次完成：

- 新增 dependency-free `sample_sources.py`，以 immutable `SourceDocument(text, input_labels)` 固定一般
  `.txt`／`.ai2` reader 在切片前的輸出契約；path label parser 與 UTF-8 text reader 皆以 callback 注入，
  isolated test 不需 import tokenizer、pandas、Elasticsearch 或讀取真實 filesystem。
- `SampleReader.run()` 的 regular filesystem 分支改為薄 adapter：仍傳遞既有 `UniqueSorted`／
  `OnlyLettersDigits` keyword，保留有 label 才讀取 `.txt`、無 label 的 `.ai2` 使用 `Scrap`、以及 UTF-8
  text reader 契約；regex data cleaning、BasicDataCleaner、TextDivider、multi-label 與 sample transformation
  順序均未改動。
- characterization tests 固定 label adapter keyword、label 順序、UTF-8 reader arguments、unlabelled `.txt`
  不觸發 I/O、unlabelled `.ai2` fallback，以及非 regular extension 在 adapter 呼叫前明確失敗。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** regular source 的讀取／routing 已有具名結果，但 regex cleaner 與
   document-level BasicDataCleaner／TextDivider 仍由 `SampleReader.run()` orchestration；下一批可只抽取
   regular document preparation boundary，不應同時改 tokenization 或切片寬度演算法。
2. CZJ corpus／CZJ samples SQLite 與 ES network source 尚未採用 `SourceDocument`；應分別先固定各自的空值、
   missing row 與 value-type 契約，不要假設 filesystem contract 可直接套用，也不得用正式服務作測試。
3. 完整 reader／CLI 仍受重型 runtime dependencies、模型與工作池 fixture 限制；本批只驗證 regular source
   adapter 和既有 dependency-free pipeline，Phase 5 的 bundle/result/output work 尚未開始。

### 2026-08-13 — Phase 4 regular label-aware cleaning boundary（進行中）

本次完成：

- `sample_sources.apply_regular_cleaning_rules()` 將 regular filesystem document 的 label-aware regex cleaning
  從 `SampleReader.run()` 抽到 dependency-free boundary；輸入／輸出皆使用 immutable `SourceDocument`，不讀
  reader globals、logger、filesystem 或重型 runtime。
- label overlap 與 pattern cleaner 以 callback 注入，production 仍使用既有 `ListCap` 與
  `DataCleanerWithPattern` adapters。保留 legacy mapping iteration order、`ExemptInLabelList` 預設空清單，
  以及每加入一條 eligible rule 就以累積 rules 再執行 cleaner 的歷史順序；本批未趁抽取時改成單次清理。
- characterization tests 固定 eligible rules 累積順序、跨步驟 text 傳遞、label exemption、空 rules 不呼叫
  adapters，以及 immutable labels 不因 cleaning 遺失。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `BasicDataCleaner` 與 `TextDivider` 是 regular、CZJ corpus 與 ES
   共用的 document preparation／slicing 路徑；下一批應先把共用 orchestration 的輸入／輸出固定為具名結果，
   但保留 tokenizer、language heuristic 與 FixedTest width policy 作為 injected adapters 或現有薄相容層。
2. 累積 rules 重複套用先前 cleaner 是已固定的 legacy 行為，不代表最佳效能；只有 fixture 證明單次套用產物
   等價並完成效能量測後，才能在 Phase 8 改寫，不能在 Phase 4 責任抽取時暗中改變文本。
3. CZJ／ES／FixedTest value type、empty policy 與 adapter failure 仍缺 characterization；完整 CLI、SQLite 與
   external-service 路徑未在本批執行，Phase 5 仍未開始。

### 2026-08-13 — Phase 4 共用 document preparation 結果邊界（進行中）

本次完成：

- 新增 immutable `PreparedDocument(text, input_labels, segments)` 與
  `sample_sources.prepare_document_segments()`，固定 source document 在 sample conversion 前必須先執行
  normalization、再執行 slicing，並以 tuple 保留 ordered segments 與 labels。
- `SampleReader.run()` 的 regular filesystem、CZJ corpus lookup 與 ES read 分支現在於共同路徑建立
  `SourceDocument`，再將既有 `BasicDataCleaner(strQ2B=True, DummySpace=True)` 與完整 `TextDivider` 設定以
  callbacks 注入。tokenization、model directory、mode、width、FixedTest 與 language heuristic 仍留在原 adapter，
  本批只抽取 orchestration，不重寫切片演算法。
- characterization tests 固定 normalize-before-divide、divider 必須收到 normalized text、label／segment ordering、
  empty segment sequence，以及 immutable named result；測試不需載入 tokenizer、OpenCC、pandas 或 ES。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `SampleReader.run()` 仍直接執行 source-specific ES network、CZJ SQLite
   與 CZJ samples DataFrame adapters；下一批應選 CZJ corpus title lookup 固定 missing row、null label 與 connection
   cleanup 契約，再抽成窄 adapter，避免直接處理較高風險的 ES retry／credential boundary。
2. `TextDivider` 仍混合 redundant-space cleanup、tokenizer adapter 與 character/language heuristic；現有
   `prepare_document_segments()` 刻意只注入整體 divider。若繼續細分，應一次固定一項 policy，不得改變
   FixedTest、FullCut 或 short-message 行為。
3. 完整 reader／CLI、SQLite artifacts 與 external service 未執行；Phase 5 的 `DatasetBundle`、reproducible
   augmentation 與 `ConversionResult` 仍未開始。

### 2026-08-13 — Phase 4 CZJ corpus title lookup adapter（進行中）

本次完成：

- 新增 `sample_sources.read_czj_corpus_document()`，將 `SampleReader.run()` 內的 CZJ corpus SQLite title lookup
  抽成窄 adapter，統一回傳 immutable `SourceDocument`；query 仍使用既有 `Corpus` table、`title=?` parameter、
  `InLabel,text` columns 與 null label → `Scrap` fallback。
- database connector 以 callback 注入，connection 由 `try/finally` 保證在成功、missing title、malformed row 或
  fetch exception 時關閉。missing title 現在以包含 title 與 database path 的 `LookupError` 在 preparation／output
  副作用前失敗，取代舊程式 unpack `None` 時缺少來源資訊的 `TypeError`。
- characterization tests 固定 SQL 與 parameters、label/text mapping、null label fallback、missing/malformed diagnostics、
  fetch failure cleanup；另以 `TemporaryDirectory` 與標準庫 SQLite 驗證真實 isolated database lookup，不讀寫專案
  dataset 或工作池。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** CZJ samples database 分支仍透過 pandas `dfFromSQLite3()` 直接建立 rows，
   CZJ corpus-file fan-out 分支也混合 DataFrame iteration、nested readers 與 console output；下一批應先固定 CZJ
   samples rows schema／empty DB 行為，再決定是否抽 output-neutral SQLite row adapter。
2. ES network branch 仍含 retry、credential-bearing client 建立、response parsing 與 cleanup；應先定義 response-to-
   `SourceDocument` 純 mapping，再處理 executor/retry，不得在測試連線正式 ES 或輸出 credentials。
3. 本批只執行 temporary SQLite lookup 與 dependency-free suites，未執行完整 legacy CLI、真實 CZJ corpus 或
   workspace handoff；Phase 5 尚未開始。

### 2026-08-13 — Phase 4 CZJ samples row adapter（進行中）

本次完成：

- 新增 `sample_sources.read_czj_sample_rows()`，將已切片 CZJ samples database 的 row loading 與 reader branch
  分開；SQLite connection factory 以 callback 注入，adapter 直接從 canonical `sampleSrc` table 選取 sample
  columns，核心結果固定為有序 tuple，不依賴 pandas、不直接寫檔或建立 DataFrame。
- 共用 `sample_schema.validate_sample_rows()` 在 dataset assembly 前檢查 mapping shape，以及 `file`、`InLabel`、
  `OutLabel`、`text` 必要欄位；錯誤會包含 `CZJ samples database` 與 row index，`PartNO` 仍維持 external row
  可省略的既有契約。
- 明確固定 empty table 回傳空 tuple；SQL 只選取 `file`、`InLabel`、`OutLabel`、`text`、`PartNO`，不再依賴
  pandas 產生的 `index` column。所有 query／fetch 成功或失敗路徑均關閉 connection；reader 在 boundary 外轉回
  list，故其下游 return shape 與 multi-label count 不變。
- temporary SQLite characterization tests 涵蓋 canonical rows、legacy index 不外洩、empty table、缺少 canonical
  column 與 fetch failure cleanup；完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check` 均通過。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** CZJ corpus-file fan-out branch 仍直接載入整個 DataFrame、逐列建立 nested
   reader 並輸出 raw `df`／`title`／`result`；下一批應先建立 corpus title enumeration adapter，固定空 database、
   多 title ordering 與 nested results aggregation，並移除 raw text/dataframe console output。
2. `sampleSrc.PartNO` 目前依現有 CZJ artifact schema 視為 canonical database column；外部 in-memory rows 仍可依
   `sample_schema` 契約省略它。若需支援缺少 `PartNO` 的第三方 database，應先新增具版本的 schema adapter，不能
   以 broad exception 或 `SELECT *` 靜默接受未知格式。
3. ES network response mapping、CZJ／ES value type 與完整 CLI fixture 仍未完成；Phase 5 的 `DatasetBundle`、
   reproducible augmentation 與 `ConversionResult` 尚未開始。

### 2026-08-13 — Phase 4 CZJ corpus title discovery adapter（進行中）

本次完成：

- 新增 `sample_sources.read_czj_corpus_titles()`，將 `DataConvertJobGenerater.run()` 的 CZJ corpus title discovery
  從 generic `sqlite3Query()` 與 console output 抽成窄 SQLite adapter；job generator 不再理解 query string、
  `ListForm` 或 generic DB helper 的回傳形狀。
- adapter 使用 injected connection factory，依 database row order 回傳 immutable title tuple；空 `Corpus` table
  明確回傳空 tuple，query／fetch 成功或失敗均關閉 connection，null title 在建立 worker job 前以 row index 診斷。
- production job generation 保留 `(title, database path)` fan-out order 與後續 `SampleReader` 設定傳遞，並移除會將
  完整 title list 印到 console 的 raw output；沒有改 per-title text loading、切片、label 或 multiprocessing 行為。
- temporary SQLite 與 fake connection characterization tests 固定多 title ordering、empty corpus、null title 與 fetch
  failure cleanup；source-related targeted suites、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check` 通過。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `SampleReader.run()` 仍保留一個直接收到 `CZJ_CorpusFile*.sql3` 的 legacy
   branch，該 branch 以 pandas 載入整庫並建立 nested readers；canonical `DataConvertJobGenerater` 已不走此路徑。
   下批應先以 import/call-site search 與 characterization 判定是否可移除或改為薄 compatibility adapter，不可在未確認
   caller 時直接改變 return shape。
2. title discovery 保留 SQLite 未指定 `ORDER BY` 的 database row order，以免重構時改變既有 job ordering；若 Phase 7
   需要跨資料庫可重現排序，應另行定義排序契約並比較 artifacts，而不是在 adapter 中暗加 alphabetical sort。
3. ES response-to-`SourceDocument` mapping、CZJ／ES text null/type policy 與完整 CLI fixture 仍未完成；Phase 5 尚未開始。

### 2026-08-13 — Phase 2 SampleReader mutable defaults 收斂（進行中）

本次完成：

- 移除 `SampleReader.__init__()` 的 list／dict／nested dict mutable defaults；`LabelList`、`sampleMethod`、label/rule
  mappings、ES job/metadata 與 cleaning rules 現以 `None` 作為 API default，並在 instance 建立時產生各自容器。
- `sampleMethod`、`esJob` 與 nested cleaning rules 使用 deep copy，其他 flat mappings/list 使用明確 copy；caller 傳入
  的設定不再因 reader 更新 `InfoScoreTable`、`esRetMeta` 或 nested config 而被跨 job／跨 instance 意外污染。
- 保留未提供設定時的 legacy sampling defaults：每文件 default 5000、`Economist` 1000、random sampling enabled、
  minimum length 128；既有 keyword names 與 production caller 不變。
- 新增 AST regression gate，禁止 `SampleReader` constructor 再引入 list／dict／set defaults；sample/source targeted
  tests、完整輕量 unittest、相關檔案 `py_compile` 與 `git diff --check` 通過。

尚未完成／下次優先事項：

1. **Phase 2 completion gate 尚未達成。** `SampleReader` 仍接收大量鬆散 options；下一批可先建立 immutable reader
   policy dataclass 或單一 normalization function，但須維持現有 constructor keyword compatibility，避免同時重寫 caller。
2. repository 其他 legacy constructors 仍可能有 mutable defaults；本批只修正 active DatasetConverter reader，沒有做
   無界限的全 repository 格式化。後續應依實際 mutation risk 與 call graph 分批處理。
3. ES response mapping、retry/client lifecycle 與 credential-bearing config 仍混在 reader；不得因 container isolation
   完成就宣稱 external-service boundary 已建立。

### 2026-08-13 — Phase 4 Elasticsearch response mapping boundary（進行中）

本次完成：

- 新增 immutable `ElasticsearchDocument(document, subject, metadata)` 與 dependency-free
  `sample_sources.map_elasticsearch_document()`，將 ES `_source` response 轉成 `SourceDocument`、subject 與 provenance
  metadata；純 mapping 不建立 client、不 retry、不讀 credentials、不 log。
- 保留 legacy response 契約：正文取自 `rawInfo.content`、input label 固定為 `Scrap`、非空 `userNames` 設定
  `Target=T`、日期取自 `itcDT`；只有 subject filename mode 啟用時才要求 `communication` container，必要 container
  缺失仍以原生 `KeyError` fail fast，不加入 silent fallback。
- `SampleReader.run()` 的 network branch 在成功取得非空 content 後使用 mapper，再更新 instance provenance；既有最多
  100 次 retry、ES client construction/close、空 content failure 與後續 filename assembly 順序未改動。
- characterization tests 固定完整 mapping、inactive subject/target、missing content、required shape failure 與 subject-mode
  communication requirement；sample source/pipeline suites、完整輕量 unittest、相關 `py_compile` 與 `git diff --check` 通過。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** ES client lifecycle 仍有 retry 中重建 client、exception logging typo，以及只在
   success path close 的風險；下一批應建立 injected fetch adapter，固定 retry count、每次 attempt cleanup 與最終 failure
   result，但測試不得連線正式 ES 或記錄 credentials。
2. `SourceDocument.text` annotation 仍是 `str`，mapper 暫時保留 missing content 為 `None` 以供 network retry boundary
   判斷；在把 retry 搬出 reader 前不可直接收緊為 exception，否則會改變現有 retry 行為。
3. ES `userNames` 的 string/list value-type policy 尚未正式化；目前保留 legacy `len(value) > 0` semantics。若要收斂
   schema，須先補兩種實際 response fixture 並確認 Target 判定契約。

### 2026-08-13 — Phase 4 Elasticsearch bounded fetch adapter（進行中）

本次完成：

- 新增 `sample_sources.fetch_elasticsearch_response()`，以 injected client factory、fetch callback、content selector 與
  error reporter 固定 bounded retry；credentials 只存在 production factory closure，adapter 不讀取或輸出 credential。
- 每次 attempt 都獨立建立並在 `finally` 關閉 client，修正 legacy 只有最後成功 client 會 close、失敗 attempts 可能洩漏
  connection 的問題；exception 與 missing content 都消耗 attempt，但只有 exception 呼叫 error reporter，維持診斷語意。
- `SampleReader.run()` 改用 fetch adapter，保留最多 100 attempts 與最終無 content 回傳空 reader result；同時修正舊路徑
  呼叫不存在的 `self.MPlogger` 與含 typo 的錯誤訊息，改由既有 `self.MPLOGGER` 寫摘要且不含 credentials。
- characterization tests 固定 missing-content retry、exception reporting、每次 client cleanup、bounded exhaustion 與 invalid
  attempt validation；sample source/pipeline suites、完整輕量 unittest、相關 `py_compile` 與 `git diff --check` 通過。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** production client construction 仍位於 reader，且 `Elasticsearch` import 仍是
   module-level heavy dependency；下一批可把 factory 移到明確 integration adapter 並延遲至 ES source 啟用時 import，
   但不得用 try/except 包 import，也不得改 CLI credential/config contract。
2. 目前仍保留 100 次立即 retry，未加入 backoff，以免無量測地改變歷史 latency；Phase 8 profiling 若證實 external
   failure 造成資源壓力，再以 injectable retry policy 加入 delay/jitter 並建立 deterministic tests。
3. mapper 的 missing content `None` 與 ES `userNames` value-type policy 尚待收斂；完整 CLI/isolated ES client fixture 仍未完成。

### 2026-08-13 — Phase 4 Elasticsearch client factory integration boundary（進行中）

本次完成：

- 新增 `DatasetConverter/elasticsearch_source.py` integration module，以 `create_elasticsearch_client()` 集中 legacy
  host、HTTP auth 與 `verify_certs=False` client construction；credentials 只傳給 client constructor，不進入純 mapper/
  retry helpers 或 log。
- 第三方 `elasticsearch` import 移入 factory function，且未使用 try/except；一般 filesystem、CZJ 與純 transformation
  路徑載入 `sampleHandler` 時不再因 module-scope ES import 要求安裝 optional dependency，只有 ES source 啟用才載入。
- `SampleReader` production fetch factory 改為呼叫 integration adapter，保留 CLI token mapping與既有 constructor arguments；
  client close 仍由上一批 bounded fetch adapter 統一負責。
- isolated factory test 以暫時 module adapter 驗證 constructor arguments，不需安裝 package 或連線網路；AST regression
  tests 固定 `sampleHandler.py` 與 integration module 都沒有 module-scope Elasticsearch import。

尚未完成／下次優先事項：

1. **Phase 4 completion gate 尚未達成。** `transformers.AutoTokenizer`、OpenCC 等其他 heavy imports 仍在 reader module
   scope；應依 source/feature activation 一項一項建立 adapter，不可用 catch-all optional import 或一次搬動所有 dependencies。
2. ES credentials 仍以 legacy mutable mapping 由 CLI/job 傳入；Phase 2 config normalization 尚需建立 redacted immutable
   external-source config，並以 tests 保證 normalized summary 不包含 password/token。
3. 未執行真實 ES smoke test；目前只證明 client construction contract 與 dependency loading boundary，不宣稱 server、TLS
   或 credentials 可用。

### 2026-08-13 — Phase 2 DataConvertJobGenerater instance config isolation（進行中）

本次完成：

- 移除 active `DataConvertJobGenerater.__init__()` 的 mutable defaults：source roots/files、CZJ DB list、ES job、sampling、
  score/rule mappings、restricted labels 與 cleaning rules 全部改以 `None` 表示未提供，再於 instance 初始化。
- 對會被 generator 修改的 `esJob` 使用 deep copy；這修正 `retItem` 寫入 caller mapping、後續 generator 或 fixed-test job
  互相污染的風險。nested sample/cleaning config 亦 deep copy，其他 flat list/mapping 明確 copy。
- 保留 legacy sampling defaults、constructor keyword names、source discovery ordering 與 job payload shape；沒有改 ES query、
  multiprocessing、label conversion 或 reader 行為。
- 新增 AST regression gate，禁止 `DataConvertJobGenerater` constructor 再引入 list/dict/set defaults；source-role、source
  collection、conversion fixture 與 package-layout targeted tests、完整輕量 unittest、`py_compile`、`git diff --check` 通過。

尚未完成／下次優先事項：

1. **Phase 2 completion gate 尚未達成。** `DatasetGenerator`、`BuildSamplesDfFromPaths()` 等 active APIs 仍有 mutable
   defaults；應依 mutation/call graph 逐一收斂並加入窄 regression gate，不要只做全檔機械替換。
2. generator 仍以大型 loose configuration surface 傳遞至 `SampleReader`；下一批可建立 immutable normalized reader-job
   policy，但需先 characterization constructor-to-job mapping，維持 CLI/default compatibility。
3. ES config 尚未成為 redacted typed config；本批只隔離 container ownership，不代表 credential validation/logging gate 完成。

### 2026-08-13 — Phase 2 pipeline/dataset generator mutable defaults 收斂（進行中）

本次完成：

- 移除 active `BuildSamplesDfFromPaths()` 與 `DatasetGenerator.__init__()` 的 mutable defaults；source roots、index
  columns、split ratio、fixed-test paths、ES job 與 `DCkwargs` 全改以 `None` 表示未提供，再建立逐次呼叫／逐 instance 容器。
- `BuildSamplesDfFromPaths()` 在 stage boundary copy roots，並 deep-copy ES/config mappings，避免其 log truncation、job
  normalization 或下游 adapters 回寫 caller config；`DatasetGenerator` 同樣隔離 output/split 階段持有的設定。
- 保留既有 function/constructor keyword names、empty defaults、split/augmentation policy、output filenames 與 DataFrame
  flow；本批只調整 ownership，不改資料演算法或 artifact contract。
- 新增 AST regression gate，固定兩個 active APIs 不得再出現 list/dict/set defaults；fixture integration、split、source-role、
  package-layout targeted tests、完整輕量 unittest、相關 `py_compile` 與 `git diff --check` 通過。

尚未完成／下次優先事項：

1. **Phase 2 completion gate 尚未達成。** `DatasetGenerator` nested output helper 與其他 stage helpers 仍需依 call graph
   盤點；只有確實 active 且存在 mutation risk 的 API 才應收斂，避免把 legacy/dead scripts 一併機械修改。
2. `DCkwargs` 仍是大型 mutable mapping，現在雖已隔離 ownership，但尚未形成單一 typed normalized config；下一批應先
   characterization BuildSamples → job generator → reader 的必要 keys/defaults，再建立 dataclass mapping。
3. deep copy 對 taxonomy/tree objects 的成本尚未 profiling；若 Phase 8 證明是瓶頸，應用 immutable config 取代 copy，
   不可在缺少 ownership contract 時退回 shared mutable mapping。

### 2026-08-13 — Phase 1/4 tokenizer integration 與 slicing boundary（進行中）

本次完成：

- 新增 `tokenizer_source.load_auto_tokenizer()` integration boundary，集中既有
  `AutoTokenizer.from_pretrained(model_directory, trust_remote_code=True)` 契約；production wrapping 與 maintenance
  probe 均改由同一 factory 載入 tokenizer，未改模型目錄解析、token slicing 或回傳格式。
- `transformers` 改為 factory function 內的延遲 import，且未使用 `try/except`；一般 filesystem、CZJ、ES 與純
  transformation 路徑載入 `sampleHandler` 時不再因 module-scope import 要求安裝 Transformers，只有 tokenizer 功能
  實際啟用時才需要該 optional runtime。
- isolated test 以暫時 module adapter 固定 model path 與 `trust_remote_code` constructor arguments，不下載模型或連線網路；
  AST regression tests 同時禁止 reader 與 integration module 重新加入 module-scope Transformers import。
- 後續依 review 回饋補上實際 transformation boundary：新增 immutable `TokenizedChunks` 與 dependency-free
  `split_tokenized_context()`，將 special-token reserve、content token grouping、character span slicing、相鄰 boundary
  去重與 optional retokenization 從 legacy reader helper 抽出；既有 `tokenization_wrap()` 保留 dict API 薄相容層。
- fake tokenizer characterization tests 固定兩組 token chunks、相鄰 span 不重疊、只在要求時逐 chunk retokenize、只有
  special tokens 的空結果，以及無內容 token budget 的具名錯誤；既有 encoding 可注入，避免 wrapper 重複 tokenize 正文。
- 依本輪執行結果新增 immutable `TokenizerModel` 與 injected `resolve_tokenizer_model()`，將 requested path、local default
  fallback、remote default name 與第一個含 `config.json` 的 nested checkpoint discovery 移出 legacy wrapper；walker 直接
  使用每列 files metadata，不再對探索到的每個目錄額外呼叫 `os.listdir()`。
- model-resolution tests 固定 requested local model、nested checkpoint、local fallback 與無本機模型時保留 remote default
  name；`tokenization_wrap()` 現只負責組合 production resolver/walker、輸出既有 warning 並載入具名 resolved path。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** OpenCC、pandas/dataframe utilities 與其他 heavy imports 仍在 reader module
   scope；下一批應依實際 feature activation 逐項建立窄 adapter，不可用 catch-all optional import 一次隱藏 dependency。
2. `tokenization_wrap()` 仍直接處理 debug/word analysis 與 short-message fast path；下批可先確認 `word_analysis` 是否有
   caller 依賴，再把只產生 debug mapping、未進入回傳值的診斷移到 maintenance boundary，須保留 public dict shape。
3. 未執行真實 Transformers/model smoke test；目前證明 factory 呼叫、dependency loading 與 fake-tokenizer slicing boundary，
   不宣稱模型路徑、remote code 或 checkpoint 在此容器可用。

### 2026-08-13 — Phase 1 OpenCC integration boundary（進行中）

本次完成：

- 新增 `opencc_source.convert_text()`，集中既有 `OpenCC(conversion).convert(text)` 契約；
  `SampleReader.textSegsToSamples()` 改為注入此 adapter，未改 conversion-before-length、special-label bypass、
  label mapping、sampling 或 row schema。
- 第三方 `opencc` import 移至 adapter function 內，且未使用 `try/except`；未啟用文字轉碼的 filesystem、CZJ、ES
  與 tokenizer reader 路徑載入 `sampleHandler.py` 時，不再僅因 module-scope import 要求 OpenCC runtime。
- isolated fake-module test 固定 conversion 名稱、輸入文字與回傳值，AST regression gate 同時禁止 reader 與 integration
  adapter 重新加入 module-scope OpenCC import；測試不需安裝 OpenCC 或處理真實 dataset。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** `sampleHandler.py` 仍在 module scope 載入 dataframe、CLI、model path、
   text processing 與 multiprocessing utilities；下一批應以 import/call graph 找出非 reader source 必需的最窄重型
   dependency，再採 feature-activated adapter 處理，不可用 broad optional-import fallback。
2. production adapter 仍依 legacy 行為為每個需轉碼的一般 segment 建立一個 `OpenCC` converter；未先 profiling 與固定
   converter reuse/thread-safety 契約前，不應為效能猜測改成 global singleton 或 shared mutable cache。
3. 本批未執行真實 OpenCC smoke test或完整 legacy CLI；目前只證明 adapter 呼叫契約、延遲 dependency loading 與既有
   dependency-free transformation tests，不宣稱特定 conversion table 在此容器可用。

### 2026-08-13 — Phase 1/4 tokenizer word-analysis boundary（進行中）

本次完成：

- import/call-site search 確認 `word_analysis` 只存在於 `tokenization_wrap()` 的相容 keyword，production callers 均未啟用；
  該分支計算的 mappings 不進入既有 `{"ctxCut", "ReTks"}` 回傳值，只供 debug console 診斷。
- 新增 immutable `TokenWordAnalysis` 與 dependency-free `analyze_token_word_mapping()`，將 space-delimited word spans、
  tokenizer character spans 與 token positions 的組裝移出 legacy reader wrapper；保留空白 word 的 legacy index 與
  token-to-word containment 規則。
- `tokenization_wrap()` 保留 `word_analysis` keyword 與 public dict shape，但只在 `word_analysis=True` 且 `debug=True`
  時建立診斷 mapping；過去 `word_analysis=True, debug=False` 會執行無法觀察、未回傳的 mapping 計算，現在直接略過。
- fake encoding tests 固定一般兩詞、多 token word、重複空白的 legacy word index 與 special-token skip，不載入真實模型、
  Transformers、OpenCC、pandas 或 reader runtime。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** `sampleHandler.py` 的 maintenance-only `tokenization_wrap_Test()` 仍讀 CLI parser、
   捕捉 broad exception 並依賴 module globals；下一批應把 probe 搬至獨立 maintenance entrypoint，或先以 call-site/CLI
   characterization 證明可移除，但不可改 production `tokenization_wrap()` 回傳 shape。
2. word analysis 仍採每個 token 掃描所有 word spans 的 legacy O(tokens × words) 規則；它現在只在明確 debug 時執行。
   若要改為 linear cursor，須先增加 punctuation、Unicode、token span 跨 word 與 tokenizer `None` span fixtures。
3. 未執行真實 tokenizer/model smoke test或完整 legacy CLI；目前只證明純 mapping 與既有 fake-token slicing tests，
   不宣稱任一實際 tokenizer 的 `word_ids()`／`token_to_chars()` 行為。

### 2026-08-13 — Phase 1 reader maintenance probe removal（進行中）

本次完成：

- repository call-site search 證實 `tokenization_wrap_Test()` 只由 `sampleHandler.py` 自身的 `__main__` block 呼叫，沒有
  production、test 或文件入口依賴；因此移除 maintenance probe、內嵌長篇測試文本與 script-mode block，而非將其搬到
  另一個仍會 import reader side effects 的模組。
- reader 不再為已移除的 probe 在 module scope import `ClassfierOptionParser` 與 `get_base_model_checkpoint`，也移除 probe
  的 global tokenizer、broad exception swallowing、模型路徑逐一猜測及 raw tokenizer output；production
  `tokenization_wrap()`、`SampleReader` API 與 stage caller 不變。
- AST regression test 固定 reader 不再含 maintenance probe、CLI parser/model-checkpoint imports 或 `__main__` block；
  tokenizer slicing、word analysis 與 package-layout targeted suites 保持通過。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** `sampleHandler.py` import 時仍呼叫 `PackageImporter.proc()`、可能變更 cwd，並載入
   dataframe、multiprocessing 與 text-processing utilities；下批應優先 characterization import-time cwd 行為，再移除
   reader 的 cwd mutation，且須維持 `DataConverter.py` 直接執行時的 package resolution。
2. `tokenization_wrap()` 仍是 legacy public helper；若未來需要可執行 tokenizer probe，應建立有明確 argv、退出狀態與
   小型 fixture 的 maintenance CLI，不應把大型真實文本或 silent exception fallback 放回 production reader。
3. 本批未執行真實模型或完整 DataConverter CLI；目前只證明無 caller 的 maintenance code 可移除及 dependency-free
   regression suites，不宣稱 Phase 1 import-side-effect completion gate 已達成。

### 2026-08-13 — Phase 1 reader cwd/path-injector removal（進行中）

本次完成：

- 移除 `sampleHandler.py` import-time 的 `PackageImporter.proc()`；reader 不再把機器特定磁碟、`PythonModule` 或多層
  parent-relative paths 追加到 `sys.path`。canonical caller `DataConverter.py` 已使用 `__file__` 推導 repository root，
  因此直接執行 stage 的 package resolution 不依賴 reader 的 legacy injector。
- 移除 reader 依當前目錄名稱判斷並執行 `os.chdir("../")` 的 module-scope block及其 console output；import reader 不再
  由自身程式碼改變 process cwd，filesystem paths 繼續沿用 caller 傳入值與既有 stage working-directory contract。
- AST regression gate 禁止 reader 重新 import `PackageImport` 或呼叫 module-scope `os.chdir()`；DataConverter entrypoint 與
  package-layout targeted tests持續固定 direct-script root bootstrap 與 stage 自身不改 cwd 的邊界。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** isolated subprocess import 在此容器因缺少 `psutil`（由共用 utilities
   module-scope import）而無法完成；下一批應先把 reader 實際使用的輕量 filesystem helpers 與重型 generic utilities
   imports 分離，再建立真正的 `python -c "import DatasetConverter.sampleHandler"` cwd/side-effect test。
2. reader 仍 module-scope import pandas-backed `dfFromSQLite3`，但 canonical CZJ samples adapter 已不再需要它；下批應先確認
   剩餘 call sites 是否只屬 legacy corpus-file compatibility branch，再決定以 SQLite adapter 取代或延遲 import。
3. 本批未執行完整 DataConverter CLI，因其需完整 runtime 與工作池設定；目前只證明 source-level injector/cwd mutation
   已移除以及直接 stage 的 repository-root bootstrap 仍由既有 tests 固定。

### 2026-08-13 — Phase 1/4 legacy CZJ corpus fan-out removal（進行中）

本次完成：

- call graph 確認 canonical `DataConvertJobGenerater.run()` 先以 `read_czj_corpus_titles()` 枚舉 title，再建立帶有
  `CZJCorpusSQLFile` 的逐 title `SampleReader` jobs；reader 會在該具名 branch 使用 `read_czj_corpus_document()`，不會把
  corpus database path 當作一般 `file` 重新 fan-out。
- 移除 `SampleReader.run()` 中直接匹配 `CZJ_CorpusFile*.sql3` 的 legacy branch；該 branch 以 pandas 載入整庫、輸出 raw
  DataFrame/title/result、建立未傳遞原 reader policies 的 nested readers，最後亦未 return assembled result，並非 canonical
  job contract。CZJ samples database 與逐 title corpus lookup branches保持不變。
- reader 因此不再 module-scope import pandas-backed `dfFromSQLite3`；AST regression gate 固定 dataframe adapter 與 corpus-file
  filename fan-out 不回到 reader，CZJ SQLite adapter/source-role suites固定現有 canonical flow。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** isolated reader import 仍受共用 `utilities.py` 的 module-scope `psutil` 依賴阻擋；
   下批應盤點 reader 實際使用的 `RemoveIlleagalCharForFileName`、`ListCap`、`wrap` 與 filename helpers，優先移至／改用
   dependency-free boundary，不可用 try/except 隱藏 missing dependency。
2. canonical CZJ corpus path目前仍由 generator title discovery與 reader per-title lookup各開啟 SQLite connection；若 Phase 8
   profiling 證明是瓶頸，應在不跨 process共享 connection 的前提下比較 batch read artifact，而非恢復 pandas whole-DB fan-out。
3. 本批未執行真實 CZJ database或完整 CLI；temporary SQLite adapter tests與 source-role tests證明既有 canonical contracts，
   但不宣稱外部 corpus schema/data quality 已驗證。

### 2026-08-13 — Phase 1 dependency-free reader helpers（進行中）

本次完成：

- 新增 `reader_utils.py`，以標準庫／純函式提供 reader 實際使用的 filename normalization、extension extraction、filename
  sanitization、list intersection 與 fixed-width wrapping；逐項保留 generic utilities 的 legacy separators、illegal-character
  mapping、set intersection與 piece limit契約。
- `sampleHandler.py` 改用窄 reader helpers，不再 module-scope import `text_category_profiler.core.utilities`；因此 reader 不會
  僅為五個小型轉換載入該 generic module 的 `psutil`、GPUtil、numpy、pandas、setproctitle 等無關 dependencies。
- characterization tests固定 Windows separator、extension case、filename illegal characters、intersection與 piece-limit wrapping；
  AST gate禁止 reader重新依賴 generic utilities，既有 provenance、tokenizer與 sample pipeline tests保持通過。

尚未完成／下次優先事項：

1. **Phase 1 completion gate 尚未達成。** 更新後的 isolated import 已越過 generic utilities／`psutil`，目前第一個可重現
   blocker 是 `MPlogger` module-scope import 的缺少 `numpy`；下批應先建立 reader logger port／lazy default factory，並保留
   caller注入 `MPLOGGER` 的契約，不可用 try/except隱藏 dependency。
2. `reader_utils`只承接 reader實際使用的五個 contracts，不是新的 generic utility dump；其他 callers應繼續使用其既有模組，
   除非 call graph與 dependency boundary證明需要共用。
3. 本批未執行完整 DataConverter CLI或真實模型；isolated `python -c`已證明 cwd保持不變直到 `MPlogger` 的 numpy import
   失敗，但尚未完成整個 reader import，故不宣稱 Phase 1 gate通過。
