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
