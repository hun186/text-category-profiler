# BL-001：Stage 3 分類結果交接不可覆寫

`BertScript/CombineTestResult.py` 完成分類結果整合後，會將
`*_is_running_CombineTestResult` 交付至 `*_rdy_for_TestResultVis`。
原路線直接呼叫泛用 `RenameDir`，在 Linux/POSIX 的 `os.rename`
可能覆寫其他 worker 剛建立的空目的地，且在跨磁碟複製部分成功時可能留下
來源與目的地並存。

本次重用 Stage 1 已建立的 `_handoff_rename_noreplace` 安全搬移：
Linux 採 `renameat2(RENAME_NOREPLACE)`，Windows 原生 `os.rename` 拒絕
既存目的地；`EXDEV` 才使用不可併入既存目的地的 `copytree` 備援。
**跨磁碟搬移非原子**，部分複製失敗不得聲稱交接完成，亦不會自動清理。

## 交接判定

- 確認來源 basename 精確以 `_is_running_CombineTestResult` 結尾，
  且目的地必須是同一資料集的 `_rdy_for_TestResultVis`。
- 拒絕原始來源不存在、連結或 Windows junction/reparse，並拒絕已有目的地；
  原生不可覆寫搬移則額外防止檢查後競爭程序建立目的地。
- 搬移後來源須消失、目的地須為實體資料夾；否則報錯且保留現場，
  不執行下階段、不嘗試恢復或刪除資料。
- 已完成交接後，單純寫入成功日誌的失敗不得觸發第二次搬移。

`BertScript/result_combination_stage.py` 的注入式 adapter 介面、
`_rdy_for_CombineTestResult` → `_is_running_CombineTestResult` 的
**啟動階段 rename**、合併運算及結果 schema 均不在本次修改範圍。
若要強化啟動階段的多程序競爭行為，須另行查核獨立測試與合併門檻。

回歸：`python -m unittest -v tests.test_bl001_combine_handoff_no_overwrite tests.test_result_combination_stage`

Windows／Ubuntu CI 只在私人 `TemporaryDirectory` 測試，
不能替代正式 WorkPool、網路磁碟、真實模型與完整 GUI 驗收。
