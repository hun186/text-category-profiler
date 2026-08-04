call activate TF1.5

python BertScript/run_classifier.py   ^
--vocab_file=BertScript/chinese_rbtl3_L-3_H-1024_A-16/vocab.txt ^
--task_name=topic ^
--do_eval=False   ^
--bert_config_file=BertScript/chinese_rbtl3_L-3_H-1024_A-16/bert_config_rbtl3.json ^
--init_checkpoint=BertScript/chinese_rbtl3_L-3_H-1024_A-16/bert_model.ckpt ^
--max_seq_length=256   ^
--train_batch_size=24   ^
--learning_rate=2e-5   ^
--num_train_epochs=3.0   ^
--do_train=False ^
--output_dir=BertScript\output_20230529110733_TF15Bert_Using_20230529160904/  ^
--do_predict=True ^
--keep_checkpoint_max=1 ^
--data_dir=WorkPool\dataset_20230529160904_TF15Bert_pt8060_is_running_RunClassfier/  ^
> RunClassfier.log 2>&1 & 

