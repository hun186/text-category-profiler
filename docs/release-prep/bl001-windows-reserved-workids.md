# BL-001｜外部 Work-ID 的 Windows 保留裝置名稱

Work-ID 會同時被當成 Linux 與 Windows 的工作資料夾名稱，
並用於外部工作單的 acquisition、backup 和最終完成交接。
先前 `validate_external_work_id` 已拒絕 `/`、反斜線、冒號、
目錄特殊項、尾端空白／句點及控制字元，但 Windows 還有
不需路徑分隔符就能觸發裝置別名的 DOS 裝置名稱。

本批在**所有平台**的同一個純詞法入口拒絕 `CON`、
`PRN`、`AUX`、`NUL`、`CONIN$`、`CONOUT$`，
以及 `COM1～COM9`、`LPT1～LPT9`（包括 Windows
也視為數字 1～3 的上標符號 `¹²³`）。即使是
`CON.txt`、`lpt9.backup` 也拒絕；大小寫不敏感。
`CONNECTION`、`COM10`、`COM0`、正常中文、
Unicode、內部空白、合法延伸副檔名的 Work-ID 仍可使用。

- 已明確提供的 Work-ID 在任何 directory listing／檔案操作前驗證。
- 從外部列表選出的 Work-ID 在建立 processing 資料夾／移動前驗證。
- 交付備份及 processing → processed 前先驗證。
- 空字串仍表示原有無外部工作單模式，並不變更其契約。

這是避免平台間隱式路徑別名的結構驗證，不掃描、不更名、
不自動修復正式 WorkPool 舊資料，也不試圖自動判定
已存在保留名稱的外部工作單應如何遷移。
Windows/Ubuntu 使用 fake filesystem 進行隔離驗證，
不執行分類、SQLite、GPU 或 GUI。
