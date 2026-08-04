# Project Memory

> 類型：Recent durable context。不是聊天紀錄或完整 changelog；只保存能讓後續任務少走彎路的近期成果。

## Current Focus

- 初始化狀態：`UNINITIALIZED`
- 目前工作焦點：`待初始化`
- 最近確認可工作的路徑：`待初始化`
- 需要延續的相容性／限制：`待初始化`

Current Focus 最多保留 5～8 個短項目。專案長期身份放 `project.md`，完整架構放 `architecture.md`，不得在此重複整份內容。

## Recent Outcomes

目前尚無已記錄成果。初始化完成後，用 `.codex/templates/memory-entry.template.md` 的格式新增；最多保留最近 10 筆有持久參考價值的項目。

## Open Handoffs

只列已開始但尚未完成、或下一個任務必須知道的交接。單純構想放 `backlog.md`，未證實問題放「待確認」而非假裝已知。

- 目前無已確認項目。

## Archive Index

- 詳細索引見 `.codex/archive/README.md`。
- 一般任務不讀 archive，除非 Current Focus／Recent Outcomes 明確引用或使用者要求追溯。

## 記錄準則

值得記錄：

- 任務的可觀察結果與重要範圍。
- 實際通過的驗證，或具體未驗證原因。
- 後續修改會用到的相容性、不變條件或教訓。
- 尚未完成但已存在的交接。

不要記錄：

- 完整命令輸出、聊天逐字稿與每一步操作。
- 可直接從 Git diff 得知的瑣碎檔名清單。
- 已失效的猜測、一次性 typo、無後續價值的失敗命令。
- 尚未接受的改善靈感。
- 秘密、個資、真實連線資料或敏感 payload。

## 濃縮規則

符合任一條件時濃縮：超過 10 筆 Recent Outcomes、約 200 行、24 KB，或內容出現明顯重複／失效。

1. 更新 Current Focus 為目前仍有效的摘要。
2. 近期 5～10 筆留在 active memory。
3. 將仍有追溯價值的較舊條目移到 `.codex/archive/memory-YYYY-MM.md`；不要複製整份 active memory。
4. 更新 `.codex/archive/README.md`。
5. 可由 Git 歷史充分回答且沒有持久價值的細節直接移除。
