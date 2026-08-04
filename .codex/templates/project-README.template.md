# `<Project Name>`

> 使用方式：這是 README 內容檢查骨架，不是必須逐段照抄的固定格式。Codex 只有在根 `README.md` 缺少、近乎空白或只是無關占位文字時才以此建立；若已有實質內容，應保留原結構並做最小補強。刪除所有不適用段落與占位符。

`<用一至三句話說明專案解決的問題、主要使用者，以及目前是原型、開發中或可用狀態。只寫有證據的內容。>`

## 目前狀態

- 階段：`<Prototype | In Development | Stable | Maintenance；無法證實時寫「待確認」>`
- 已具備：`<目前實際存在且可驗證的能力>`
- 尚未具備／限制：`<會影響使用者預期的重要限制>`

## 主要功能或範圍

- `<功能或責任；不得把規劃中功能寫成已完成>`

## 快速開始

### 前置需求

- `<runtime、版本、系統工具或服務；附證據來源可連到 manifest>`

### 安裝

```text
<已由 repository 證實的命令；無法證實時不要猜，改以文字標示待確認>
```

### 執行

```text
<已證實的最小啟動或 CLI 命令>
```

### 驗證

```text
<最快且安全的 smoke test、test、lint 或 build 命令>
```

## 設定

只列環境變數或設定鍵的名稱、用途與安全的示例格式，不得放入真實值。

| 名稱 | 必要性 | 用途 | 預設／範例 |
| --- | --- | --- | --- |
| `<NAME>` | `<Required / Optional>` | `<purpose>` | `<non-secret example or none>` |

## 輸入、輸出與資料邊界

- 主要輸入：`<verified input>`
- 主要輸出：`<verified output>`
- 不應提交 Git：`<datasets, models, secrets, local outputs, etc.>`
- 最小測試資料：`<fixture location or pending>`

## Repository 結構

只列會幫助使用者或維護者找到入口的主要路徑，不貼完整目錄樹。

| 路徑 | 用途 |
| --- | --- |
| `<path>` | `<responsibility>` |

## 文件

- 架構：`.codex/architecture.md`（若此文件適合公開給一般使用者，另建立或連結正式架構文件）
- 開發與測試：`.codex/workflows.md`
- 介面契約：`.codex/contracts.md`

## 已知限制

- `<只列已證實且會影響使用的限制；詳細追蹤可連到 .codex/known_issues.md>`

## 授權

`<只有 repository 已有 LICENSE 或使用者明確指定時才寫；否則刪除此節，不能自行選擇授權。>`

## 建立前檢查

- 專案名稱、目的與狀態有 repository 或使用者要求可支持。
- 安裝、執行與驗證命令來自可查證來源，未把「通常如此」當成事實。
- 規劃中能力與現有能力清楚分開。
- 沒有秘密、個資、內部位址、真實連線值或敏感輸出。
- 沒有捏造 license、徽章、版本、平台、相容性、效能或部署狀態。
- README 與 `AGENTS.md` Quickstart、`.codex/project.md`、`.codex/workflows.md` 沒有互相矛盾。
