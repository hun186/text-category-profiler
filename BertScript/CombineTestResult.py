import os
#print("=*50")
#print(os.getcwd().split(os.path.sep)[-1])
#if os.getcwd().split(os.path.sep)[-1] in [
#        "DatasetConverter","BertScript"]:
#    os.chdir("../")
#    print(f"Change working directory to {os.getcwd()}")
from PackageImport import PackageImporter
PackageImporter.proc()

import pandas as pd
#import csv
import sqlite3 as lite
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
#import matplotlib.pyplot as plt
import numpy as np
#import re
import setproctitle
from pathlib import Path
#import multiprocessing as mp
from multiprocessing import  Pool
from functools import partial
#import numpy as np

#read the original test data for the text and id
from utils.pipeline.TCF_utils import datasetDirOutputDirPickers
from utils.pipeline.TCF_utils import ClassfierOptionParser
from utils.pipeline.TCF_utils import PYTORCH_MODEL_TYPES
from utils.core.utilities import OSWALK
from utils.core.utilities import WaitUntilFileIsStable
from utils.core.utilities import SplitList
from utils.core.utilities import getFNFromFullPath
from utils.core.utilities import RenameDir
from utils.core.utilities import flattenList
from utils.concurrency.MP_utils import MPlogger
from utils.concurrency.MP_utils import multicoreJob
from utils.data.df_utils import dfOutputer
from utils.data.df_utils import dfFromSQLite3
from utils.core.log_display import key_values
from utils.core.log_display import summarize_sequence
from utils.core.log_display import stage_banner
from utils.core.log_display import stage_done
from ClassesTree.Label_utils import LabelListLoader
#from utils.pipeline.DataConverter_utils import datasetDirOutputDirPickers


class TextInfoSearcher:
    '''
    infoName in ["file", "PartNO"]
    return a list of tuple infoNameList cols in SrcLogFileList, whose text is the same of input text.
    '''
#def searchSrc(text, SrcLogFileList="dataset_total_with_filename.sql3"):
    def __init__(self, SrcLogFileList, infoNameList,MPLOGGER = None):
        self.SrcLogFileList = SrcLogFileList
        #self.infoName = infoName
        self.infoNameList = infoNameList
        if MPLOGGER == None:
            self.MPLOGGER = MPlogger()
        else:
            self.MPLOGGER = MPLOGGER
    def proc(self,text,):
        text = str(text)
        text = text.replace("\"","\"\"")
        for logFile in self.SrcLogFileList:
            #if '\"' in text:
                #return "Pass"

            #if "clear the ground for a new property development project" in text:
                #print("text 1a:",text)
            if not os.path.isfile(logFile):
                MES = f"The file {logFile} does NOT exist. Try Next File."
                self.MPLOGGER.logW(MES, printOnScreen = False)
                continue
            if Path(logFile).stat().st_size == 0:
                MES = f"The file {logFile} is empty. Try Next File."
                self.MPLOGGER.logW(MES, printOnScreen = False)
                continue
            try:
                conn=lite.connect(logFile)
                query = 'SELECT COUNT() from sampleSrc;'
                cursor=conn.execute(query)
            except Exception as e:
                self.MPLOGGER.logW(e)
                continue

            #如果是空表，跳過。
            if cursor.fetchone()[0] == 0:
                MES = "The table sampleSrc in file {} is empty. Try Next File.".format(logFile)
                self.MPLOGGER.logW(MES, printOnScreen = False)
                #MPlogger.logW(MES)
                continue
            #if "clear the ground for a new property development project" in text:
                #print("text 2:",text)
            #query = 'SELECT {} from sampleSrc WHERE text = "{}";'.format(
                #self.infoName,text)
            ColumnsString = ",".join(self.infoNameList)
            query = 'SELECT {} from sampleSrc WHERE text = "{}";'.format(
                ColumnsString,text)

            #if "clear the ground for a new property development project" in query:
                #print("query:",query)
                #raise Exception
            #print("text is ", text)
            try:
                cursor=conn.execute(query)
                #result = cursor.fetchone()
                result = cursor.fetchall()
                #print("result in CR Line 93",result)
                #import time
                #time.sleep(15)
                if result != None:
                    #return result[:1]
                    return result
            except Exception as ex:
                MES = "When applying query {} for file {},".format(
                    query, logFile)
                MES += f"the following error occurs:{ex}"
                self.MPLOGGER.logW(MES)
                pass
        #所有查詢資料庫都查不到該text片段的info來自何檔案時，回傳None。
        return None

class SpecTopicResultOutputer:
    '''
    輸定各類別的相關推論結果。
    '''
    def __init__(self, df_map_result, SpecTopicList, SPEC_outputDir):
        self.df_map_result = df_map_result
        self.SpecTopicList = SpecTopicList
        self.SPEC_outputDir = SPEC_outputDir
    def show(self,):
        print("SPEC_outputDir", self.SPEC_outputDir)
        print("SpecTopicList[:10]", self.SpecTopicList[:10])
    def proc(self,):
        for topic in self.SpecTopicList:
            #df_map_result_Part = df_map_result[
                #df_map_result['Src'].str.contains(topic, na=False)]
            df_map_result_Part = self.df_map_result[
                (self.df_map_result['Type'] == topic)|(self.df_map_result['pred_Type'] == topic)]
            #MKDIR(SPEC_outputDir)
            #df_OutputMain(df_map_result_Part, os.path.join(
                #SPEC_outputDir,'test_results_verification_{}'.format(topic)))
            OUTPUTMAIN = os.path.join(
                self.SPEC_outputDir,'test_results_verification_{}'.format(topic))
            dfOutputer(df_map_result_Part,OUTPUTMAIN,dtype={"PartNO":"INTEGER"}).run()

#multiprocessing平行化分詞程式碼
#Windows上執行python無fork，pandarallel會報錯，改用multiprocessing自建。
#On Windows, Pandaral·lel will works only if the Python session
# (python, ipython, jupyter notebook, jupyter lab, ...) is
# executed from Windows Subsystem for Linux (WSL).

#若要使用multiprocessing，注意不要在主環境import keras，否則mp會卡住，無法執行。
def parallelize(data, func, num_of_processes=8):
    data_split = np.array_split(data, num_of_processes)
    pool = Pool(num_of_processes)
    data = pd.concat(pool.map(func, data_split))
    pool.close()
    pool.join()
    return data

def run_on_subset(func, data_subset):
    #return data_subset.apply(func, axis=1)
    return data_subset.apply(func)

def parallelize_on_rows(data, func, num_of_processes=8):
    return parallelize(data, partial(run_on_subset, func), num_of_processes)

#============================new parallel_apply====================
#def compute(row,kwargs):
def compute(row,SrcLogFileList):
    #global SrcLogFileList
    # 執行運算，這裡假設將 column 'A' 的值平方並存到兩個新 column 'C' 和 'D'
    #print("kwargs in compute",kwargs)
    #SrcLogFileList = kwargs["SrcLogFileList"]
    #result = dict()
    #result["Src"],result["PartNO"] = TextInfoSearcher(
        #SrcLogFileList,["file","PartNO"]).proc(row['text'])
    #result["File"] = getFNFromFullPath(result["Src"])
    result = TextInfoSearcher(SrcLogFileList,["file","PartNO"]).proc(row['text'])
    return result

# 定義一個應用於每一行的輔助函數
def apply_compute(row,**kwargs):
    #result = compute(row,**kwargs)
    #for key, value in result.items():
        #row[key] = value
    #print("~"*50)
    #print("type(row)",type(row))
    #print("row to return",row)
    #return row
    SrcPartNOList = compute(row,**kwargs)
    #print("~"*50)
    #print("len(SrcPartNOList) for text", row['text'], len(SrcPartNOList))
    #print("~"*50)
    result = []
    for Src,PartNO in SrcPartNOList:
        sample = row.copy()
        sample["Src"],sample["PartNO"] = Src,PartNO
        sample["File"] = getFNFromFullPath(Src)
        result.append(sample)
    #print("~"*50)
    #print("type(result)",type(result))
    #print("result to return",result)
    #print("~"*50)
    #import time
    #time.sleep(20)
    return result


# 使用多重處理進行平行化運算
def parallel_apply(df, func, num_of_processes=8,kwargs=dict()):#,factor1=None,factor2=None):
    with Pool(num_of_processes) as pool:
        #func = partial(func, factor1=factor1, factor2=factor2)
        func = partial(func, **kwargs)

        result = pool.map(func, [row for _, row in df.iterrows()])
    #允許一個執行對象回傳多筆輸出為清單，（即為列擴增），在主程式中進行flat合併。
    #print("result in Line 211 b4 fla",result)
    result = flattenList(result)
    #print("result in Line 211 af",result)
    #print('type(result)',type(result))
    #import time
    #time.sleep(20)
    return pd.DataFrame(result)

#============================new parallel_apply====================


def SummarizePerformance():
    SPEC_outputDir = os.path.join(datasetDir,'test_results_verification')
    nProcessSPC = multicoreJob().ComputeSPCNProcess()
    nProcess_STRO = min(nProcessSPC,10)
    print("nProcess_STRO is", nProcess_STRO)


    DTBJobs = [
        SpecTopicResultOutputer(df_map_result,subList,SPEC_outputDir)
        for subList in SplitList(SPEC_TOPIC_LIST, nChunks=nProcess_STRO)]
    multicoreJob(
        DTBJobs, nProcess=nProcess_STRO,method="proc").run()

    RowAttList = ['Type']
    ColAttList = ['pred_Type']


    dfPVT = pd.pivot_table(df_map_result[RowAttList+ColAttList],
                           index=RowAttList,columns=ColAttList,
                           aggfunc=len,margins=False)
    vmin = max(0,dfPVT.min().min())
    vmax = dfPVT.max().max()
    dfPVT['All'] = dfPVT.sum(axis=1)
    # select numeric columns and calculate the sums
    sums = dfPVT.select_dtypes(np.number).sum().rename('All')
    # append sums to the data frame
    dfPVT = dfPVT.append(sums)
    '''
    dfPVT = pd.pivot_table(df_map_result[RowAttList+ColAttList],
                           index=RowAttList,columns=ColAttList,
                           aggfunc=len,margins=True)
    '''
    #print(dfPVT)
    #df_OutputMain(dfPVT, os.path.join(
        #datasetDir,'Confusion Matrix'))
    OUTPUTMAIN = os.path.join(
        datasetDir,'Confusion Matrix')
    dfOutputer(dfPVT,
               OUTPUTMAIN, IndexCols=["Src"]).run()

    cbar = False
    annot = True
    xticklabels = "auto"
    yticklabels = "auto"
    figsize = (10,6)
    figsize = (dfPVT.shape[0]*3,dfPVT.shape[0]*0.6*3)
    #figsize = (20,12)
    OuF = os.path.join(datasetDir, "Heatmap.png")
    dpi = 300
    fig, (ax1)=plt.subplots(
        #nrows=1,ncols=1,
        figsize=figsize,
        #gridspec_kw=grid_kws,
        constrained_layout=True)
    sns.set(font_scale=1.4)
    ax1 = sns.heatmap(dfPVT,annot=annot,fmt=".0f",cmap='inferno_r',
                      ax=ax1,norm=LogNorm(vmin=vmin, vmax=vmax),
                      cbar=cbar,
                      xticklabels=xticklabels,
                      yticklabels=yticklabels,
                      )
    plt.xticks(rotation=45)
    plt.yticks(rotation=45)
    #plt.yticks(np.arange(len(dfPVT.index))+0.5)
    #ax1.set_ylim([len(dfPVT.index),0])
    fig.savefig(OuF, dpi = dpi)
    #SaveFigToPNG(fig, OFNM)
    plt.close('all')

if __name__=='__main__':
    setproctitle.setproctitle('CZJCombineTestResult')
    if os.getcwd().split(os.path.sep)[-1] in [
            "DatasetConverter","BertScript"]:
        os.chdir("../")
        print(f"Change working directory to {os.getcwd()}")
    args = ClassfierOptionParser()
    BertDatasetSubDir,outputDir = datasetDirOutputDirPickers(
        args=args,rdy_for_stage="CombineTestResult").proc()
    if BertDatasetSubDir == None:
        MES = "-"*50+"\n"
        MES += f"In {args.WorkPoolROOT}, There is no BertDatasetSubDir ready for CombineTestResult! ABORT!"
        MPlogger().logW(MES)
        raise Exception


    NewBertDatasetSubDir = BertDatasetSubDir.replace(
        "_rdy_for_CombineTestResult","_is_running_CombineTestResult")
    #NewBertDatasetSubDir += BertDatasetSubDir + "_is_running_DataConverter"
    os.rename(BertDatasetSubDir,NewBertDatasetSubDir)
    stage_banner("CombineTestResult", detail=f"WorkDir: {NewBertDatasetSubDir}")
    MES = f"CombineTestResult started. WorkDir is {NewBertDatasetSubDir}."
    BertDatasetSubDir = NewBertDatasetSubDir
    MPLOGGER = MPlogger(logSubDir=f"{BertDatasetSubDir}/logs")
    MPLOGGER_TCFMain = MPlogger(logSubDir=f"{BertDatasetSubDir}/logs",logFile="TCFMain.log")
    MPLOGGER_TCFMain.logW(MES, printOnScreen=False)
    key_values("CombineTestResult workspace", [("workdir", NewBertDatasetSubDir)])
    datasetDBDir = args.datasetDataBaseSubDir

    datasetDir = BertDatasetSubDir
    '''
    args = ClassfierOptionParser()
    if args.BertDatasetSubDir == "":
        datasetDir, outputDir = datasetDirOutputDirPickers(args=args).proc()
    else:
        datasetDir = args.BertDatasetSubDir
    '''
    MES = "Analysis test_result of dataset {}".format(datasetDir)
    MPLOGGER_TCFMain.logW(MES, printOnScreen=False)
    '''
    SrcLogFileList = [
        os.path.join(datasetDir,datasetDBDir,"dataset_total_with_filename.sql3"),
        os.path.join(datasetDir,datasetDBDir,"dataset_total_with_filename_FixedTest.sql3"),
        os.path.join(datasetDir,datasetDBDir,"dataset_total_with_filename_ES.sql3"),
        ]
    '''
    #dataset_total_with_filename.sql3,dataset_total_with_filename_ES.sql3,dataset_total_with_filename_FixedTest.sql3
    SrcLogFileList = OSWALK(os.path.join(datasetDir,datasetDBDir),FNrePat=r"dataset_total_with_filename.*\.sql3")
    if len(SrcLogFileList) == 0:
        MES = f"When run CombineTestResult.py, there is no dataset_total_with_filename database found! Check the correctness of the datasetDB file pointer for {os.path.join(datasetDir,datasetDBDir)}."
        MPLOGGER_TCFMain.logW(MES)
    key_values("Result analysis inputs", [
        ("dataset", datasetDir),
        ("source db count", len(SrcLogFileList)),
        ("source db preview", summarize_sequence(SrcLogFileList, limit=3)),
    ])
    '''
    nProcess = mp.cpu_count()-1
    nProcess = 10
    '''
    nProcess = multicoreJob().ComputeNProcess(log=False)

    LabelFile = "TopicAnalysis_LabelList.txt"

    LabelFile = os.path.join(datasetDir,"TopicAnalysis_LabelList.txt")
    #TypeList = ['体育', '娱乐', '家居', '彩票','房产', '教育', '时尚', '时政','星座',
                #'游戏', '社会', '科技','股票', '财经']
    #SPEC_TOPIC_LIST = ['PRC_OffDoc','South_Sea']

    TypeList = LabelListLoader.proc(LabelFile)
    SPEC_TOPIC_LIST = TypeList

    labeltoType = {}
    TypetoLabel = {}
    for i,Type in enumerate(TypeList):
        labeltoType[i] = Type
        TypetoLabel[Type] = i
    #print(indextoLabel)

    #讀取test.tsv，內含label答案。
    df_test = dfFromSQLite3(os.path.join(datasetDir,"test.sql3"))
    for removeCol in ["index","ID"]:
        if removeCol in df_test.columns:
            df_test = df_test.drop([removeCol],axis=1)
    df_test.columns = ["Type", "text"]

    #讀取test_results.tsv，內含模型預測機率值。
    WatchedFN = os.path.join(datasetDir, 'test_results.tsv')
    WaitUntilFileIsStable(WatchedFN)
    #df_result = pd.read_csv(os.path.join(outputDir, 'test_results.tsv'),sep='\t', header=None)
    df_result = pd.read_csv(WatchedFN,sep='\t', header=None)
    if df_test.shape[0] != df_result.shape[0]:
        MES = f"The number of test samples {df_test.shape[0]} is not the same as the number of result probability for test samples {df_result.shape[0]}"
        MES += "\n There might be somehting wrong!"
        MPLOGGER_TCFMain.logW(MES)


    #create a new dataframe
    if args.ModelType == "TF15Bert":
        df_map_result = pd.DataFrame({'Type': df_test['Type'],
            'text': df_test['text'],
            'label': df_result.idxmax(axis=1)})
        df_map_result['pred_Type'] = df_map_result['label'].apply(
            lambda x:labeltoType[x])
    elif args.ModelType in PYTORCH_MODEL_TYPES:
        df_map_result = pd.DataFrame({'Type': df_test['Type'],
            'text': df_test['text']})
        df_map_result['pred_Type'] = df_result
    else:
        raise ValueError(f"Unsupported ModelType for result combination: {args.ModelType}")
    MES = "Start to query the Src of texts."
    MPLOGGER_TCFMain.logW(MES, printOnScreen=False)
    key_values("Source lookup", [("processes", nProcess), ("rows", len(df_map_result))])
    #print("Start to query the Src of texts.")
    #df_map_result['Src'] = df_map_result['text'].apply(
        #lambda x:searchSrc(x,SrcLogFile))

    '''
    paraResult = parallelize_on_rows(
        df_map_result['text'],
        TextInfoSearcher(SrcLogFileList,["file","PartNO"]).proc, num_of_processes=nProcess)
    print("paraResult",paraResult)
    print("paraResult.shape",paraResult.shape)
    '''
    kwargs = {"SrcLogFileList":SrcLogFileList}
    df_map_result = parallel_apply(df_map_result, apply_compute, num_of_processes=nProcess,kwargs=kwargs)
    #print("df_map_result",df_map_result)
    #df_map_result[['Src','PartNO']]
    #import time
    #time.sleep(20)
    #df_map_result['PartNO'] = parallelize_on_rows(
        #df_map_result['text'],
        #TextInfoSearcher(SrcLogFileList,"PartNO").proc, num_of_processes=nProcess)

    #df_map_result['File'] = parallelize_on_rows(
        #df_map_result['Src'],
        #getFNFromFullPath, num_of_processes=nProcess)

    #view sample rows of the newly created dataframe
    df_map_result = df_map_result.reindex(
        columns=['Type','pred_Type', 'text','Src', 'File','PartNO'])


    MES = "Finished querying the Src of texts."
    MPLOGGER_TCFMain.logW(MES, printOnScreen=False)
    key_values("Verification dataframe", [("sort by", ["Type", "pred_Type"]), ("rows", len(df_map_result))])
    df_map_result = df_map_result.sort_values(by=['Type','pred_Type'])
    #df_OutputMain(df_map_result, os.path.join(
        #datasetDir,'test_results_verification'))
    OUTPUTMAIN = os.path.join(datasetDir,'test_results_verification')
    dfOutputer(df_map_result,
               OUTPUTMAIN, IndexCols=["Src", 'File'],dtype={"PartNO":"INTEGER"}).run()

    Matchdf = pd.DataFrame(
        [df_map_result['Type'] == df_map_result['pred_Type']]).transpose()
    Matchdf.columns = ["match"]
    MatchCount = Matchdf.groupby('match').size()
    match_count = int(MatchCount.get(True, 0))
    mismatch_count = int(MatchCount.get(False, 0))
    total_count = match_count + mismatch_count
    accuracy = f"{match_count / total_count:.4f}" if total_count else "n/a"
    sample_count_status = "normal" if len(df_map_result) == total_count else "WARNING: strange"
    key_values("Match summary", [
        ("matched", match_count),
        ("mismatched", mismatch_count),
        ("accuracy", accuracy),
        ("sample count sum", sample_count_status),
    ], icon="·")

    if args.SummarizePerformance == True:
        SummarizePerformance()
    #將目錄更名，以供下階段功能程式抓取。
    NewBertDatasetSubDir = BertDatasetSubDir.replace(
        "_is_running_CombineTestResult","_rdy_for_TestResultVis")
    #os.rename(BertDatasetSubDir,NewBertDatasetSubDir)
    RenameDir(SrcDir=BertDatasetSubDir,DesDir=NewBertDatasetSubDir)
    stage_done("CombineTestResult")
    MES = f"CombineTestResult is finished. Rename {BertDatasetSubDir} as {NewBertDatasetSubDir}"
    key_values("CombineTestResult handoff", [("from", BertDatasetSubDir), ("to", NewBertDatasetSubDir)])
    MPLOGGER_TCFMain = MPlogger(logSubDir=f"{NewBertDatasetSubDir}/logs")
    MPLOGGER_TCFMain.logW(MES, printOnScreen=False)
