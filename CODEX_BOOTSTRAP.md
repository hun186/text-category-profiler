# Codex 新專案初始化

本檔提供新專案第一次使用範本時的操作方式，包含專案記憶盤點與 README 閘門。初始化完成並提交後可以保留作為重建指南，也可以刪除；`AGENTS.md` 與 `.codex/` 才是日常機制。

## 首次初始化提示詞

從 repository 根目錄啟動 Codex，貼上以下內容：

```text
請依根目錄 AGENTS.md 執行「Codex 新專案首次初始化」。

本次授權範圍：
- 只盤點 repository，並初始化或更新根目錄 AGENTS.md 的 Quickstart 區塊、.codex/*.md，以及依 README 閘門建立或局部補強根目錄 README.md。
- 不修改產品程式碼、測試、設定、依賴或資料。
- 不執行會安裝套件、寫入外部服務、啟動長時間程序或改變資料的命令。

初始化要求：
1. 先閱讀現有 README、manifest、lockfile、主要設定、CI、入口、測試設定與最上層目錄；只在需要時深入。
2. 預設略過 .git、vendor、node_modules、venv、build、dist、cache、datasets、models、logs、outputs、archive 與大型二進位檔。
3. 依 AGENTS.md 的 README 閘門，把根 README 判定為 ADEQUATE、NEEDS_UPDATE 或 MISSING_OR_PLACEHOLDER；保留合適內容，只在後兩種狀態採取對應動作。
4. 若需建立 README，使用 .codex/templates/project-README.template.md 作為檢查骨架，依專案實況刪除不適用段落；若專案目的也無法證實，先停止 README 建立並詢問我。
5. 以程式碼、設定與測試提供的證據填寫 project、workflows、architecture、contracts、memory、decisions、known_issues、backlog。
6. 不適用的章節明確寫「目前不適用」；無法證實的資訊標成「待確認」，不要猜測。
7. 只把已存在且可驗證的設計決策、問題與 backlog 搬入對應文件；不要自行產生願望清單。
8. 將 AGENTS.md Quickstart 的初始化狀態改為 INITIALIZED，填入專案目的、主要技術、主要入口與最快驗證。
9. 對 README、AGENTS.md 與 .codex 文件做一次相互一致性及敏感資訊檢查。

完成時請回報：
- 你辨識出的專案一句話目的與主要資料流。
- README 的判定狀態、保留／更新／建立動作，以及主要證據。
- 寫入或更新了哪些記憶文件。
- 哪些內容是已驗證事實、哪些仍待確認。
- 建議我人工確認的最多五個問題。
```

## 初始化時應採用的證據順序

1. 可執行程式碼與測試。
2. package／build／deployment manifest 與 lockfile。
3. CI 工作流程與實際命令。
4. schema、migration、API spec、CLI parser 或資料模型。
5. 現有 README 與設計文件。
6. 檔名、目錄名或註解只能當線索，不能單獨當成已驗證事實。

## 初始化後的人工檢查清單

- README 是否保留了原本仍正確的內容，且沒有捏造功能、命令、授權或支援狀態。
- 專案目的與非目標是否正確。
- 主要入口、執行方式與最快測試是否真的可用。
- 資料、模型、輸出、憑證或本機設定是否被正確排除。
- 模組邊界與依賴方向是否反映真實設計，而非只依目錄名稱猜測。
- contracts 是否涵蓋真正需要相容的 API、CLI、schema、檔案與跨專案交接格式。
- decisions、known issues 與 backlog 是否只含已證實或已接受內容。

## 日常任務提示格式

日常不需要重貼整套規則。對較複雜任務，可用四段式描述：

```text
目標：要改變的可觀察結果。
上下文：最相關的檔案、功能、錯誤或既有決策。
限制：相容性、安全、範圍與不可變條件。
完成條件：必須通過的測試或可驗證行為。
```

## 修正 Codex 誤解時

若錯誤只涉及當前專案事實，可說：

```text
請先查證我剛才的修正，然後把它更新到最適合的 .codex current-state 文件，避免下次沿用舊資訊。
```

若同一種工作方式或錯誤假設已重複發生，可說：

```text
請把這次教訓濃縮成一條可操作、範圍明確的規則，寫到最接近其作用範圍的 AGENTS.md；不要複製整段歷史。
```

## 大型專案的子模組指引

只有子目錄需要不同測試命令、相依限制、資料安全規則或完成條件時，才從 `.codex/templates/module-AGENTS.template.md` 建立該目錄的 `AGENTS.md`。

Codex 在啟動時會從 repository root 走到目前工作目錄載入指引。若主要工作集中於某個子模組，最好從該子目錄啟動或用 `--cd` 指向它，並要求 Codex列出已載入的 instruction sources，以確認巢狀規則生效。
