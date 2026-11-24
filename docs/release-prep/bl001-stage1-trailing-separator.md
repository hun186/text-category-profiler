# BL-001｜Stage 1 狀態後綴必須接在工作資料夾名稱

DataConverter 規劃時先經 `pick_dataset_directories` 取得資料集基底目錄，
接著以字串串接 `_is_running_DataConverter`。
原行為若基底為 `.../job/`，會得到 `.../job/_is_running_DataConverter`，
誤把 working workspace 建在 job **內部**，而不是與 job 同層的新狀態目錄；
同時可能繞過 Stage 1 的同名獨占建立語意。

本變更在 Stage 1 **規劃階段**只移除尾端斜線（`/`、`\`），
不使用 `os.path.normpath`、不改寫內部正反斜線、不建立或刪除資料。
對空字串、Unix root、Windows drive root、UNC share root、
`.`、`..` 等無法安全接狀態後綴的基底 fail-closed 拒絕。
已有正常基底（沒有尾斜線）的原始目錄及輸出契約保持不變。

使用私人 `TemporaryDirectory` 驗證 StagePlan 工作目錄、真正啟用時
僅建立同層 running 目錄、Ctrl+C 遺留 running 目錄仍拒絕重複使用，
並用文字測試 Windows／UNC 路徑。沒操作正式 WorkPool 或模型。
