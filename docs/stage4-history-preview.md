# Stage 4 已儲存結果：安全歷史預覽（第一階段）

`text-category-profiler` 的原版完整 Stage 4 必須先執行分析計算，
且在啟動過程改名 `_rdy_for_TestResultVis → _is_running_TestResultVis`，
網頁結束後可能改名為 `_rdy_for_Spike`。因此，**請勿單純將歷史資料夾
手動改名來騙過正式工作池選取器**。

## 啟動（Windows / Anaconda Prompt）

先更新至包含此功能的版本，在專案根目錄執行：

```bat
run-stage4-history-preview.bat
```

或：

```bat
python BertScript\Test_result_Vis.py --history-preview --workpool WorkPool -p 8060
```

在同一台電腦開啟 `http://127.0.0.1:8060/`。
獨立歷史預覽預設使用 8060，和可能仍在 8059 執行的完整 Stage 4 分開。
只綁定 `127.0.0.1`，不使用公開網路介面。

## 目前實際提供的功能

- 列出符合 `dataset_<時間>_..._pt<port>_rdy_for_Spike` 和
  `..._is_running_TestResultVis` 的歷史資料夾，可下拉選擇。
- 按目前檔案實況標示已完成／可能中斷、資料庫缺漏；單憑資料夾名稱
  **不能證明結果內容完整**。
- 只讀取兩個常用已存結果資料庫：
  `DFPreambleCols_df_ALL.sql3` 和 `test_results_verification.sql3`。
  直接選擇 SQLite 資料表，分頁讀取（每頁至多 50 列、前 24 欄、
  每個欄位值至多 600 字元），無需再次建立 441 秒分析資料表。
- 保留同埠獨立 Jaal 進階檢視、根分類搜尋、中文翻譯、
  網狀／階層等模式，以及按需載入的輕量 Cytoscape 分類樹。
- 預覽模式不呼叫正式 Stage 4 工作流程，不重新計算或匯出
  `DFPreambleCols_df_ALL`，不重命名 WorkPool 資料夾，也不執行模型。

## 中斷與資料庫安全界線

`_is_running_TestResultVis` 有可能是真正仍在寫入，也可能是先前
例外或 Ctrl+C 所遺留。預設**不讀取**這些資料；須先由使用者確認
其他程序不再寫入，勾選明確的確認框，才能讀取存在的結果。

缺任何一個必要 SQLite 資料庫、存在 `-wal`、`-shm` 或
`-journal` sidecar、資料庫損毀、資料表不存在或路徑有疑義時，
預覽會拒絕開啟該結果，絕不進行寫入或修復。
SQLite 以 `mode=ro&immutable=1` 開啟，避免在 Windows 原資料
目錄建立鎖定、journal 或 shm；**不要在資料庫仍有寫入者時勾選確認**。

在一個終端機執行 GUI，另一個終端機可跑不啟動模型的測試：

```bat
python -m unittest -v tests.test_stage4_history_preview
```

## 尚未提供（請勿誤認為原版完整 Stage 4）

第一階段是**已儲存資料的唯讀檢視**，並非原版 4,000 多行 Stage 4
所有互動統計圖表、排序處理、匯出、重新計算或工作池交接的重現。
部分原始圖表依賴額外統計與全域狀態，未確認其讀取純度前不會接入。
因此新頁面保留 Jaal，提供主要已存分析表格的分頁檢視，
但**不宣稱原版 Stage 4 全功能已恢復**。下一階段將評估可從
既存 SQLite 安全還原的圖表，再個別加入、各自驗證無資料寫回。
