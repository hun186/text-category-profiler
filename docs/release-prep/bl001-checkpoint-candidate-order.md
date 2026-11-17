# BL-001｜PyTorch 模型 checkpoint 候選順序與完整性

## 原先問題

在 `text_category_profiler/pipeline/TCF_utils.py` 的
`inspect_pytorch_output_candidate()` 中，`checkpoint-*` 使用字串反向排序，
可能把 `checkpoint-9` 排在 `checkpoint-10` 前面。此外，檢查僅看
checkpoint 目錄內容的檔名，空權重檔、同名資料夾及不完整名稱也可能
造成誤判或例外。

## 新增規則

- 僅處理完整符合 `checkpoint-<非負整數>` 名稱的實體子目錄。
- 依數值訓練步數由大到小檢查；較新 checkpoint 無可用權重時，
  再依序檢查較舊 checkpoint。
- 支援原本的 `pytorch_model.bin` 及 `model.safetensors`，並要求
  候選為非空檔案；不會修改或刪除任何模型。
- 保持原本 `PytorchOutputInspection`、成功回傳與拒絕原因介面；
  沒有改動 `TF15Bert` 或使用者明確指定 `--modelDir` 的政策。

## 驗證界線

`python -m unittest -v tests.test_model_directory_selection`
只在私人 `TemporaryDirectory` 用小型假 checkpoint 檔測試目錄順序、
完整性與選擇結果，並由 Windows／Ubuntu CI 驗證。

**這不是**真實 PyTorch checkpoint 是否能載入、權重是否與 tokenizer
匹配、GPU/CUDA、內網 WorkPool、GUI 或正式部署驗收。
