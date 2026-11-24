# BL-001｜Linux Work-ID 完成交接的擁有權順序

問題：舊版 `DeliveryManager.backup_and_complete` 在將
`AutoBertClassify_Processing/<work-id>` 移到
`AutoBertClassify_Processed/<work-id>` **之前**，便呼叫
`walk(completed)` 並 `chown` 其後代。如果另一工作程序
或中斷紀錄已佔有該完成目錄，即使接下來的 no-replace move
會拒絕碰撞，所有權操作也可能先動到別人的已完成資料。

新邊界：
- 備份成功後，先建立 processed 父目錄；Linux 僅對
  `processing`、`processed` 父目錄與本次
  `processing/<work-id>` 來源執行前置 ownership。
- 以既有 `LegacyFileSystem.move` 做不覆寫移交；
  失敗仍傳遞原例外、禁止 Complete log、不做補償重試。
  **未成功移交時，絕不巡訪 completed 工作單**。
- 只有 move 已完成後才對新的
  `completed/<work-id>` 做 `walk` + `chown`。
  此時是不可回滾的 post-commit 操作：若巡訪、chown 或錯誤
  報告 callback 失敗，保留移交結果、向既有 reporter
  回報可回報的錯誤，且不重新執行 move；正常 complete
  日誌依既有 committed-move policy 繼續。
- Windows 的 ownership 流程仍不執行此段。

新跨平台 mock filesystem 測試驗證 move 與 walk 的先後、
碰撞前不碰已完成工作單、後置 chown 或 reporter 故障
仍只 move 一次，並重用既有 WorkPool/Delivery 測試。

**不代表已做 Linux 正式檔案權限、ACL、不同 UID/GID、
網路共享或 WorkPool 的實機驗收。** Backup、move 與
chown 仍不是單一原子交易；中斷後必須人工核對，不自動清理。
