# BL-001｜子程序失敗紀錄器不可取代原始 exit code

根流程的 `RootFailFastPolicy.check` 先呼叫
`failure_reporter(stage_name, returncode, command)`，
再依 returncode 拋出 `RuntimeError` 並停止下游階段。
若 reporter 自身因 log 權限、磁碟空間、外部 IO 等問題
拋出一般例外，原始 child exit code 就被另一個錯誤取代，
不利於失敗位置診斷和中斷恢復判斷。

本批僅對 reporter 呼叫加上 best-effort `try/except Exception`：
- 子程序原非 0 exit code 仍原樣表現在根流程錯誤。
- Exit 130、-2、Windows control-C-like exit 仍**僅標示
  interruption-like/unconfirmed**，不能據此認定真人 Ctrl+C。
- reporter 正常時依舊收到 stage、code、原 command
  三個既有參數；returncode 0 時完全不觸發 reporter。
- 若 reporter 本身被 KeyboardInterrupt 中斷，仍按使用者
  中斷正常傳播，不轉成一般子程序失敗。
- 不嘗試恢復失敗 reporter 的資料、不重跑子程序、不修改
  WorkPool，不變更原有 exception message 或 Stage 順序。

Windows／Ubuntu 隔離 fault injection 搭配原
`tests/test_process_runner.py` 驗證。尚未做正式
Windows/Linux 分類 child process、真實 IO 或 GUI 實機驗收。
