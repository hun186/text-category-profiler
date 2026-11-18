# BL-001｜外部工作單移交不可以在同名目錄下重複巢狀放入

`TCFMain.py` 建立的 `LegacyFileSystem.move` 原本使用
`shutil.move(source, destination)`。當完成／處理中的同名工作單目的地
已經是目錄時，`shutil.move` 會將來源移**進**該目錄，而不是拒絕。
Ctrl+C 的工作單殘留目錄不能自動重用或合併。

此次僅更改正式 `LegacyFileSystem.move` 工作單目錄搬移：

- 來源必須是真實目錄，拒絕符號連結與 Windows Junction；
- 目的地任何類型已存在（含壞掉的 symlink）即拒絕；
- 共用 Stage 專用 `_handoff_rename_noreplace`：Linux
  `renameat2(RENAME_NOREPLACE)`、Windows `os.rename`；
- 跨磁碟部分複製／刪除失敗時，postcondition 不能成立就報錯，
  保留現場，不繼續聲稱成功；無自動刪除或重新執行；
- `WorkPoolManager.acquire` 失敗直接中止；現有
  `DeliveryManager.backup_and_complete` 仍沿用錯誤回報後捕捉行為，
  **此 PR 不宣稱完成端已把錯誤向根入口上拋**，應列入後續檢查。

只使用私人 `TemporaryDirectory` 模擬 WorkID，不對正式工作池做
搬移、複製、刪除。完成進度仍以 GitHub CI／Review 為先，
實際內網／跨磁碟驗收待另行確認。
