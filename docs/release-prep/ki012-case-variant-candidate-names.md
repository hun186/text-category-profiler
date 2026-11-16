# KI-012 SQLite 大小寫變體的候選表安全判讀

SQLite 表名在一般情況下不區分大小寫，但原子式 Writer 的候選表格式固定為小寫 `__bl001_stage_` 加 32 個小寫十六進位 UUID 字元。因此離線盤點仍只把完全符合格式的表計入 `candidate_count`。

對於 `__BL001_STAGE_...`、`__Bl001_Stage_...` 或後綴包含大寫字母的變體，會納入 `unexpected_prefix_count`、要求 `REVIEW_REQUIRED`，**不再誤判為沒有候選表**。離線 diff 與 triage 使用相同規則。這只是一個保守的可疑表名分類；其建立者與運行狀態仍未知，任何名稱都不能授權自動 DROP/DELETE。