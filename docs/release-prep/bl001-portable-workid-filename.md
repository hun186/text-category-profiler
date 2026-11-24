# BL-001｜跨 Windows 與 Linux 的外部 Work-ID 檔名

先前 `validate_external_work_id` 已拒絕路徑分隔符、
冒號（含 ADS）、控制字元、尾隨點／空白及 Windows
保留裝置名稱。仍存在一組 Windows **不可作為一般檔名**
的 ASCII 字元：`< > " | ? *`；Linux 作業環境可能
允許這些單一子目錄名稱，但工作單若被 Windows worker
讀取就會在不同階段失敗。

本批統一跨平台驗證：凡 Work-ID 包含這六種字元之一，
在 WorkPool incoming 認領、明確指定 ID 或備份／交付
**之前**拋出原有 `EXTERNAL_WORK_ID_INVALID`，
不得已開始備份或移動後才發現非法命名。
合法中文、空白內含、括號、連字號與普通點仍保持不變。

Hosted Windows/Ubuntu 以 fake filesystem 驗證
零副作用；不處理歷史已存在的不合法工作單，也不擅自
重新命名或刪除正式 WorkPool 項目。Unicode normalization
與既有跨程序 race 仍需正式環境核實。
