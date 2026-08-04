import os
import random
if os.getcwd().split(os.path.sep)[-1] in [
        "DatasetConverter","BertScript"]:
    os.chdir("../")
    print(f"Change working directory to {os.getcwd()}")
print(f"cwd:{os.getcwd()}")
from PackageImport import PackageImporter
PackageImporter.proc()

import os
from utils.DB_utils import sqlite3Query
sql3File = os.path.join("DatasetConverter","dataset","top-1m_CZJ_SamplesFile.sql3")
print(os.path.isfile(sql3File))
table = "sampleSrc"
OutLabel = "Benign Web Link"
col = "text"
query = f'SELECT {col} FROM {table} WHERE OutLabel = "{OutLabel}";'
#print("query",query)
TextPools = set([x[0] for x in list(sqlite3Query(sql3File, query = query))])
#print("="*50)
#print("TextPools[:10]",list(TextPools)[:10])
cnt = 0
iterText = iter(TextPools)
print("="*50)
for x in range(10):
    #if cnt>=10:
        #break
    print(next(iterText))
    #cnt += 1
print("="*50)
#print("retrieve 10 random samples:", random.sample(TextPools, 10))

CheckSrcFN = os.path.join("DatasetConverter","dataset","CheckSrc.csv")
contsSet = set()
CheckSrcCnt = 0
with open(CheckSrcFN,"rt",encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        conts = line in TextPools
        if conts == True:
            #print(f"{line}, {line in TextPools}")
            contsSet.add(line)
        CheckSrcCnt += 1
print("contsSet",contsSet)
print("-"*50)
print(f"{len(contsSet)} of {CheckSrcCnt} are in TextPools.")
