# BL-001｜外部 WorkPool 備份目的地不得是 symlink／junction

`DeliveryManager.backup_and_complete` 在最後移交工作單前，
會呼叫 `LegacyFileSystem.backup(BertDatasetSubDir=..., DesDir=WorkPool/work-id)`。
如果此 Work-ID 的目的地是 symlink、Windows Junction 或損壞連結，
既有備份工具可能跟隨連結，把輸出寫入工作池外部的其他目錄。

本 PR 在**實際備份 adapter 的副作用前**加入 `DesDir` 預檢：

檢查前先只對目的地**字串副本**移除尾端 `/` 或 `\\`，避免 Linux
`lstat("job/")` 跟隨目錄 symlink 而漏判；傳給既有備份工具的原始
`DesDir` 字串不改寫，且拒絕空／drive root／UNC share root。


- 現有目的地葉節點必須是真實目錄，拒絕普通檔案、有效/損壞 symlink、reparse/Junction；
- `DesDir` 為空、非字串或不合法 path-like 也拒絕；
- 沒有 `DesDir` 的既有一般備份模式照舊；
- 尚不存在的 `DesDir` 保留既有代理建立語意，本 PR 不擅自改變其他任務的備份契約；
- 不做刪除、覆寫、修復或自動重試。

**限制：** 這是目前葉節點的 fail-closed 預檢，仍不是持有 fd 的不可競爭
完整路徑驗證；父層 symlink、檢查後被另一程序替換的 TOCTOU
競爭、網路儲存實機行為不在本 PR 解決範圍。若正式工作池原本刻意讓
**Work-ID 子目錄**是 symlink/junction，則新政策會拒絕該工作單備份，
必須在實機部署前另做相容性確認，而不是在此偷偷自動解參照。

測試只使用私人 TemporaryDirectory 和無作用的 backup 回呼，
驗證 Windows/Ubuntu、有效/損壞連結、一般目錄、正常與無 DesDir 的
向下相容行為。從未操作正式 WorkPool、SQLite、模型或 GPU。
