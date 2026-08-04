# Technical Decisions

> 類型：Durable rationale。只記錄存在實質取捨、會約束後續維護的決策；一般程式修改放 `memory.md` 即可。

## Active Decision Index

| ID | 決策 | 狀態 | 日期 | 影響範圍 | 被取代／取代者 |
| --- | --- | --- | --- | --- | --- |
| 目前無已確認決策 | — | — | — | — | — |

## 何時建立 Decision Record

符合多數下列條件時才建立：

- 有兩個以上合理方案與明確取捨。
- 會影響模組邊界、資料模型、契約、安全、相容性、部署或營運成本。
- 未來維護者只看程式碼不容易理解「為什麼」。
- 回復或改變成本不低。

不要為重新命名、單純 bug fix、格式調整、每次拆檔或理所當然的最佳實務建立決策紀錄，除非其中真的存在專案特有取捨。

## Decision Records

目前尚無已確認紀錄。新增時：

1. 從 `.codex/templates/decision-entry.template.md` 複製格式。
2. 使用遞增且不重用的 ID，例如 `ADR-0001`。
3. 將索引更新到本檔頂端。
4. 決策被新決策取代時，不刪除舊紀錄；將狀態改為 `Superseded`，雙向連結 ID。

## 維護規則

- 狀態使用 `Proposed`、`Accepted`、`Superseded`、`Rejected` 或 `Deprecated`。
- 只有 `Accepted` 決策可視為目前設計約束；仍需與實際程式碼交叉查證。
- 大量舊的 Superseded／Rejected 紀錄可移到 `.codex/archive/decisions-YYYY.md`，但 Active Decision Index 應保留必要替代鏈。
- 不記錄秘密、內部帳密或可識別個人的審批資訊。
