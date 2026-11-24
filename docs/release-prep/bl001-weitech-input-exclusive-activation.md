# BL-001｜WeiTech 輸入目錄的獨占 activation

`PipelinePlan → PipelineContext` 的 root activation 在指定
`WeiTechFormatInputPATH` 時，會把輸入目錄更名為
`<path>_<ExecutionTime>_is_running_AI`，再重建空的輸入目錄。
原預設 `LocalFileSystem.rename` 直接使用 `os.rename`；在 Linux
可能蓋掉另一程序留下的**空**同名 running 目錄，與其他四階段
已收斂的 no-replace 手段不一致。

本批僅修改 root 預設 adapter：確認來源是真實目錄，拒絕 symlink
與 Windows reparse/Junction；拒絕任意已存在（含損壞 symlink）
的 running 目的地，採用共同的 Windows/Linux no-replace
發布 primitive，完成後檢查來源已消失且目的地是真實目錄。
不修改透過 injection 注入的自訂 filesystem callback。
`WeiTechFormatInputPATH` 的尾端正反斜線在 activation
前才去除，避免把 running 目錄錯誤放到輸入目錄內部；
空字串不進入 activation，無法安全接子目錄名的 root path
拒絕。保留命令 CLI 名稱、時間後綴及現有新建空輸入目錄行為。

失敗時嚴禁清理／自動重試／覆寫；跨裝置複製中斷可能留下
來源與部分目的地，屬需另由 operator 核對的資料。
若**改名已成功而重建輸入目錄失敗**，既有設計也沒有完整
回滾交易，本批保留已移動的內容，向上傳遞錯誤，不猜測可重試。

Windows/Ubuntu 私人 `TemporaryDirectory` 實檔測試涵蓋正常
activation、Ctrl+C 遺留目標、source/target symlink、
競爭式目的地、部分跨碟複製、尾端斜線、重建失敗；
不存取正式 WorkPool、模型、SQLite、GPU 或 GUI。
