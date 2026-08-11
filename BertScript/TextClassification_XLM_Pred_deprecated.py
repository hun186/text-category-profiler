from PackageImport import PackageImporter
PackageImporter.proc()
import os
import re
import torch
from time import sleep
from tqdm import tqdm, trange
from transformers import pipeline 

from text_category_profiler.concurrency.MP_utils import MPlogger
from text_category_profiler.pipeline.TCF_utils import ClassfierOptionParser
from text_category_profiler.pipeline.TCF_utils import datasetDirOutputDirPickers
from text_category_profiler.data.DB_utils import sqlite3Query
from text_category_profiler.pipeline.TextClassfier_utils import getTopicLabelList


def LoadSamples(sql3File,istest = False):
    #sqlCols = ['OutLabel','text']
    print(f"Loading data from {sql3File}, istest = {istest}")
    query = 'SELECT Count(*) FROM sampleSrc;'
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
        sqlCols = ['OutLabel','text']
        colList=','.join(sqlCols)
        query = f'SELECT {colList} FROM sampleSrc;'           
        cur = sqlite3Query(sql3File,query = query, ListForm=False)        
        for qures in cur.fetchall():
            progress.update(1)
            samp = {"labels":label2id[qures[0]],"text":qures[1]}
            samp.update(tokenizer(samp['text']))
            del(samp['text'])
            samples.append(samp)
    return samples


#def 
datasetDir, outputDir = datasetDirOutputDirPickers.proc(
    modelType = "PytorchXLM")

DC_args = ClassfierOptionParser()
if DC_args.modelDir != "":
    outputDir = DC_args.modelDir
if outputDir == "":
    outputDir = "dataset"

r = re.compile(r"^checkpoint-\d{1,}$")
finetuned_checkpoint = list(filter(r.match, os.listdir(outputDir)))
finetuned_checkpoint = sorted(finetuned_checkpoint, reverse=True)[0]
finetuned_checkpoint = os.path.join(outputDir,finetuned_checkpoint)

device = 0 if torch.cuda.is_available() else -1

if torch.cuda.is_available():
    total = torch.cuda.get_device_properties(0).total_memory
    reserved = torch.cuda.memory_reserved(0)
    alloc = torch.cuda.memory_allocated(0)
    free = total-alloc  # free inside reserved
    print("free gpu memory",free)
    batch_size = int(free/500000000)
else:
    batch_size = 12
    
classifier = pipeline("text-classification", model=finetuned_checkpoint,
                      tokenizer=finetuned_checkpoint, 
                      truncation=True,max_length=180, 
                      device=device,batch_size =batch_size,
                      #return_all_scores = True)
                      )

'''
print(classifier("I loved reading the Hunger Games!"))
print("="*50)
print(classifier(["ハンガーゲーム」を読むのが好きだった!","I loved reading the Hunger Games!"]))
print("="*50)
'''

#datasetDir = "dataset"
testSet = []
test_result = []
'''
with open(os.path.join(datasetDir,"test.tsv"),'rt',encoding='utf-8') as f:
    for line in f:
        sample = line.strip().split("\t")
        testSet.append(sample[1])
'''
        
sql3File = os.path.join(datasetDir,"test.sql3")
testSet = LoadSamples(sql3File,istest=True)

test_result = classifier(testSet)
#print(test_result)
with open(os.path.join(outputDir, 'test_results.tsv'),'wt',encoding='utf-8') as f_ts_result:
    for pred_Type in test_result:
        f_ts_result.write(pred_Type['label']+"\n")

    