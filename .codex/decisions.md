# Technical Decisions

> 類型：Durable rationale。只記錄存在實質取捨、會約束後續維護的決策；一般程式修改放 `memory.md` 即可。

## Active Decision Index

| ID | 決策 | 狀態 | 日期 | 影響範圍 | 被取代／取代者 |
| --- | --- | --- | --- | --- | --- |
| `ADR-0002` | Python package 使用 `text_category_profiler` namespace | Accepted | 2026-08-06 | Python package、imports、stage boundaries | 取代 `ADR-0001` |
| `ADR-0001` | 跨 stage 共用工具使用 `tcf_utils` namespace | Superseded | 2026-08-06 | Python shared utilities、imports、stage boundaries | 被 `ADR-0002` 取代 |

## 何時建立 Decision Record

符合多數下列條件時才建立：

- 有兩個以上合理方案與明確取捨。
- 會影響模組邊界、資料模型、契約、安全、相容性、部署或營運成本。
- 未來維護者只看程式碼不容易理解「為什麼」。
- 回復或改變成本不低。

不要為重新命名、單純 bug fix、格式調整、每次拆檔或理所當然的最佳實務建立決策紀錄，除非其中真的存在專案特有取捨。

## Decision Records

### ADR-0002：Python package 使用 `text_category_profiler` namespace

- **狀態**：Accepted
- **日期**：2026-08-06
- **背景**：專案已由 TopicClassification 改名為 `text-category-profiler`；`tcf_utils` 中的 `tcf` 是舊名稱縮寫，無法讓新維護者直接理解它與目前專案的關係。
- **決策**：根目錄 Python package 與 imports 統一使用 `text_category_profiler`；repository 名稱仍使用連字號 `text-category-profiler`。本次不同時改名 `TCFMain.py`、`TCF_Params/` 或 `TCF_utils.py`，以維持現有 CLI 與 stage 相容性。
- **理由**：完整專案 namespace 比歷史縮寫更容易理解，也不會與通用的頂層 `utils` package 衝突；並可在未來容納不屬於 utility 的 application modules。
- **影響**：active code 必須以 `text_category_profiler.<domain>.<module>` 匯入。後續依 `.codex/text-category-profiler-package-migration.md` 收斂模組職責並漸進淘汰 path injection。
- **重新檢視條件**：若未來採用 `src/` layout，可將此 package 搬至 `src/text_category_profiler/`，但不需再變更 public namespace。

### ADR-0001：跨 stage 共用工具使用 `tcf_utils` namespace

- **狀態**：Superseded by `ADR-0002`
- **日期**：2026-08-06
- **背景**：`PythonModule/utils/` 透過 `PackageImport.py` 加入 `sys.path`，再由多個 stage 使用泛用的 `utils` namespace。候選方案包括根目錄 `utils`、完整應用 namespace `text_category_profiler`，以及專案限定的 shared package `tcf_utils`。
- **決策**：當時採用根目錄 `tcf_utils` 作為跨 stage helper namespace。
- **理由**：相較泛用 `utils`，`tcf_utils` 可降低 import 衝突，並維持當時以 stage scripts 為入口的結構。
- **影響**：此 namespace 已由 `ADR-0002` 取代；不得再對 active code 新增 `tcf_utils` imports。
- **重新檢視條件**：已觸發；專案改名後，`tcf` 縮寫不再能清楚表達目前專案名稱。

新增其他紀錄時：

1. 從 `.codex/templates/decision-entry.template.md` 複製格式。
2. 使用遞增且不重用的 ID，例如 `ADR-0001`。
3. 將索引更新到本檔頂端。
4. 決策被新決策取代時，不刪除舊紀錄；將狀態改為 `Superseded`，雙向連結 ID。

## 維護規則

- 狀態使用 `Proposed`、`Accepted`、`Superseded`、`Rejected` 或 `Deprecated`。
- 只有 `Accepted` 決策可視為目前設計約束；仍需與實際程式碼交叉查證。
- 大量舊的 Superseded／Rejected 紀錄可移到 `.codex/archive/decisions-YYYY.md`，但 Active Decision Index 應保留必要替代鏈。
- 不記錄秘密、內部帳密或可識別個人的審批資訊。
