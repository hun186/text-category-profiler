# KI-012 Stage 原子替換的既有索引保護

Stage Writer 原本會在同一筆交易中刪除舊的 `sampleSrc` 再依 pandas 的輸出結構建立新表與索引，因此任何額外的手工索引、Unique constraint、Partial index 或改過排序／Collation 的索引，都可能在成功提交後無聲消失。

現在取得 `BEGIN IMMEDIATE` 寫入鎖後，會在 DROP 之前只讀取原有 `sampleSrc` 的 `PRAGMA index_list`、`PRAGMA table_info`、`PRAGMA index_xinfo`，接受原有 Stage-local 形態的 `text_Index` 和 `ix_sampleSrc_*`，拒絕未知、UNIQUE／partial、expression、DESC 或 NOCASE 等不相容索引。拒絕替換時應回滾本次交易，只清理由本次寫入者產生的候選表，原始資料、所有索引與約束保持不變。

這是**保守拒絕替換**，不是自動遷移外部自訂索引。若確實需要對現有資料庫做 schema 變更，應先在隔離複本驗收相依性，再另立遷移流程；不能直接跳過此保護。正式 WorkPool 尚未進行實機驗證。