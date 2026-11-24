# BL-001｜Git 歷史相容入口證據的跨平台位元組一致性

已存在的 `bl001_package_census.py` 能在 Windows checkout
經 `core.autocrlf` 產生 CRLF 時，僅針對 13 筆已登錄
legacy path 以記憶體複本校正 CRLF → LF，並要求校正後
**Git blob SHA 和原長度兩者皆完全一致**。
但另一套 `bl001_legacy_root_audit.py` 仍直接把 Windows
工作樹 bytes 與 Git manifest 比對，可能產生偽陽性失敗。

本批收斂成共同的 `scripts/bl001_git_blob_identity.py`：
`git_blob_sha` 與 `legacy_git_blob_bytes` 是兩套稽核
共同引用的唯一實作；原 `census.git_blob_sha`、
`census.legacy_git_blob_bytes` 與
`legacy_audit.blob_sha` 名稱透過匯入保留相容。

- 優先接受原始檔案 SHA + 大小完全吻合。
- 只有在原樣不合時，對**已核實的 legacy manifest**
  在記憶體內試算 CRLF → LF；符合原 SHA + 大小才接受。
- 其他損壞、編輯、裸 CR、錯誤原長度皆仍失敗。
- 不修改、重寫、讀取正文以外的外部資料，
  不 import 任何 8 個 legacy 相容入口，並保持 Git
  tracked original SHA 作為唯一權威。
- 外部、動態與非 Python caller 仍是 unverified；
  **跨平台 blob PASS 並不授權刪除任何 legacy 檔案。**

新增 Windows/Ubuntu 獨立 CI，驗證兩套報告都對相同
13 筆歷史檔案判定一致，且假修改不能冒充 Git checkout 轉碼。
