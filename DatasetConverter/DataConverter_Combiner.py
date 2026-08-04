import os
if os.getcwd().split(os.path.sep)[-1] in [
        "DatasetConverter","BertScript"]:
    os.chdir("../")
    print(f"Change working directory to {os.getcwd()}")
from PackageImport import PackageImporter
PackageImporter.proc()

import setproctitle
#載入DatasetConverter參數設定
try:
    import DatasetConverter.ConverterParameters as ConverterParameters_Combiner
except:
    pass
from TCF_Params.TCFParameters import WorkPoolROOT
from TCF_Params.TCFParameters import TopicTextCrawlerROOT
from TCF_Params.TCFParameters import DatasetConverterROOT
from TCF_Params.TCFParameters import BertClassfierPath

from DatasetConverter.ConverterParameters_Combiner import CombinerROOTPATHList

import sys
import ntpath
import pathlib
import platform
import psutil
import pandas as pd
#import csv
import random
import time
import sqlite3 as lite
from pandas.io import sql
import re
import glob
import subprocess
from pathlib import Path
from collections import Counter
import json

#import plotly.io as pio; pio.renderers.default='notebook'
from plotly.offline import plot
import plotly.express as px
import textwrap
#from zhconv import convert
from opencc import OpenCC
import multiprocessing as mp

import shutil
import argparse
#import GPUtil

from utils.utilities import CapWords
from utils.utilities import OSWALK
from utils.utilities import MKDIR
#from utilities import ShowElapsedTime
#from utils.utilities import mem_report
#from utils.TCF_utils import GetTreeFilePath
from utils.TCF_utils import GetRSTRLabelList
from utils.TCF_utils import datasetDirOutputDirPickers
from utils.TCF_utils import ClassfierOptionParser
from utils.TCF_utils import TaskConnector

from ClassesTree.Label_utils import getLabelsFromOSWALK
from ClassesTree.Label_utils import getLabelsFromFileName
from ClassesTree.Label_utils import LabelsStringReader
from ClassesTree.Label_utils import LabelListExtractor

from utils.DataConverter_utils import getSrcFromFileName
#from utils.DataConverter_utils import datasetDirOutputDirPickers
#from utils.DataConverter_utils import LoadTree
#from utils.DataConverter_utils import GetNodes
#from utils.DataConverter_utils import GetSubTopics
#from utils.DataConverter_utils import GetClosestMatchingParent
#from utils.DataConverter_utils import GetInducedSubgraph
#from utils.DataConverter_utils import BuildInfoScoreTable
#from utils.DataConverter_utils import GetFixedTestPATH
#from utils.DataConverter_utils import RANDLoader
#from utils.DataConverter_utils import CheckDatasetFiles
try:
    from sampleHandler import SampleReader
except:
    from DatasetConverter.sampleHandler import SampleReader

#from utilities import hash
from utils.df_utils import dfOutputer
from utils.MP_utils import multicoreJob
from utils.MP_utils import MPlogger
from utils.Dash_utils import LevelDVisProcessor
#from utilities_RAND import LoadTree
#from utilities_RAND import RANDLoader


from utils.utilities import fileNameNormalizer
from utils.utilities import getMFNFromFN
from utils.utilities import getFNFromFullPath

from utils.utilities import timeNow
from utils.utilities import ShowElapsedTime
from utils.utilities import ShowStepCostTime
from utils.utilities import SplitList
from utils.utilities import ListDivider
from utils.utilities import ListDiff
from utils.utilities import flattenList
from utils.utilities import fileNameReplacer
from utils.utilities import WaitUntilFileIsStable
from utils.utilities import CopyOrMoveWithFNList
from utils.utilities import RandomSample
from utils.TextProcessor_utils import textReader
from utils.TextProcessor_utils import TxtFileHashDictBuilder

from utils.DB_utils import sqlite3Query
from utils.DB_utils import getESData

from utils.df_utils import DictRowsListToDF

def ArticleRowsListToDF(rows_list,start_time=None):
    rows_list = list(filter((None).__ne__, rows_list))
    print("="*50)
    print("finished remove empty list of Row_List")
    ShowElapsedTime(start_time)
    random.shuffle(rows_list)
    print("="*50)
    print("Finished shuffling Row_List.")
    ShowElapsedTime(start_time)    
    print("="*50)
    print("The first 3 of rows_list:")
    for x in rows_list[0:1]:
        print("="*50)
        print(x[0])
        print("-"*50)
        print(x[1])
        print("="*50)
    df = pd.DataFrame(rows_list)
    df.columns = ['OutLabel','text']
    #RemoveDumpSamples = False
    RemoveDumpSamples = True
    if RemoveDumpSamples == True:
        #去除重複樣本，當(Out)Label與text都相同時，則去除。    
        df = df[~df.duplicated(['OutLabel','text'])]
        print("finished remove duplicated")
        ShowElapsedTime(start_time)
        print("df af remov dup", df)
        print("df.columns af remov dup", df.columns)
    
    if df.shape[0] == 0:
        print("WARNING!! Dataframe df is empy!! ABORT!")
        #raise Exception
    df = df.reset_index(drop=True)
    #df = TextNormalize(df)
    return df

def BuildSamplesDfFromPaths(
    datasetSubDir = "dataset",
    ROOTPATHList = [],
    
    SQLFile = "",
    esJob = dict(),
    OUTPUTMAIN = os.path.join(
        "dataset", "dataset_total_with_filename"),
    OUTPUTMAIN_Counter = None,
    datasetCountOFN = None,
    RemoveDumpArticle = True,
    DataAugmentationGoal=0,
    Count_SQL_table="sampleCount_Main",
    #nProcess = 1,
    DCkwargs = {},
    start_time=None,
    MPLOGGER = None):
    if MPLOGGER == None:
        MPLOGGER = MPlogger()
    if "nProcess" in DCkwargs.keys():
        nProcess = DCkwargs["nProcess"]
    else:
        nProcess = 1
    
    inputSrc = DCkwargs["inputSrc"]
    outputSrc = DCkwargs["outputSrc"]
    UseTerms = set(inputSrc).union(set(outputSrc))
    PairDir = dict()
    print("ROOTPATHList",ROOTPATHList)
    for path in ROOTPATHList:
        for file in OSWALK(path):
            for term in UseTerms:
                if term in file:
                    #print("file",file)
                    MFN = getMFNFromFN(file)
                    if MFN not in PairDir.keys():
                        PairDir[MFN] = dict()
                    PairDir[MFN][term] = file
    
    rows_list = []

    for MFN in PairDir.keys():

        #print("dealing ",MFN)
        try:
            inp = ""
            opt = ""
            for inpTerm in inputSrc:
                inp += textReader(
                    file=PairDir[MFN][inpTerm],encoding="utf-8").run()
            if len(inp)<500:
                continue
            for optTerm in outputSrc:
                opt += textReader(
                    file=PairDir[MFN][optTerm],encoding="utf-8").run()
            if len(opt)<30:
                continue
            if len(inp) < len(opt):
                continue
            rows_list.append([opt,inp])
        except Exception as e:
            print(f"While handling {MFN}, the following error occurs:{e}")
    #print("inputSrc",inputSrc)
    #print("outputSrc",outputSrc)
    #print(rows_list[0][0])
    #print("="*50)
    #print(rows_list[0][1])
    #raise Exception
    df = DictRowsListToDF(
        rows_list,Cols = ['OutLabel','text'],start_time=start_time)
    return df

if __name__=='__main__':
    start_time = time.time()
    setproctitle.setproctitle(f'DC_Combiner')
    nProcess = multicoreJob().ComputeNProcess()
    #if "windows" not in platform.system().lower():
        #nProcess = 200
    #nProcessSPC = multicoreJob().ComputeSPCNProcess()
    MKDIR(WorkPoolROOT)
    inputMaxLen = 2048
    DCkwargs = {
        "inputMaxLen" : inputMaxLen, #輸入樣本最長度
        "inputSrc" : ["=MainText"], #樣本輸入組建來源
        "outputSrc" : ["=EngAbstract"], #預期推論輸出組建來源
        #"outputSrc" : ["=CnAbstract"], #預期推論輸出組建來源
        #"outputSrc" : ["=Keyword"], #預期推論輸出組建來源
        }

    MPLOGGER_DCC = MPlogger(
        logSubDir=f"logs",logFile="DataConveter_Combiner.log")
    #MPLOGGER_DCC.logW(MES)

    #依照目錄設定，由txt檔產製資料集檔案。
    MES = "開始產製資料集檔案。"
    MPLOGGER_DCC.logW(MES)
    OUTPUTMAIN = os.path.join(os.getcwd(),"DatasetConverter/train")
    df = BuildSamplesDfFromPaths(
        ROOTPATHList = CombinerROOTPATHList,
        #OUTPUTMAIN = OUTPUTMAIN,
        #OUTPUTMAIN_Counter = OUTPUTMAIN_Counter,
        #nProcess = nProcess,
        DCkwargs = DCkwargs,
        start_time=start_time)
    print("df",df)

    #以下排序程式碼會將輸出依文本及檔名排序，以供快速查閱中文亂碼，僅供debug使用。
    #正式產製訓練資料時，務必mark，否則會因沒有亂數排序，導致訓練資料集label不平衡。
    #df = df.sort_values(['text', 'file'], ascending=[1, 1])

    #輸出總表，包含所有樣本之label、text及檔名資訊
    DTBJobs = []
    IndexCols = ["text", "Src"]
    dfOutputer(df, OUTPUTMAIN, IndexCols=IndexCols, TSVTextAdapter=True).run()
    print(f"The combined data has been export to {OUTPUTMAIN}.sql3.")
    os.system("pause")