from PackageImport import PackageImporter
PackageImporter.proc()
import setproctitle

import os
import torch
import re
import math
import json
import platform

from time import sleep
from tqdm import tqdm, trange

#import numpy as np
#from sklearn.metrics import mean_absolute_error

from sklearn.metrics import precision_recall_fscore_support
from sklearn.metrics import accuracy_score
#from transformers import TFXLMRobertaModel
from transformers import BertModel
from transformers import AutoTokenizer
from transformers import pipeline
from transformers import Trainer
from transformers import AutoModelForSequenceClassification
from transformers import TrainingArguments

from utils.utilities import SplitList
from utils.utilities import flattenList
from utils.utilities import SortedDictWithValue
from utils.MP_utils import MPlogger
from utils.MP_utils import multicoreJob
from utils.TCF_utils import ClassfierOptionParser
from utils.TCF_utils import datasetDirOutputDirPickers
from utils.TCF_utils import get_base_model_checkpoint
from utils.DB_utils import sqlite3Query
from utils.TextClassfier_utils import getTopicLabelList


class classifierJob:
    def __init__(self,testSet,finetuned_checkpoint,
                 device=0,batch_size=8,return_all_scores=False,
                 max_length=180):
        self.testSet = testSet
        self.finetuned_checkpoint = finetuned_checkpoint
        self.device = device
        self.batch_size = batch_size
        self.return_all_scores = return_all_scores
        self.max_length = max_length
    def show(self):
        print(f"The length of testSet is {len(self.testSet)}")
    def proc(self):
        classifier = pipeline("text-classification", 
                              model=self.finetuned_checkpoint,
                              tokenizer=self.finetuned_checkpoint, 
                              truncation=True,max_length=self.max_length,
                              device=self.device,
                              batch_size=self.batch_size,
                              return_all_scores=self.return_all_scores
                              )
        return classifier(self.testSet)
    
def LoadSamples(
        sql3File,label2id={},istest = False,nSampleUPD = math.inf):
    #sqlCols = ['OutLabel','text']
    print(f"Loading data from {sql3File}, istest = {istest}")
    query = 'SELECT Count(*) FROM sampleSrc;'
    totalrow = sqlite3Query(sql3File,query = query, ListForm=True)[0]
    if nSampleUPD < totalrow:
        print("="*50)
        print(f"nSampleUPD {nSampleUPD} < #input samples {totalrow}, LoadSamples will only load {nSampleUPD} samples")
        print("="*50)
        totalrow = min(totalrow,nSampleUPD)
    samples = []
    progress = tqdm(total=totalrow)
    MES = f"Loading samples from {sql3File}"
    print(MES)
    cnt = 0
    if istest:
        sqlCols = ['text']
        colList=','.join(sqlCols)
        query = f'SELECT {colList} FROM sampleSrc;'           
        cur = sqlite3Query(sql3File,query = query, ListForm=False)
        for qures in cur.fetchall():
        #cur = sqlite3Query(sql3File,query = query, ListForm=True)
        #for qures in cur:
            progress.update(1)
            samples.append(qures[0])
            cnt += 1
            if cnt >= nSampleUPD:
                break
            
    elif not istest:
        if label2id == {}:
            print("Input label2id is {}. But for loading training \
                  or validation dataset, the label2id dict is NEEDED. Abort.")
            raise Exception
        sqlCols = ['OutLabel','text']
        colList=','.join(sqlCols)
        query = f'SELECT {colList} FROM sampleSrc;'           
        cur = sqlite3Query(sql3File,query = query, ListForm=False)
        for qures in cur.fetchall():
        #cur = sqlite3Query(sql3File,query = query, ListForm=True)
        #for qures in cur:
            progress.update(1)
            #samp:樣本字典
            samp = {"labels":label2id[qures[0]],"text":qures[1]}
            samp.update(tokenize_text(samp['text']))
            del(samp['text'])
            samples.append(samp)
            cnt += 1
            if cnt >= nSampleUPD:
                break
    return samples

def tokenize_text(text):
    return tokenizer(text, truncation=True, max_length=args.MaxSeqLength)

def compute_metrics(pred):
    labels = pred.label_ids
    preds = pred.predictions.argmax(-1)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, preds, average='micro')
    acc = accuracy_score(labels, preds)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }

def trainModel():
    label_names = getTopicLabelList(outputDir)
    id2label = {idx:label for idx, label in enumerate(label_names)}
    
    label2id = {v:k for k,v in id2label.items()}
    
    tokenized_dataset = {}
    tokenized_dataset['train']=[]
    tokenized_dataset['validation']=[]
    
    sql3File = os.path.join(datasetDir,"train.sql3")
    tokenized_dataset['train'] = LoadSamples(sql3File,label2id)
    print(tokenized_dataset['train'][0])
    sql3File = os.path.join(datasetDir,"dev.sql3")
    #dev過程可能會逐步吃光GPU Mem，導致OOM，故先暫時最多只取10萬筆做為dev
    tokenized_dataset['validation'] = LoadSamples(
        sql3File,label2id,nSampleUPD=10*10000)
    
    if torch.cuda.is_available():
        total = torch.cuda.get_device_properties(0).total_memory
        reserved = torch.cuda.memory_reserved(0)
        alloc = torch.cuda.memory_allocated(0)
        free = total-alloc
        print("free gpu memory",free)
        batch_size = max(1, int(free/1100000000))
    else:
        batch_size = 12
    print(
        "Finished loading/tokenizing datasets. "
        f"train samples={len(tokenized_dataset['train'])}, "
        f"validation samples={len(tokenized_dataset['validation'])}. "
        "The next tqdm progress bar is Hugging Face Trainer training/evaluation, "
        "not SQLite dataset loading."
    )
        
    #batch_size = 6
    #print("batch_size",batch_size)
    num_labels = len(label_names)
    model = AutoModelForSequenceClassification.from_pretrained(model_checkpoint, num_labels=num_labels, label2id=label2id, id2label=id2label, trust_remote_code=True)
    model_name = model_checkpoint.split("/")[-1]
        
    num_train_epochs = 3
    logging_steps = max(1, len(tokenized_dataset["train"]) // (batch_size * num_train_epochs))
    train_steps_per_epoch = math.ceil(len(tokenized_dataset["train"]) / batch_size)
    expected_train_steps = train_steps_per_epoch * num_train_epochs
    print(
        f"Training configuration: batch_size={batch_size}, "
        f"num_train_epochs={num_train_epochs}, "
        f"expected training steps={expected_train_steps}."
    )
    
    # 共用參數
    common_args = dict(
        output_dir=outputDir,
        eval_steps=50,
        save_strategy="epoch",
        save_total_limit=1,
        learning_rate=2e-5,
        num_train_epochs=num_train_epochs,
        weight_decay=0.01,
        logging_steps=logging_steps,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
    )
    
    # 嘗試使用 evaluation_strategy，若失敗則 fallback 到 eval_strategy（新版 dev）
    try:
        args = TrainingArguments(
            evaluation_strategy="steps",
            **common_args
        )
    except TypeError as e:
        print(f"⚠️發生TypeError:{e} 使用 eval_strategy（開發版 API）")
        args = TrainingArguments(
            eval_strategy="steps",
            **common_args
        )
    
    trainer = Trainer(
        model,
        args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["validation"],
        tokenizer=tokenizer,
        compute_metrics=compute_metrics
    )
    
    trainer.train()
    
    print("Finished Training Model.")
    print("="*50)

def PredictSamples(ActiveHTCZeroshot=False):
    print(f"Start to predicting samples, the outputDir is {outputDir}")
    r = re.compile("^checkpoint-\d{1,}$")
    finetuned_checkpoint = list(filter(r.match, os.listdir(outputDir)))
    finetuned_checkpoint = sorted(finetuned_checkpoint, reverse=True)[0]
    finetuned_checkpoint = os.path.join(outputDir,finetuned_checkpoint)
    
    device = 0 if torch.cuda.is_available() else -1
    
    batch_size = 8
    if device >= 0:
        nProcess = 1
        '''
        total = torch.cuda.get_device_properties(0).total_memory
        reserved = torch.cuda.memory_reserved(0)
        alloc = torch.cuda.memory_allocated(0)
        free = total-alloc
        singleThreadMemReq = 3*1000*1000*1000
        nProcess = int(free/singleThreadMemReq)
        '''
    elif device == -1:
        #nProcess = multicoreJob().ComputeNProcess()
        nProcessSPC = multicoreJob().ComputeSPCNProcess()
        nProcess = nProcessSPC
        #nProcess = 1
    '''
    if torch.cuda.is_available():
        total = torch.cuda.get_device_properties(0).total_memory
        reserved = torch.cuda.memory_reserved(0)
        alloc = torch.cuda.memory_allocated(0)
        free = total-alloc  # free inside reserved
        print("free gpu memory",free)
        batch_size = int(free/500000000)
    else:
        batch_size = 12
    '''
    
    testSet = []
    sql3File = os.path.join(datasetDir,"test.sql3")
    testSet = LoadSamples(sql3File,istest=True)    
    print(f"Use {nProcess} threads to predict.")
    return_all_scores = ActiveHTCZeroshot
    DTBJobs = [classifierJob(
        testSet=testSetCK,
        finetuned_checkpoint=finetuned_checkpoint,
        device = device,
        batch_size = batch_size,
        return_all_scores=return_all_scores,
        max_length=args.MaxSeqLength
        ) for testSetCK in SplitList(testSet, nChunks=nProcess)]
    #如果開啓平行化執行classifierJob，但未關閉ShuffleJobs，
    #輸出切片分類結果會因不明原因順序錯亂。
    MPresult = multicoreJob(
        DTBJobs, nProcess=nProcess,
        ShuffleJobs=False).run()
    test_result = flattenList(MPresult)
    
    '''
    for nProcess in range(1,6):
        DTBJobs = [classifierJob(
            testSet=testSetCK,
            finetuned_checkpoint=finetuned_checkpoint,
            device = device,
            batch_size = batch_size,
            ) for testSetCK in SplitList(testSet, nChunks=nProcess)]
        MPresult = multicoreJob(
            DTBJobs, nProcess=nProcess).run()
        test_result[nProcess] = flattenList(MPresult)
    for i in range(1,6):
        for j in range(i+1,6):
            print("="*50)
            print(i,j,test_result[i]==test_result[j])
            print(test_result[i][:10])
            print(test_result[j][:10])
    raise Exception
    '''
    testResultFN = f'test_results.tsv'
    #with open(os.path.join(outputDir, testResultFN),'wt',encoding='utf-8') as f_ts_result:
    if "windows" in platform.system().lower():
        os.system("chcp 65001")
    pred_output = open(os.path.join(datasetDir,"logs","pred_output.txt"),"wt",encoding="utf-8")
    HTCZeroShotProbUPD = 0.4
    nHTCZS = 0
    with open(os.path.join(datasetDir, testResultFN),'wt',encoding='utf-8') as f_ts_result:
        #print("testSet",testSet)
        for i,pred_Type in enumerate(test_result):
        #[{'label': '1992 Consensus', 'score': 8.835544917928928e-07}, {'label': '2016 Nice Truck Attack', 'score': 1.599908046046039e-07}]
            if ActiveHTCZeroshot == True:
                pred_Type = sorted(pred_Type,key=lambda x:x["score"],reverse=True)[:6]
                if pred_Type[0]['score'] < HTCZeroShotProbUPD:
                    nHTCZS += 1
                    try:
                        pred_output.write("="*50)
                        #pred_output.write(f"\npred_Type[:4]:{pred_Type[:4]}\n")
                        pred_output.write(json.dumps(pred_Type,sort_keys=True, indent=4))
                        pred_output.write(f"text:\n{testSet[i]}\n")
                        #print(f"text:\n{testSet[i].decode('utf-8')}")
                        #print("pred_Type[:4]",pred_Type[:4])
                    except Exception as e:
                        print(e)
                        pass
                f_ts_result.write(pred_Type[0]['label']+"\n")
            elif ActiveHTCZeroshot == False:
                f_ts_result.write(pred_Type['label']+"\n")
    if ActiveHTCZeroshot == True:
        pred_output.write(f"{len(test_result)}片測試集中，共有{nHTCZS}片推論結果之類別最高機率小於{HTCZeroShotProbUPD}")
    pred_output.close()
            
if __name__=='__main__':
    setproctitle.setproctitle(f'TxCL_Transformer')
    
    args = ClassfierOptionParser()
    
    #model_checkpoint = "./xlm-roberta-base"
    model_checkpoint = get_base_model_checkpoint(args.ModelType)
        
    for model_ckptDir in ["./","./BertScript/"]:
        #for model_checkpoint in ["./xlm-roberta-base","./BertScript/xlm-roberta-base"]:
        model_ckptPath = model_ckptDir+model_checkpoint
        print("="*50)
        print("model_ckptPath",model_ckptPath)
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_ckptPath, trust_remote_code=True)
            #如果成功載入tokenizer的話，回存取獲的完整模型正確路徑到model_checkpoint。
            model_checkpoint = model_ckptPath
            print("final model_checkpoint",model_checkpoint)
            break
        except:
            pass
    
    #raise Exception
    
    os.environ["WANDB_DISABLED"] = "true"
    datasetDir, outputDir = datasetDirOutputDirPickers(args = args).proc()
    if args.BertDatasetSubDir != "":
        datasetDir = args.BertDatasetSubDir
    if args.modelDir != "":
        outputDir = args.modelDir
    
    if outputDir == "":
        outputDir = "dataset"
    # ClassfierOptionParser() already turns test on when neither train nor test
    # is requested. Do not force prediction after a train-only RunClassfier call.
    if args.train == True:
        trainModel()
    if args.test == True:
        PredictSamples(ActiveHTCZeroshot=args.ActiveHTCZeroshot)