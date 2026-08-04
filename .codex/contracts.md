# Interface Contracts

> 類型：Current state。記錄需要相容、可被其他模組或系統依賴的介面；不限於 HTTP API。

## 契約範圍

依專案實況保留適用項目：

- HTTP／RPC API
- CLI command、argument、exit code 與 stdout／stderr 格式
- Python／library public API
- Database schema、migration 與 query boundary
- File、dataset、model artifact 或 export format
- Event、queue message、batch handoff 與 webhook
- 跨 repository 的輸入／輸出成果

若目前沒有需穩定維持的對外或跨模組介面，明確寫「目前無已確認的穩定契約」，不要為填表捏造 API。

## 契約索引

| ID | 類型 | 名稱 | Producer／Owner | Consumer | 權威定義 | 穩定性 |
| --- | --- | --- | --- | --- | --- | --- |
| 待初始化 | 待初始化 | 待初始化 | 待初始化 | 待確認 | `待初始化` | 待確認 |

## 通用相容性規則

- `待初始化：例如欄位新增可向後相容、刪除／改名需版本化。`
- 錯誤表示與重試語意：`待初始化`
- 時間、timezone、encoding、locale 與 identifier 規則：`待初始化`
- 敏感欄位與遮蔽規則：`待初始化`

## 契約詳細內容

每個重要契約使用穩定 ID，並依實際類型保留必要欄位。

### `待初始化：CONTRACT-001 名稱`

- 類型：`待初始化`
- 狀態：`Draft | Stable | Deprecated | Removed`
- 權威定義：`待初始化，例如 schema / code / OpenAPI / parser / test`
- Producer／Owner：`待初始化`
- Consumer：`待確認`
- 輸入：`待初始化`
- 輸出：`待初始化`
- 驗證與約束：`待初始化`
- 錯誤／exit code／失敗語意：`待初始化`
- 版本與相容性：`待初始化`
- 安全與敏感資訊：`待初始化`
- 契約測試：`待初始化`

## Deprecated／Migration

| 舊契約 | 替代契約 | 過渡方式 | 移除條件／日期 |
| --- | --- | --- | --- |
| 目前沒有已確認項目 | — | — | — |

## 維護規則

- 介面實作改變時同步更新 current contract 與 contract test。
- 不以 README 範例取代 schema、parser 或測試等權威定義。
- 若需要破壞性變更，先記錄 consumer、遷移路徑與相容性決策；必要時新增 `decisions.md` 紀錄。
- 過時細節不追加日期流水帳；原地更新，並透過 Git 或 decision 追溯原因。
