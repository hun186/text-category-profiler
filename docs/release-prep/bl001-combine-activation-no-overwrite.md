# BL-001｜Stage 3 啟動時不可覆寫既有 running 工作目錄

正式的 `BertScript/CombineTestResult.py` 原本以 `os.rename`
將 `*_rdy_for_CombineTestResult` 轉成 `*_is_running_CombineTestResult`。
在 Linux/POSIX，如果其他程序剛建立空目的目錄，`os.rename`
可能將其替換；即使上一批已保護了合併**完成**的交接，也不代表
**開始合併**的這條路線已安全。

本批將正式入口的 `activate_rename` adapter 換成
`_result_combination_activate`，共用既有無覆寫搬移原語：

- 確認 ready 來源是真實資料夾且不為 symlink、Windows Junction/reparse。
- 若 running 目的地已存在，停止、保留兩邊，不開始合併運算。
- Linux 用 `renameat2(RENAME_NOREPLACE)`，Windows 使用原生
  不覆寫既存目錄的 `os.rename`；不支援安全語意的平台拒絕。
- 搬移後確認 ready 名稱消失且 running 真實資料夾存在。
  `EXDEV` 跨磁碟複製仍**非原子交易**，若部分完成，拋錯保留現場。
- `activate_result_combination` 及完成階段的目錄名稱轉換只接受
  **basename 最後**的正式 suffix；父資料夾碰巧含相同字串不再被更名。

本批不改變 `ResultCombinationPlan` 資料格式、回呼注入介面、
正常資料表/schema、分類模型、使用者先前 Ctrl+C 留下的工作目錄，
也不將一般 helper 的所有外部呼叫者統一修改。保留
`activate_result_combination(plan, rename=...)` 的顯式注入行為；
只有正式入口明確改用受保護 adapter。

驗證：
`python -m unittest -v tests.test_bl001_combine_activation_no_overwrite tests.test_result_combination_stage`

使用 `TemporaryDirectory` 的假結果檔，不接觸正式 WorkPool、
模型或 GPU；Host CI 不能代替正式 Windows／網路共享磁碟實機驗收。
