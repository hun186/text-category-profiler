# Development Workflows

> 類型：Current state。保存可重現的安裝、執行與驗證方式。Codex 不得執行尚未查證的占位命令。

## 環境前提

| 項目 | 要求 | 查證來源 |
| --- | --- | --- |
| 作業系統 | 待初始化 | 待初始化 |
| Runtime 版本 | 待初始化 | 待初始化 |
| 套件管理器 | 待初始化 | 待初始化 |
| 必要本機服務 | 待初始化 | 待初始化 |
| 必要環境變數 | 只列變數名稱與用途，不列值；待初始化 | 待初始化 |

## Canonical Commands

初始化時應從 manifest、CI、Makefile、task runner、官方 README 或實際測試取得命令。無法證實時保留「待確認」，不要憑生態慣例猜測。

| 用途 | 命令 | 工作目錄 | 狀態／最後查證 |
| --- | --- | --- | --- |
| 安裝／同步依賴 | 待確認，禁止執行 | repository root | Unverified |
| 啟動開發環境 | 待確認，禁止執行 | repository root | Unverified |
| Build | 待確認，禁止執行 | repository root | Unverified |
| Format | 待確認，禁止執行 | repository root | Unverified |
| Lint | 待確認，禁止執行 | repository root | Unverified |
| Type check | 待確認，禁止執行 | repository root | Unverified |
| 最小 smoke test | 待確認，禁止執行 | repository root | Unverified |
| 完整 test suite | 待確認，禁止執行 | repository root | Unverified |

## 驗證矩陣

| 變更類型 | 最小必要檢查 | 需要擴大驗證的條件 |
| --- | --- | --- |
| 純文件 | 連結／格式／範例一致性；待初始化 | 文件含可執行命令或契約 |
| 小型單模組邏輯 | 相關單元測試；待初始化 | 影響共用介面或資料流 |
| API／CLI／schema／檔案格式 | 契約測試＋相容性檢查；待初始化 | 對外 consumer 不在此 repo |
| 資料轉換／migration | fixture 驗證＋失敗／回復路徑；待初始化 | 可能改寫正式資料 |
| UI | 靜態／component／E2E／視覺檢查；待初始化 | layout、互動或 browser 相容性改變 |
| 部署／基礎設施 | config validation＋安全的 smoke test；待初始化 | 會觸及外部環境或不可逆資源 |

## 測試資料與外部服務

- 最小 fixture：`待初始化`
- 測試是否允許網路：`待確認`
- 外部服務替代方式：`待確認；mock 必須明確揭露，不得冒充正式成功`
- 測試產物位置與清理方式：`待初始化`

## 常見失敗與替代驗證

若是可重現且尚未解決的限制，詳細記在 `known_issues.md`；本節只保留驗證時該怎麼做。

| 限制 | 首選驗證 | 安全替代 | 不足之處 |
| --- | --- | --- | --- |
| 目前未確認 | 待初始化 | 待初始化 | 待初始化 |

## 完成前檢查

- 使用的是此 repo 已確認的 runtime 與 package manager。
- 先跑最相關檢查，再依風險擴大；不為小改動無條件重裝全部依賴。
- 不把資料庫、雲端、寄信、發布、刪除或 migration 當成無副作用測試。
- 所有未執行或失敗的檢查都在最終回報中明確區分。

## 維護規則

- 命令變更時原地更新表格，附上可查證來源與最後驗證時間。
- 臨時 debug 命令、完整 log 與一次性 workaround 不留在本檔。
- 真正成為長期限制的問題移到 `known_issues.md`；有長期取捨的流程改變移到 `decisions.md`。
