# AGENTS.md — `<module name>`

> 使用方式：把本檔複製到真正需要局部指引的子目錄並命名為 `AGENTS.md`。刪除所有不適用段落與占位符，不要把根目錄規則整份複製進來。

## Scope

- 適用路徑：`<relative/path/**>`
- 模組責任：`<one sentence>`
- 不適用：`<nearby directories or responsibilities>`

## Local Map

| 路徑 | 責任 | 主要入口／測試 |
| --- | --- | --- |
| `<path>` | `<responsibility>` | `<entry or test>` |

## Local Commands

只寫與根 workflow 不同或更精確的命令。

| 用途 | 命令 | 狀態 |
| --- | --- | --- |
| `<targeted test>` | `<verified command>` | `<verified date/source>` |

## Local Boundaries and Invariants

- `<dependency direction, schema invariant, security rule, or compatibility boundary>`

## Change Rules

- `<what must be updated together>`
- `<what must not be modified or generated>`
- `<required migration or compatibility behavior>`

## Verification

- 最小必要檢查：`<verified command or procedure>`
- 高風險變更追加：`<broader test or review>`

## Code Review Rules

只列能指出實際 bug、regression、安全或專案特有風險的規則；純格式問題交給 formatter／lint。

- `<behavior to flag>`；安全路徑：`<expected alternative>`。

## 維護注意

- 本檔只寫此子模組與根規則的差異。
- 若規則其實適用整個 repository，移到根 `AGENTS.md` 或相應 `.codex/` 文件。
- 若同目錄建立 `AGENTS.override.md`，它會取代該目錄的 `AGENTS.md` 候選；只有刻意需要 override 時才使用。
