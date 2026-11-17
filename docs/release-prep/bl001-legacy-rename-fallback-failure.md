# BL-001：泛用 RenameDir 備援失敗不可假裝成功

`text_category_profiler/core/utilities_path.py` 既有 `RenameDir` 先嘗試
`os.rename`，失敗後才使用 `shutil.copytree` 與 `shutil.rmtree`。
原本 **兩層都失敗** 時僅印出例外，函式仍正常返回，讓呼叫者誤以為
目錄交接已完成。這個缺點不只影響單一 `TaskConnector`，也可能影響
直接呼叫泛用 `RenameDir` 的既有程式。

本次只將**備援複製／刪除來源再次失敗**的例外明確向外拋出：

- `os.rename` 成功：既有結果維持不變
- 原生 rename 失敗，但 `copytree` + `rmtree` 都成功：既有成功行為維持不變
- 備援 `copytree` 失敗：拋出失敗，不刪除原來源
- 備援 `rmtree` 失敗：拋出失敗；已產生的目的複本與可能部分保留的來源**不自動清理、不宣稱交易原子性**

**重大限制**：泛用 `RenameDir` 此次沒有取得跨程序原子性、不覆寫目的地
或跨磁碟的 crash-safe 保證。這些是不同的資料安全問題，不能僅靠
改成 `raise` 解決；使用者 Ctrl+C 留下的舊 WorkPool 目錄也不自動
復原／刪除。

可用私有 fixture 指令驗證：

```sh
python -m unittest -v tests.test_bl001_rename_dir_fallback_failure
```

以上不觸及正式 WorkPool、SQLite 或模型。Hosted Windows／Ubuntu 單元
測試不能取代真實 Windows／網路共享路徑交接驗收。
