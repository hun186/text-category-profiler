from PackageImport import PackageImporter
PackageImporter.proc()

import os
import torch
import re

from time import sleep
from tqdm import tqdm, trange

#import numpy as np
#from sklearn.metrics import mean_absolute_error

from sklearn.metrics import precision_recall_fscore_support
from sklearn.metrics import accuracy_score
from transformers import TFXLMRobertaModel
from transformers import AutoTokenizer
from transformers import pipeline
from transformers import Trainer
from transformers import AutoModelForSequenceClassification
from transformers import TrainingArguments

from text_category_profiler.core.utilities import SplitList
from text_category_profiler.core.utilities import flattenList
from text_category_profiler.concurrency.MP_utils import MPlogger
from text_category_profiler.concurrency.MP_utils import multicoreJob
from text_category_profiler.pipeline.TCF_utils import ClassfierOptionParser
from text_category_profiler.pipeline.TCF_utils import datasetDirOutputDirPickers
from text_category_profiler.data.DB_utils import sqlite3Query
from text_category_profiler.pipeline.TextClassfier_utils import getTopicLabelList


class classifierJob:
    def __init__(self,testSet,finetuned_checkpoint,
                 device=0,batch_size=8):
        self.testSet = testSet
        self.finetuned_checkpoint = finetuned_checkpoint
        self.device = device
        self.batch_size = batch_size
    def show(self):
        print(f"The length of testSet is {len(self.testSet)}")
    def proc(self):
        classifier = pipeline("text-classification", 
                              model=self.finetuned_checkpoint,
                              tokenizer=self.finetuned_checkpoint, 
                              truncation=True,max_length=180, 
                              device=self.device,
                              batch_size=self.batch_size,
                              )#, return_all_scores = True)
        return classifier(self.testSet)
    
def LoadSamples(sql3File,label2id={},istest = False):
    #sqlCols = ['OutLabel','text']
    print(f"Loading data from {sql3File}, istest = {istest}")
    query = f'SELECT Count(*) FROM sampleSrc;'
    totalrow = sqlite3Query(sql3File,query = query, ListForm=True)[0]
    samples = []
    progress = tqdm(total=totalrow)
    MES = f"Loading samples from {sql3File}"
    print(MES)
    if istest:
        sqlCols = ['text']
        colList=','.join(sqlCols)
        query = f'SELECT {colList} FROM sampleSrc;'           
        cur = sqlite3Query(sql3File,query = query, ListForm=False)
        for qures in cur.fetchall():
            progress.update(1)
            samples.append(qures[0])
            
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
            progress.update(1)
            samp = {"labels":label2id[qures[0]],"text":qures[1]}
            samp.update(tokenize_text(samp['text']))
            del(samp['text'])
            samples.append(samp)
    return samples

def tokenize_text(text):
    return tokenizer(text, truncation=True, max_length=180)

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
    tokenized_dataset['validation'] = LoadSamples(sql3File,label2id)
    
    if torch.cuda.is_available():
        total = torch.cuda.get_device_properties(0).total_memory
        reserved = torch.cuda.memory_reserved(0)
        alloc = torch.cuda.memory_allocated(0)
        free = total-alloc
        print("free gpu memory",free)
        batch_size = int(free/1100000000)
    else:
        batch_size = 12
        
    #batch_size = 6
    #print("batch_size",batch_size)
    num_labels = len(label_names)
    model = AutoModelForSequenceClassification.from_pretrained(model_checkpoint, num_labels=num_labels, label2id=label2id, id2label=id2label)
    model_name = model_checkpoint.split("/")[-1]
        
    num_train_epochs = 3
    logging_steps = len(tokenized_dataset["train"]) // (batch_size * num_train_epochs)
    
    args = TrainingArguments(
        output_dir=outputDir,
        evaluation_strategy = "epoch",
        save_strategy = "epoch",
        save_total_limit = 1,
        learning_rate=2e-5,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        num_train_epochs=num_train_epochs,
        weight_decay=0.01,
        logging_steps=logging_steps,
        #push_to_hub=True,
        #hub_token = 'token value',
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

def PredictSamples():
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
    
    DTBJobs = [classifierJob(
        testSet=testSetCK,
        finetuned_checkpoint=finetuned_checkpoint,
        device = device,
        batch_size = batch_size,
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
    with open(os.path.join(outputDir, 'test_results.tsv'),'wt',encoding='utf-8') as f_ts_result:
        for pred_Type in test_result:
            f_ts_result.write(pred_Type['label']+"\n")
            
if __name__=='__main__':
    
    args = ClassfierOptionParser()

    #model_checkpoint = "./xlm-roberta-base"
    for model_checkpoint in ["./xlm-roberta-base","./BertScript/xlm-roberta-base"]:
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_checkpoint)
            break
        except:
            pass
    
    os.environ["WANDB_DISABLED"] = "true"
    datasetDir, outputDir = datasetDirOutputDirPickers(args = args).proc()
    if args.BertDatasetSubDir != "":
        datasetDir = args.BertDatasetSubDir
    if args.modelDir != "":
        outputDir = args.modelDir
    
    if outputDir == "":
        outputDir = "dataset"
    #args.train = False
    args.test = True
    if args.train == True:
        trainModel()
    if args.test == True:
        PredictSamples()