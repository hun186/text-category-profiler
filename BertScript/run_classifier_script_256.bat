# 指定你使用哪个GPU，不指定会默认使用所有的GPU
::export CUDA_VISIBLE_DEVICES=3

# 指定你的预训练模型位置
::export MODEL_PATH=chinese_rbt3_L-3_H-768_A-12
# 指定你的输入数据的目录（该目录下，放着前面的三个文件train.tsv, dev.tsv, test.tsv）
::export DATA_PATH=data_set
# 指定你的模型输出目录
::export OUTPUT_PATH=output

::python run_classifier.py --vocab_file=./chinese_rbt3_L-3_H-768_A-12/vocab.txt --bert_config_file=./chinese_rbt3_L-3_H-768_A-12/bert_config_rbt3.json --./init_checkpoint=./chinese_rbt3_L-3_H-768_A-12/bert_model.ckpt --data_dir=./data_set/ --task_name=senti --output_dir=./output/ --do_train=True --do_eval=True --do_predict=True --max_seq_length=512 --train_batch_size=12 --num_train_epochs=8.0> server.log 2>&1 &
::python run_classifier.py --vocab_file=./chinese_rbtl3_L-3_H-1024_A-16/vocab.txt --bert_config_file=./chinese_rbtl3_L-3_H-1024_A-16/bert_config_rbt3.json --./init_checkpoint=./chinese_rbtl3_L-3_H-1024_A-16/bert_model.ckpt --data_dir=./data_set/ --task_name=senti --output_dir=./output/ --do_train=True --do_eval=True --do_predict=True --max_seq_length=256 --train_batch_size=12 --num_train_epochs=5.0> server.log 2>&1 &
::python run_classifier.py --vocab_file=./chinese_rbtl3_L-3_H-1024_A-16/vocab.txt --bert_config_file=./chinese_rbtl3_L-3_H-1024_A-16/bert_config_rbtl3.json --./init_checkpoint=./chinese_rbtl3_L-3_H-1024_A-16/bert_model.ckpt --data_dir=./data_set/ --task_name=senti --output_dir=./output/ --do_train=True --do_eval=True --do_predict=True > server.log 2>&1 &
::python run_classifier.py --vocab_file=./chinese_rbt3_L-3_H-768_A-12/vocab.txt --bert_config_file=./chinese_rbt3_L-3_H-768_A-12/bert_config_rbt3.json --./init_checkpoint=./chinese_rbt3_L-3_H-768_A-12/bert_model.ckpt --data_dir=./data_set/ --task_name=senti --output_dir=./output/ --do_train=True --do_eval=True --do_predict=True> server.log 2>&1 &

::Topic
::python run_classifier.py --vocab_file=./chinese_rbtl3_L-3_H-1024_A-16/vocab.txt --bert_config_file=./chinese_rbtl3_L-3_H-1024_A-16/bert_config_rbtl3.json --./init_checkpoint=./chinese_rbtl3_L-3_H-1024_A-16/bert_model.ckpt --data_dir=./dataset_topic/ --task_name=Topic --output_dir=./output_topic/ --do_train=True --do_eval=True --do_predict=True > server.log 2>&1 &
python run_classifier.py   ^
--vocab_file=./chinese_rbtl3_L-3_H-1024_A-16/vocab.txt ^
--task_name=topic ^
--do_train=True  ^
--do_eval=True   ^
--do_predict=True ^
--data_dir=./dataset_topic/ ^
--bert_config_file=./chinese_rbtl3_L-3_H-1024_A-16/bert_config_rbtl3.json ^
--init_checkpoint=./chinese_rbtl3_L-3_H-1024_A-16/bert_model.ckpt ^
--max_seq_length=256   ^
--train_batch_size=24   ^
--learning_rate=2e-5   ^
--num_train_epochs=3.0   ^
--output_dir=output_topic  ^
> server.log 2>&1 &


::original
::python run_classifier.py --vocab_file=./chinese_L-12_H-768_A-12/vocab.txt --bert_config_file=./chinese_L-12_H-768_A-12/bert_config.json --./init_checkpoint=./chinese_L-12_H-768_A-12/bert_model.ckpt --data_dir=./data_set/ --task_name=senti --output_dir=./output/ --do_train=True --do_eval=True --do_predict=True > server.log 2>&1 &

::python run_classifier.py --vocab_file=./chinese_wwm_L-12_H-768_A-12_tf1/vocab.txt --bert_config_file=./chinese_wwm_L-12_H-768_A-12_tf1/bert_config.json --./init_checkpoint=./chinese_wwm_L-12_H-768_A-12_tf1/bert_model.ckpt --data_dir=./data_set/ --task_name=senti --output_dir=./output/ --do_train=True --do_eval=True --do_predict=True > server.log 2>&1 &
