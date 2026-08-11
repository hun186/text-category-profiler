import os
import sys
from pathlib import Path

# Direct script execution puts only DatasetConverter/ on sys.path.  Add the
# repository root explicitly instead of loading the legacy path injector,
# which also searched machine-specific and parent-relative directories.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

if os.getcwd().split(os.path.sep)[-1] in [
        "DatasetConverter","BertScript"]:
    os.chdir("../")

import setproctitle
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
from collections import Counter
import json

#import plotly.io as pio; pio.renderers.default='notebook'
from plotly.offline import plot
import plotly.express as px
import textwrap
#from zhconv import convert
import multiprocessing as mp

import shutil
import argparse
from colorama import Fore#, Back, Style

#載入DatasetConverter參數設定
'''
try:
    import DatasetConverter.ConverterParameters as ConverterParameters
except:
    pass
'''
from TCF_Params.TCFParameters import WorkPoolROOT
from TCF_Params.TCFParameters import DatasetConverterROOT
#from TCF_Params.TCFParameters import ROOTPATHList
#from TCF_Params.TCFParameters import BertClassfierPath

#from DatasetConverter.ConverterParameters import RBDict
#from DatasetConverter.ConverterParameters import DataCleanerRePatternDict
#from DatasetConverter.ConverterParameters import StasticSwitch
#from DatasetConverter.ConverterParameters import ConvertToSpec
#from DatasetConverter.ConverterParameters import TreeBinaryTarget
#from DatasetConverter.ConverterParameters import UniqueLabel
from DatasetConverter.ConverterParameters import nProcess
from DatasetConverter.ConverterParameters import nProcessSPC
#from DatasetConverter.ConverterParameters import UniqueSortedLabels
#from DatasetConverter.ConverterParameters import RemoveDumpSamples
#from DatasetConverter.ConverterParameters import OnlyLettersDigitsLabels
from DatasetConverter.ConverterParameters import DatasetRatioDict
#from DatasetConverter.ConverterParameters import WIDTH
#from DatasetConverter.ConverterParameters import sampleMethod
#from DatasetConverter.ConverterParameters import DataAugmentationGoal
from DatasetConverter.ConverterParameters import RemoveDumpArticle_FT
from DatasetConverter.ConverterParameters import DCkwargs
from DatasetConverter.EXTConverter.ExtractionConverter import Extractor
from DatasetConverter.EXTConverter.ExtractionRule import ExtractionRuleDict
from DatasetConverter.EXTConverter.Combiner import CZJCorpusFileBuilder


from text_category_profiler.core.utilities import OSWALK
from text_category_profiler.core.utilities import MKDIR
from text_category_profiler.core.utilities import randomReplace
from text_category_profiler.pipeline.TCF_utils import GetRSTRLabelList
from text_category_profiler.pipeline.TCF_utils import datasetDirOutputDirPickers
from text_category_profiler.pipeline.TCF_utils import ClassfierOptionParser
from text_category_profiler.pipeline.TCF_utils import get_base_model_checkpoint
from text_category_profiler.pipeline.TCF_utils import TaskConnector

from text_category_profiler.pipeline.DataConverter_utils import getSrcFromFileName
from text_category_profiler.pipeline.DataConverter_utils import GetFixedTestPATH
from ClassesTree.ClassesTree_utils import GetNodes
from ClassesTree.ClassesTree_utils import GetSubTopics
from ClassesTree.ClassesTree_utils import GetClosestMatchingParent
#from ClassesTree.ClassesTree_utils import GetInducedSubgraph
from ClassesTree.ClassesTree_utils import SetTreeFiles
#try:
    #from sampleHandler import SampleReader
#except:
from DatasetConverter.sampleHandler import SampleReader
from DatasetConverter.dataset_split import augment_training_rows
from DatasetConverter.dataset_split import build_split_plan
from DatasetConverter.dataset_split import deduplicate_dataset_rows
from DatasetConverter.dataset_split import ensure_train_covers_labels
from DatasetConverter.dataset_split import expand_train_to_cover_labels
from DatasetConverter.dataset_split import iter_dataset_splits
from DatasetConverter.sample_schema import columns_for_sample_rows

#from utilities import hash
from text_category_profiler.data.df_utils import dfOutputer
from text_category_profiler.concurrency.MP_utils import multicoreJob
from text_category_profiler.concurrency.MP_utils import MPlogger
from text_category_profiler.core.log_display import info
from text_category_profiler.core.log_display import key_values
from text_category_profiler.core.log_display import section
from text_category_profiler.core.log_display import stage_banner
from text_category_profiler.core.log_display import stage_done
from text_category_profiler.core.log_display import summarize_sequence
from text_category_profiler.core.log_display import warning
#from utilities_RAND import LoadTree
#from utilities_RAND import RANDLoader


from text_category_profiler.core.utilities import ShowElapsedTime
from text_category_profiler.core.utilities import ShowStepCostTime
from text_category_profiler.core.utilities import SplitList
from text_category_profiler.core.utilities import ListDiff
from text_category_profiler.core.utilities import flattenList
from text_category_profiler.core.utilities import fileNameReplacer
from text_category_profiler.core.utilities import CopyOrMoveWithFNList
from text_category_profiler.core.utilities import RandomSample
from text_category_profiler.core.utilities import FileHashDictBuilder

from text_category_profiler.data.DB_utils import getESData
from text_category_profiler.data.DB_utils import sqlite3Query

from text_category_profiler.data.df_utils import DictRowsListToDF

#from text_category_profiler.Tika_pdf_to_txt import ExtractTxt
r'''
import winreg
winreg.SetValueEx(
    winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE,
                     r'SYSTEM\CurrentControlSet\Control\FileSystem'),
    'LongPathsEnabled', None, winreg.REG_DWORD, 1)
'''

class DataConvertJobGenerater():
    '''
    輸入原始文本目錄清單，輸出資料集轉換任務工作物件，續送入平行化工作器。
    Mode:切割模式，全文切割模式為"FullCut"，
    ConvertToSpec：繁轉簡及慣用語轉換，None、'tw2s'：簡轉繁、'tw2sp'：簡轉繁加慣用語轉換。
    nBound：單一文本檔案輸出資料集樣本數量設定上限，依文本類別作用。
    sampleLenLBD：取樣長度下限
    LabelConvertDict：最終輸出標籤轉換字典。
    TreeBinaryTarget：執行特定分類二元樹標籤轉換目標，預設為None，不啓用轉換功能，
    LabelConvertDict為Identity mapping，如果此設定不為None，
    將會把該標籤下的所有子分類標籤mapping為該標籤，其他為Negative，設定LabelConvertDict。
    產製對應的LabelConvertDict，最終輸出標籤轉換字典，用於最終輸出標籤。
    UniqueLabel：單一樣本若輸出入多個標籤，是否只取優序最高之標籤做為唯一輸出。
    '''
    def __init__(self,
                 ROOTPATHList = [],
                 datasetSubDir = "dataset",
                 nProcess = 1,
                 fileList = [],
                 CZJCorpusSQLFileList = [],
                 FixedTestFileBound=6000,
                 #SQLFile = "",
                 esJob = dict(), #es_token,indexname,startDay,endDay
                 RemoveDumpArticle = True,
                 ReadQuery = "",
                 WIDTH = 256,
                 Mode = "FullCut", #全文切割模式:"FullCut"
                 tokenizationWrap = True,
                 modelDir = "",
                 ConvertToSpec = None, #繁轉簡及慣用語轉換，None,'tw2s'
                 LabelList = None,
                 sampleMethod = {
                     "nBound":{
                     "default": 5000, 
                     "Economist":1000,
                     },
                     "RandomSample":True,
                     "LenLBD":128
                     },
                 #nBound = {
                     #"default": 5000, 
                     #"Economist":1000, 
                     #},
                 #sampleLenLBD = 128,
                 #TreeBinaryMode = False,
                 TreeBinaryTarget = None,
                 UniqueLabel = True, #輸出樣本是否僅單一Label
                 InfoScoreTable = {},
                 UniqueSortedLabels = True, #讀取Label清單字串時，是否進行Label Unique
                 OnlyLettersDigitsLabels = False, #讀取Label清單字串時，是否去除非字母或數字字符
                 tpcTree = None, #類別樹
                 #tpcDeepLimit = None, #類別深度限制
                 RSTRLabelList = [], #限制允許標籤列表
                 RBDict = {},
                 RBActive = True,
                 DataCleanerRePatternDict = {},
                 MPLOGGER = None
                 ):
        if MPLOGGER == None:
            self.MPLOGGER = MPlogger()
        else:
            self.MPLOGGER = MPLOGGER
        self.datasetSubDir = datasetSubDir
        self.ROOTPATHList = ROOTPATHList
        #self.SQLFile = SQLFile
        self.esJob = esJob
        self.RemoveDumpArticle = RemoveDumpArticle
        self.nProcess = nProcess
        #self.nProcess = nProcess
        self.fileList = fileList
        self.CZJCorpusSQLFileList = CZJCorpusSQLFileList
        self.FixedTestFileBound = FixedTestFileBound
        
        #if len(self.esJob)>0:# != {}:
        if self.esJob != dict():
            #print("self.esJob",self.esJob)
            #getESData回傳為[{"id":3234},{"id":1356},{"id":1263}]
            self.esJob["retItem"] = {"id"}
            self.ESidList = [x['id'] for x in getESData(self.esJob)]
            #print("self.ESidList",self.ESidList)
            #取得送編清單
            self.esSelectedJob = self.esJob.copy()
            #self.esSelectedJob["selectedMessage"] = False
            self.esSelectedJob["selectedMessage"] = True
            self.esSelectedJob["retItem"] = {"id","subject"}
            self.ESSelectedDictList = {
                x['id']:x['subject'] for x in getESData(self.esSelectedJob)}
            #print("self.ESSelectedidList",self.ESSelectedDictList)
            #from collections import Counter
            df_selectedMessage = pd.DataFrame.from_dict(
                self.ESSelectedDictList, 
                #Counter(self.ESidList),
                orient='index',columns = ["subject"])
            #df_selectedMessage.reset_index(drop=True)
            #print("df_selectedMessage",df_selectedMessage)
            #print("df_selectedMessage.columns",df_selectedMessage.columns)
            df_selectedMessage.columns = ["subject"]
            #OUTPUTMAIN = os.path.join("dataset", "ESselect")
            OUTPUTMAIN = os.path.join(self.datasetSubDir, "ESselect")
            dfOutputer(df_selectedMessage, OMFN=OUTPUTMAIN,
                       tsvIndex=True,SQL_table="selectedMessage").run()
            '''
            self.SelectedESidList = [x['id'] for x in getESData(
                self.esJob["es_tokens"],self.esJob["indexname"],
                self.esJob["startDay"],self.esJob["endDay"],
                self.esJob["langCode"],self.esJob["selectedMessage"],
                #retItem = "(id)")
                retItem = {"id"})]
            '''
            #print("self.ESidList",self.ESidList)
            #raise Exception
        else:
            self.ESidList = []
        #輸入檔案單路完成型
        if self.fileList == []:
            self.fileList = self.BuildFileList(
                FullPathFNrePat=(r"(.*CZJ_SamplesFile.*sql3)|"
                                 r"(.*#T#\[.*\].*\.txt)|(.*\.AI2)")
                )
        #輸入檔案多路完成型
        #if self.fileList == []:
        if True:
            self.CZJCorpusSQLFileList = self.BuildFileList(
                FullPathFNrePat=".*CZJ_CorpusFile.*sql3"
                )
            
        self.ReadQuery = ReadQuery
        #print(self.fileList[0:10])
        #print(len(self.fileList))
        #raise Exception
        self.WIDTH = WIDTH
        self.Mode = Mode
        self.tokenizationWrap = tokenizationWrap
        if tokenizationWrap == True:
            if modelDir == "":
                info("tokenizationWrap is True but modelDir is empty; resolving modelDir from dataset/output settings.")
                _,modelDir = datasetDirOutputDirPickers(
                    args=args,rdy_for_stage="DataConverter").proc()
                if modelDir in [None, ""]:
                    modelDir = get_base_model_checkpoint(args.ModelType)
                key_values("Tokenizer model directory", [
                    ("modelDir", modelDir),
                    ("MaxSeqLength", args.MaxSeqLength),
                ], icon="·")
        #print("In DC,modelDir",modelDir)
        #raise Exception
        self.modelDir = modelDir
        self.ConvertToSpec = ConvertToSpec
        self.LabelList = LabelList
        #self.nBound = nBound
        #self.sampleLenLBD = sampleLenLBD
        self.sampleMethod = sampleMethod
        self.TreeBinaryTarget = TreeBinaryTarget
        self.tpcTree = tpcTree
        self.RSTRLabelList = RSTRLabelList
        self.LabelConvertDict = self.BuildLabelConvertDict(
            self.LabelList, self.TreeBinaryTarget, self.RSTRLabelList)
        self.RBDict = RBDict
        self.UniqueLabel = UniqueLabel
        self.InfoScoreTable = InfoScoreTable
        self.UniqueSortedLabels = UniqueSortedLabels
        self.OnlyLettersDigitsLabels = OnlyLettersDigitsLabels
        self.RBActive = RBActive
        self.DataCleanerRePatternDict = DataCleanerRePatternDict
        #print("nProcess", nProcess)
        #raise Exception
        self.show()

        

        
    def show(self):
        key_values("Dataset converter job", [
            ("input roots", len(self.ROOTPATHList)),
            ("root preview", summarize_sequence(self.ROOTPATHList, limit=3)),
        ], icon="·")
    
    def RemoveDumpArt(self,fiL):
        if len(fiL) == 0:
            key_values("Duplicate article removal", [
                ("input files", 0),
                ("duplicates removed", 0),
                ("remaining files", 0),
                ("elapsed seconds", "0.0000"),
            ], icon="·")
            return fiL
        start_time = time.time()
        key_values("Duplicate article removal", [
            ("input files", len(fiL)),
            ("method", "hash first 100MB"),
        ], icon="·")
        #要用'rt'模型讀取文字檔，進行hash比對，去除重複，故比對時只考慮副檔名為"txt"之檔案。
        #非txt檔則全部保留，不比對內容。
        #fiLTxt = [x for x in fiL if os.path.splitext(x)[1][1:].lower() == "txt"]
        #fiLNonTxt = [x for x in fiL if os.path.splitext(x)[1][1:].lower() != "txt"]
        DTBJobs = [
            #TxtFileHashDictBuilder(fiLCK, hashalg = "sha1")
            FileHashDictBuilder(
                fiLCK, hashalg = "sha1", nBytes = 100*1000*1000)
            for fiLCK in SplitList(fiL, nChunks=self.nProcess)]
        hashDictList = multicoreJob(
            DTBJobs, nProcess=self.nProcess).run()
        hashDict = dict()
        for mydict in hashDictList:
            hashDict.update(mydict)
        hashDict = {value : key for (key, value) in hashDict.items()}
        fiL = list(hashDict.values())
        return fiL
    
    def BuildFileList(self,FullPathFNrePat):
        fiL = []
        start_time = time.time()
        key_values("Dataset file discovery", [
            ("input roots", len(self.ROOTPATHList)),
            ("root preview", summarize_sequence(self.ROOTPATHList, limit=3)),
            ("filename pattern", FullPathFNrePat),
        ], icon="·")
        
        #if self.SQLFile == "":
        #print("In BfileL,FullPathFNrePat",FullPathFNrePat)
        #time.sleep(10)
        for PATH in self.ROOTPATHList:
            filePaths = OSWALK(
                PATH, Extension = ["txt","AI2","sql3"],
                FullPathFNrePat = FullPathFNrePat,
                #FullPathFNrePat=("(.*CZJ_SamplesFile.*sql3)|"
                                 #"(.*CZJ_CorpusFile.*sql3)|"
                                 #"(.*#T#\[.*\].*\.txt)|(.*\.AI2)")
                )
            #print("filePaths b4",filePaths)
            #排除路徑內有UnTagged或UnSpec的檔案。
            filePaths = [x for x in filePaths 
                         if "UnTagged".lower() not in x.lower() and 
                          "UnSpec".lower() not in x.lower() ]
            #print("filePaths af",filePaths)
            fiL.extend(filePaths)
        nOri = len(fiL)
        #利用Hash比對各檔案前100MB是否相同，以去除同樣檔案。
        if self.RemoveDumpArticle == True:
            fiL = self.RemoveDumpArt(fiL)
        '''
        elif self.SQLFile != "":
            conn = lite.connect(SQLFile)
            FilePath_query = 'SELECT FilePath,ArticleHash FROM Corpus WHERE topics IS NOT "[]";'
            FHP = conn.execute(FilePath_query).fetchall()
            conn.close()
            fiL = [x[0] for x in FHP]
            nOri = len(fiL)
            if self.RemoveDumpArticle == True:
                hashDict = {}
                for file, hashVal in FHP:
                    hashDict[hashVal] = file
                fiL = list(hashDict.values())
                #nOri = len(FHP)
        '''        
        if self.RemoveDumpArticle == True:
            nDiff = nOri - len(fiL)
            key_values("Duplicate article removal result", [
                ("input files", nOri),
                ("duplicates removed", nDiff),
                ("remaining files", len(fiL)),
                ("elapsed seconds", f"{time.time() - start_time:.4f}"),
            ], icon="·")

        else:
            key_values("Dataset file discovery result", [
                ("RemoveDumpArticle", False),
                ("files", len(fiL)),
                ("elapsed seconds", f"{time.time() - start_time:.4f}"),
            ], icon="·")
        #如果檔案數過多，大於FixedTestFileBound，則將FixedTest_xxx目錄下
        #的檔案隨機選取一部份留下，FixedTest_xxx下其他檔案略過，以免癱瘓片段推論結果可視化介面。
        if self.FixedTestFileBound!=0 and len(fiL)>self.FixedTestFileBound:
            PartFixedTest = [x for x in fiL if "FixedTest_" in x or "AIpool".lower() in x.lower()]
            #PartNonFixedTest = [x for x in fiL if "FixedTest_" not in x]
            PartNonFixedTest = [x for x in fiL if "FixedTest_" not in x and "AIpool".lower() not in x.lower()]
            #random.shuffle(PartFixedTest)
            #fiL = PartFixedTest[:self.FixedTestFileBound]+PartNonFixedTest
            fiL = RandomSample(PartFixedTest,self.FixedTestFileBound)+PartNonFixedTest
        return fiL

    def BuildLabelConvertDict(self, 
                              LabelList = None,
                              TreeBinaryTarget = None,
                              RSTRLabelList = [],
                              ):
        LabelConvertDict = {}
        #if TreeBinaryMode == True:
        #如果有設定二元分類目標（非None），則進行正負標籤轉換。
        if TreeBinaryTarget is not None:
            #tpcTree = LoadTree(TreeFile)
            subTpcs = GetSubTopics([TreeBinaryTarget], self.tpcTree)
            print("subTpcs of topic {} are {}.".format(
                TreeBinaryTarget, subTpcs))
            for tpc in LabelList:
                if tpc in subTpcs:
                    LabelConvertDict[tpc] = TreeBinaryTarget
                else:
                    LabelConvertDict[tpc] = "Negative"
        #如果二元分類目標為None，且限制性標籤不為空，則進行限制性標籤轉換。
        elif RSTRLabelList != []:
            print("="*50)
            print("RSTRLabelList", RSTRLabelList)
            #print("="*50)
            #tpcTree = GetInducedSubgraph(tpcTree,RSTRLabelList)
            #print("InducedSubtree", tpcTree)
            for node in sorted(set(GetNodes(self.tpcTree))):
                CMPNodeList = GetClosestMatchingParent(
                    self.tpcTree, node, RSTRLabelList,
                    ReturnOnlyOneClosestParent = True)
                #CMPNode = CMPNodeList[0]
                #print(f"For {node}, the closestMatchingParent is {CMPNode}.")
                #print("="*50)
                
                if CMPNodeList == []:
                    CMPNode = "UnAllowedLabel"
                else:
                    CMPNode = CMPNodeList[0]
                    print(f"For {node}, the closest Matching Parent is {CMPNode}.")
                    print("="*50)
                    LabelConvertDict[node] = CMPNode
            #raise Exception
        #elif tpcDeepLimit != None:
            #tpcLvsDict = BuildtpcLvsDict(self.tpcTree)
        #如果二元分類目標為None，且限制性標籤為空，則不進行任何標籤轉換。
        else:
            for tpc in LabelList:
                LabelConvertDict[tpc] = tpc
        nConvertedLabels = sum([LabelConvertDict[x] != x for x in LabelConvertDict.keys()])
        MES="LabelConvertDict Mapping:\n"
        if nConvertedLabels == 0:
            MES += "Identity Map\n"
        else:
            for key in sorted(LabelConvertDict.keys()):
                MES += "{:<35s} : {:>35s}\n".format(key, LabelConvertDict[key])
                #print("{:<35s} : {:>35s}".format(key, LabelConvertDict[key]))
        MES += f"共有{len(LabelConvertDict.keys())}個標籤。"
        key_values("Label conversion", [
            ("mode", "Identity Map" if nConvertedLabels == 0 else "Mapped"),
            ("label count", len(LabelConvertDict.keys())),
            ("converted labels", nConvertedLabels),
        ], icon="·")
        MKDIR(self.datasetSubDir)
        MPlogger(os.path.join(self.datasetSubDir,"OnlyForRecord"),
                 logFile="dataset.txt").logW(MES=MES, printOnScreen=False)
        with open(os.path.join(
            self.datasetSubDir,"OnlyForRecord","TopicAnalysis_LabelList_Including_NonOccuring.txt"),
            'wt',encoding='utf-8') as f:
            #for y in sorted(set([LabelConvertDict[x] for x in DNTags])):
            for y in sorted(set([LabelConvertDict[x] for x in LabelList])):
                f.write(y+"\n")
        return LabelConvertDict
    
    def run(self):
        DTBJobs = []
        ESidSet = set(self.ESidList)
        CZJCorpusJobList = []
        for CZJSQL in self.CZJCorpusSQLFileList:
            query = 'SELECT title FROM Corpus;'
            TitleList = sqlite3Query(
                CZJSQL, query = query,ListForm = True)
            print("TitleList",TitleList)
            CZJCorpusJobList.extend(
                [(ti,CZJSQL) for ti in TitleList])
        for (file,CZJSQL,esJob) in [
            (file,"",{}) for file in self.fileList]+[
            (_id,"",self.esJob) for _id in self.ESidList]+[
            (ti,CZJSQL,{}) for ti,CZJSQL in CZJCorpusJobList]+[
            ]:
            if any(["FixedTest_" in file,
                    "Deactive_DCRB" in file,
                    file in ESidSet,
                    ]):
                RBActiveFin = False
            else:
                RBActiveFin = self.RBActive
            Job = SampleReader(
                file = file,
                LabelList = self.LabelList, 
                width = self.WIDTH,
                Mode = self.Mode, 
                tokenizationWrap = self.tokenizationWrap,
                modelDir = self.modelDir,
                ConvertToSpec = self.ConvertToSpec, 
                #nBound = self.nBound,
                #sampleLenLBD = self.sampleLenLBD,
                sampleMethod = self.sampleMethod,
                LabelConvertDict = self.LabelConvertDict,
                RBDict = self.RBDict,
                UniqueLabel = self.UniqueLabel,
                #SQLFile = self.SQLFile,
                CZJCorpusSQLFile = CZJSQL,
                esJob = esJob,
                InfoScoreTable = self.InfoScoreTable,
                UniqueSortedLabels = self.UniqueSortedLabels,
                OnlyLettersDigitsLabels = self.OnlyLettersDigitsLabels,
                RBActive = RBActiveFin,
                DataCleanerRePatternDict = self.DataCleanerRePatternDict,
                MPLOGGER = self.MPLOGGER
                )
            DTBJobs.append(Job)
        #random.shuffle(DTBJobs)
        return DTBJobs


def BuildSamplesDfFromPaths(
    datasetSubDir = "dataset",
    ROOTPATHList = [],
    
    #SQLFile = "",
    esJob = dict(),
    OUTPUTMAIN = os.path.join(
        "dataset", "dataset_total_with_filename"),
    OUTPUTMAIN_Counter = None,
    datasetCountOFN = None,
    RemoveDumpArticle = True,
    Count_SQL_table="sampleCount_Main",
    nProcess = nProcess,
    DCkwargs = {},
    start_time=None,
    MPLOGGER = None):
    '''
    處理指定路徑，轉換成樣本DataFrame，其中rows_list為字典清單，如：[
    {'file': 'FixedTest/FixedTest_8050/Using/20220301/#T#[CN-IND Boundary]/老一辈革命家处理中印边界问题的对策方法.txt', 'InLabel': 'CN-IND Boundary', 'OutLabel': 'CN-IND Boundary', 'text': '文献研究室研究员，北京100017〕', 'PartNO': 65},....]
    '''
    if start_time is None:
        start_time = time.time()
    if MPLOGGER == None:
        MPLOGGER = MPlogger()
    #if "nProcess" in DCkwargs.keys():
        #nProcess = DCkwargs["nProcess"]
    #else:
        #nProcess = 1
    LabelList = DCkwargs["LabelList"]
    if datasetCountOFN == None:
        datasetCountOFN = os.path.join(
            datasetSubDir,"OnlyForRecord","dataset.txt")
    #參數存log檔時，控制顯示Label數量。
    DCkwargsToPrint = DCkwargs.copy()
    #LabList = DCkwargsToPrint["LabelList"]
    #if len(LabList)> 40:
        #DCkwargsToPrint["LabelList"]=LabList[:15]+[f"{len(LabList)-30} skipped terms"]+LabList[-15:]
    for key in ["LabelList","tpcTree"]:
        list_obj = DCkwargsToPrint[key]
        if len(list_obj)> 40:
            DCkwargsToPrint[key]=list_obj[:15]+[f"{len(list_obj)-30} skipped terms"]+list_obj[-15:]
        
    MES = "IN BSDF, DCkwargs \n" + str(DCkwargsToPrint)
    MPLOGGER.logW(MES,printOnScreen=False)
    DCJG = DataConvertJobGenerater(
        datasetSubDir=datasetSubDir,
        ROOTPATHList=ROOTPATHList,
        #SQLFile = SQLFile,
        esJob = esJob,
        RemoveDumpArticle = RemoveDumpArticle,
        #nProcess = nProcess,
        MPLOGGER = MPLOGGER,
        **DCkwargs
        )
    
    datasetCountOFP = open(datasetCountOFN,mode='at',encoding='utf-8')
    DTBJobs = DCJG.run()
    # 將每個已發現的檔案、ES document 或 corpus title 轉成 SampleReader job，
    # 再匯集各 job 返回的 sample rows。
    section(
        "Load source data into sample rows",
        detail=(
            "Create one reader job per discovered file/document/corpus title, "
            "then collect the rows returned by those readers."
        ),
        icon="📥",
    )
    key_values("Reader job inputs", [
        ("configured input roots", len(ROOTPATHList)),
        ("matching sample files", len(DCJG.fileList)),
        ("Elasticsearch documents", len(DCJG.ESidList)),
        ("corpus databases", len(DCJG.CZJCorpusSQLFileList)),
        ("reader jobs created", len(DTBJobs)),
        ("worker processes requested", nProcess),
    ], icon="·")
    if DTBJobs:
        MPresult = multicoreJob(DTBJobs, nProcess=nProcess).run()
    else:
        MPresult = []
        warning(
            "Sample loading was skipped: no reader jobs were created because no "
            "supported input files, Elasticsearch documents, or corpus titles "
            "were discovered. Check the configured input roots and the file "
            "discovery summaries above."
        )
    if MPresult == []:
        rows_list = []
        MultiLabelCountList = []
    else:
        rows_list, MultiLabelCountList = zip(*MPresult)
    rows_list = flattenList(rows_list)
    key_values("Sample row collection result", [
        ("reader results returned", len(MPresult)),
        ("sample rows collected", len(rows_list)),
        ("multi-label count results", len(MultiLabelCountList)),
        ("next step", "convert collected rows to a DataFrame"),
        ("elapsed seconds", f"{time.time() - start_time:.4f}"),
    ], icon="·")
    
    '''
    rowlist sample:
    [{'file':'abc.txt', 
      'InLabel': 'Scrap',
      'OutLabel': 'Scrap',
      'text': '都是那几个相同的头',
      'PartNO': 2},
     {...
      },
     ]
    '''
 
    #計算樣本標記數量。
    if len(rows_list) > 0:
        df_Counter = pd.DataFrame.from_dict(
            Counter([row['OutLabel'] for row in rows_list]),
            orient='index')
        df_Counter.columns = ["Loaded Samples Count"]
        df_Counter.sort_values(by='Loaded Samples Count',ascending=False, inplace=True)
        if OUTPUTMAIN_Counter is None:
            OUTPUTMAIN_Counter = OUTPUTMAIN.replace("_with_filename","")+"_labels_count"
        dfOutputer(df_Counter, OUTPUTMAIN_Counter,
                   tsvIndex=True,SQL_table=Count_SQL_table).run()
        ShowElapsedTime(start_time)
    else:
        warning(
            "No sample rows are available for DataFrame conversion. "
            f"Configured input roots: {summarize_sequence(ROOTPATHList, limit=3)}."
        )


    df = DictRowsListToDF(
        rows_list,start_time=start_time,
        #RemoveDumpBasedOnCols=['file','OutLabel','text'],
        # Keep the sample handoff schema even when this particular source is
        # empty. Test-only runs load FixedTest rows later in DatasetGenerator.
        Cols=columns_for_sample_rows(rows_list),
        )
    #部分外部來源可能沒有 PartNO，轉換為整數前先補零。
    if len(df) > 0:
        #df = df.astype({"PartNO":"int32"})
        df["PartNO"] = df["PartNO"].fillna(0).astype("int32")
    #依書籍或google蒐索爬文所獲情況，決定Src及SrcType。
    if df.shape[0] != 0:
        df = multicoreJob(nProcess=nProcess).parallelize_dataframe(df, GetDataSRC)

    key_values("Source/type columns", [
        ("rows", df.shape[0]),
        ("columns", summarize_sequence(list(df.columns), limit=8)),
        ("elapsed seconds", f"{time.time() - start_time:.4f}"),
    ], icon="·")
    
    #儲存標籤映射函數。
    for y in sorted(set([DCJG.LabelConvertDict[x] for x in LabelList])):
        datasetCountOFP.write(y+"\n")

    #統計輸出樣本數量
    MES = "There are totally {} samples converted, cf {} or {} for filename.".format(
        df.shape[0], OUTPUTMAIN+".tsv", OUTPUTMAIN+".sql3")
    key_values("Dataset conversion result", [
        ("samples", df.shape[0]),
        ("tsv", OUTPUTMAIN+".tsv"),
        ("sqlite", OUTPUTMAIN+".sql3"),
    ], icon="·")
    datasetCountOFP.write(MES + "\n")
    datasetCountOFP.close()
    return df

def GetDataSRC(df):
    '''
    def MetaDataOfSample(x):
        #x = ../Books/中文文章/scrap/中文古文
        #print("path is ", x)
        FolderList = [CapWords(fold) for fold in x.split("\\")]
        #print("FolderList",FolderList)
        #raise Exception
        for label in LabelList:
            if label in getLabelsFromFileName(x):
                #Ind = FolderList.index(label)
                for i,fold in enumerate(FolderList):
                    if fold.startswith("#T#") and label in getLabelsFromFileName(fold):
                        Ind = i
                        break
                if "Books" in x.split("\\"):
                     SrcType = FolderList[Ind-1]
                     Src = FolderList[Ind+1]
                else:
                    #print("FolderList",FolderList)
                    SrcType = FolderList[Ind-2]
                    Src = FolderList[Ind-1]
                break
        return SrcType, Src
    '''
    LabelList = list(df['InLabel'].unique())
    try:
        df['SrcType'], df['Src'] = zip(
            *df['file'].apply(getSrcFromFileName, LabelList = LabelList))
                #lambda x:getSrcFromFileName(
                    #FileName=x, LabelList = LabelList))
            #*df['file'].apply(MetaDataOfSample))
    except:
        pass
    return df

'''
def TextNormalize(df):
    for removeChar in ['\0','\u3000','\t', '\ufeff']:
        df.text = df.text.str.replace(removeChar,'')
    df.text = df.text.replace('"','“')
    df.text = df.text.replace("'","’")
    return df
'''

def MultiLabCt(MultiLabelCountList):
    '''
    (({'COVID-19', 'PRC_OffDoc'}, 14),
     ({'COVID-19', 'PRC_OffDoc'}, 10),
     ({'COVID-19', 'PRC_OffDoc'}, 8),
     ...)
    '''
    MLdict = {}
    for MLset, count in MultiLabelCountList:
        if MLset == None:
            continue
        key = tuple(sorted(MLset))
        MLdict[key] = MLdict.get(key, 0)+count
    return MLdict
        

class DatasetGenerator:
    '''
    將輸入的DataFrame切割為訓練集、驗證集、測試集，另加入固定全文指定做為測試集的資料。回傳各資料集數量字典。
    '''
    class Outputer:
        def __init__(self, df, OUTPUTMAIN, logFile, 
                     IndexCols=[],DataAugmentationGoal=0,
                     MPLOGGER = None):
            self.df = df
            self.OUTPUTMAIN = OUTPUTMAIN
            self.logFile = logFile
            self.IndexCols = IndexCols
            self.DataAugmentationGoal = DataAugmentationGoal
            if MPLOGGER == None:
                self.MPLOGGER = MPlogger(logFile=self.logFile)
            else:
                self.MPLOGGER = MPLOGGER
        def show(self):
            key_values("DataFrame filter job", [("output", self.OUTPUTMAIN), ("rows", len(self.df))], icon="·")
        def run(self):
            dfOutputer(self.df[['OutLabel','text']],
                       self.OUTPUTMAIN, IndexCols=self.IndexCols).run()
            if '\0' in open(self.OUTPUTMAIN+".tsv", encoding="utf-8").read():
                CheckResult = "are"
            else:
                CheckResult = "are not"
            key_values("TSV null-byte check", [
                ("file", self.OUTPUTMAIN+".tsv"),
                ("contains null bytes", CheckResult == "are"),
            ], icon="·")
            MES = ("For {}, there {} null bytes in your input file").format(
                self.OUTPUTMAIN+".tsv", CheckResult)
            self.MPLOGGER.logW(MES=MES, printOnScreen=False)

            
    def __init__(self, df,
                 OUTPUTMAIN = "",
                 IndexCols = [],
                 datasetSubDir = "dataset",
                 DatasetRatio = {},
                 DataAugmentationGoal = 0,
                 FixedTestPATHList = [],
                 esJob = dict(),
                 DCkwargs = {},
                 datasetCountOFN = None,
                 nProcess = nProcess,
                 MPLOGGER = None,
                 ):
        self.df = df
        self.OUTPUTMAIN = OUTPUTMAIN
        self.OUTPUTMAIN_FT = OUTPUTMAIN+"_FixedTest"
        self.OUTPUTMAIN_es = OUTPUTMAIN+"_ES"
        self.IndexCols = IndexCols
        self.datasetSubDir = datasetSubDir
        self.DatasetRatio = DatasetRatio
        self.DataAugmentationGoal = DataAugmentationGoal
        self.FixedTestPATHList = FixedTestPATHList
        self.esJob = esJob
        self.DCkwargs = DCkwargs
        if datasetCountOFN == None:
            self.datasetCountOFN = os.path.join("dataset","dataset.txt")
        else:
            self.datasetCountOFN = datasetCountOFN
        #open(self.datasetCountOFN,mode='wt',encoding='utf-8').close()
        self.logFile = self.datasetCountOFN
        self.nProcess = nProcess
        #self.InfoScoreTable = DCkwargs["InfoScoreTable"]
        if MPLOGGER == None:
            self.MPLOGGER = MPlogger(logFile=self.logFile)
        else:
            self.MPLOGGER = MPLOGGER

        
    def show(self):
        key_values("Dataset generator job", [
            ("FixedTestPATHList", summarize_sequence(self.FixedTestPATHList, limit=4)),
            ("logFile", self.logFile),
            ("OUTPUTMAIN", self.OUTPUTMAIN),
        ], icon="·")
    def run(self):
        self.show()
        if self.DataAugmentationGoal > 0 and not self.df.empty:
            # Preserve the legacy randomized source order without mixing
            # augmented variants into validation or test data.
            self.df = self.df.sample(frac=1).reset_index(drop=True)
        nBeforeDedup = len(self.df)
        self.df = deduplicate_dataset_rows(self.df)
        key_values("Dataset deduplication", [
            ("original rows", nBeforeDedup),
            ("removed rows", nBeforeDedup - len(self.df)),
            ("remaining rows", len(self.df)),
        ], icon="·")
        # FixedTest inputs are intentionally separate from the regular source
        # roots. Discover them here so test-only logs clearly show whether the
        # configured files exist before dataset split generation starts.
        FixfiL = []
        for workingPath in self.FixedTestPATHList:
            FixfiL.extend(OSWALK(workingPath, Extension=["txt", "AI2", "sql3"]))
        key_values("Fixed test file discovery", [
            ("configured paths", summarize_sequence(self.FixedTestPATHList, limit=4)),
            ("matching files", len(FixfiL)),
            ("file preview", summarize_sequence(FixfiL, limit=3)),
        ], icon="·")
        if self.FixedTestPATHList and not FixfiL:
            warning(
                "No supported FixedTest files were found below the configured "
                "paths. Expected .txt, .AI2, or .sql3 files in nested folders."
            )

        #設定訓練集、驗證集及測試集比例。
        nDataset = self.df.shape[0]
        ratio_split_plan = build_split_plan(
            nDataset,
            train_ratio=self.DatasetRatio["Train"],
            test_ratio=self.DatasetRatio["Test"],
        )
        split_plan = expand_train_to_cover_labels(
            ratio_split_plan,
            row_count=nDataset,
            label_count=self.df["OutLabel"].dropna().nunique(),
        )
        if split_plan != ratio_split_plan:
            warning(
                "Training split expanded from "
                f"{ratio_split_plan.train} to {split_plan.train} source rows "
                "so every valid label can occur in training."
            )
        self.df = ensure_train_covers_labels(self.df, split_plan.train)
        nDict = dict(split_plan.items())
        #FNDdict = {"train":"train.tsv", "validation":"dev.tsv", "test":"test.tsv"}
        MFNDdict = {"train":"train", "validation":"dev", "test":"test"}
    
        FT_df = pd.DataFrame()
        es_df = pd.DataFrame()
        #生成各資料集。
        key_values("Dataset split plan", [
            ("train", split_plan.train),
            ("validation", split_plan.validation),
            ("test", split_plan.test),
            ("fixed test paths", summarize_sequence(self.FixedTestPATHList, limit=4)),
        ], icon="·")
        DTBJobs = []
        for key, Partdf in iter_dataset_splits(self.df, split_plan):
            key_values("Generate dataset split", [("split", key), ("planned rows", nDict[key])], icon="·")
            if key == "train":
                source_train_rows = len(Partdf)
                Partdf, augmented_rows = augment_training_rows(
                    Partdf,
                    samples_per_label=self.DataAugmentationGoal,
                    text_augmenter=lambda text: randomReplace(
                        text, nReplacedChar=1
                    ),
                )
                nDict["train_source"] = source_train_rows
                nDict["train_augmented"] = augmented_rows
                nDict["train"] = len(Partdf)
                if augmented_rows > 0:
                    Partdf = Partdf.sample(frac=1).reset_index(drop=True)
                key_values("Training data augmentation", [
                    ("target rows per label", self.DataAugmentationGoal),
                    ("source rows", source_train_rows),
                    ("augmented rows", augmented_rows),
                    ("training rows", len(Partdf)),
                ], icon="·")
            #Partdf["dataType"].astype("category")
            if key == "test":
                if len(FixfiL) > 0:
                    FT_df = BuildSamplesDfFromPaths(
                        datasetSubDir = self.datasetSubDir,
                        ROOTPATHList = self.FixedTestPATHList,
                        RemoveDumpArticle = RemoveDumpArticle_FT,
                        OUTPUTMAIN = self.OUTPUTMAIN_FT,
                        #nProcess = self.nProcess,
                        Count_SQL_table = "sampleCount_FixedTest",
                        DCkwargs = self.DCkwargs)
                else:
                    FT_df = pd.DataFrame()
                key_values("Fixed test samples", [
                    ("paths", summarize_sequence(self.FixedTestPATHList, limit=4)),
                    ("rows", len(FT_df)),
                ], icon="·")
                #print("Partdf bf add FT",Partdf)
                Partdf = pd.concat([Partdf, FT_df], ignore_index=True)
                #print("Start to output FT_df to MainFN {} \n".
                      #format(self.OUTPUTMAIN_FT))
                #print("FT_df",FT_df)
                #print("self.OUTPUTMAIN_FT", self.OUTPUTMAIN_FT)
                #print("self.IndexCols",self.IndexCols)
                dfOutputer(FT_df, self.OUTPUTMAIN_FT, IndexCols=self.IndexCols).run()
                if self.esJob != dict():
                    es_df = BuildSamplesDfFromPaths(
                        datasetSubDir = self.datasetSubDir,
                        esJob = self.esJob,
                        RemoveDumpArticle = RemoveDumpArticle_FT,
                        OUTPUTMAIN = self.OUTPUTMAIN_es,
                        #nProcess = self.nProcess,
                        Count_SQL_table = "sampleCount_Elasticsearch",
                        DCkwargs = self.DCkwargs)
                    key_values("Elasticsearch test samples", [
                        ("index", self.esJob["indexname"]),
                        ("rows", len(es_df)),
                    ], icon="·")
                else:
                    es_df = pd.DataFrame()
                Partdf = pd.concat([Partdf, es_df], ignore_index=True)
                key_values("Elasticsearch output", [("output", self.OUTPUTMAIN_es), ("rows", len(es_df))], icon="·")
                dfOutputer(es_df, self.OUTPUTMAIN_es, IndexCols=self.IndexCols).run()

            if Partdf.shape[0] == 0:
                continue
            #Partdf["dataType"] = key
            #Partdf["dataType"] = Partdf["dataType"].astype("category")
            #print("Partdf",Partdf)
            #將文本正規化，去除'\0','\u3000','\t', '\ufeff'等字元。
            #for removeChar in ['\0','\u3000','\t', '\ufeff']:
                #Partdf.text = Partdf.text.str.replace(removeChar,'')
            #DFTextNormalize已整入dfOutputer函式
            #Partdf = multicoreJob(nProcess=self.nProcess).parallelize_dataframe(Partdf, TextNormalize)
            #dfOutputer(Partdf[['OutLabel','text']], MFNDdict[key]).run()
            #輸出各資料集至檔案，MFNDdict[key]為各資料集之輸出主檔名。
            DTBJobs.append(
                self.Outputer(Partdf,
                              OUTPUTMAIN = os.path.join(self.datasetSubDir, MFNDdict[key]),
                              logFile = self.logFile))
        nDict["fixed_test"] = len(FT_df)
        nDict["Elasticsearch"] = len(es_df)
        key_values("Dataset split source counts", [
            ("train source rows", nDict["train_source"]),
            ("train augmented rows", nDict["train_augmented"]),
            ("train output rows", nDict["train"]),
            ("validation source rows", nDict["validation"]),
            ("test total rows", nDict["test"] + nDict["fixed_test"] + nDict["Elasticsearch"]),
            ("fixed_test rows", nDict["fixed_test"]),
            ("Elasticsearch rows", nDict["Elasticsearch"]),
        ], icon="·")

        #使用多進程儲存train、dev、test資料集。
        #樣本數太多時(如400萬筆)，如啓用狀態條，使用新的istarmap時，在第25行:
        #return (item for chunk in result for item in chunk)
        #可能會出現struct.error: 'i' format requires -2147483648 <= number <= 2147483647錯誤
        #故此處使用SafeMode
        if nDataset>4000000:
            nDFOPTProcess = 1
        else:
            nDFOPTProcess = self.nProcess
        multicoreJob(
            DTBJobs, nProcess=nDFOPTProcess).run()
        try:
            with open(os.path.join(
                self.datasetSubDir,"OnlyForRecord", "nDict.json"),
                'wt', encoding='utf-8') as f:
                json.dump(nDict, f)
        except:
            pass
        return nDict
    
def GenStasticsVisJobs(df, datasetSubDir):
    # Dash is only needed when statistics visualization jobs are requested.
    # Keeping this import local prevents every Windows spawn worker from loading
    # Dash (and repeating dependency deprecation warnings) during sample reads.
    from text_category_profiler.visualization.Dash_utils import LevelDVisProcessor

    result = []
    for VisPath in [['SrcType', 'Src', 'InLabel'],
                    ['InLabel', 'SrcType', 'Src'],
                    ['SrcType', 'Src', 'OutLabel'],
                    ['OutLabel', 'SrcType', 'Src']]:
        for method in ["sunburst", "treemap"]:
            Job = LevelDVisProcessor(
                df = df, VisPath = VisPath,
                method = method, 
                VisOutputSubDir = os.path.join(
                    datasetSubDir, "LDVisual_"))
            result.append(Job)
    return result

def FindFileContains(path, string, ApplyMoveFile = False, ApplyCountString = False):
    def MoveFile():
        counter = 0
        for file in os.listdir(path):
            src = os.path.join(path,file)
            if not os.path.isfile(src):
                continue
            try:
                if string in open(src,'rt',encoding='utf-8').read():
                    desSubDir = os.path.join(path, "Containing_"+string)
                    des = os.path.join(desSubDir,file)
                    MKDIR(desSubDir)
                    shutil.move(src, des)
                    counter += 1
            except:
                pass
        print("於目錄 {}，發現 {} 個含有字串 {} 的檔案".format(
            path, counter, string))
        print("已將其移至原目錄下之子目錄 {}。".format(
            "Containing_"+string))
    def CountString():
        print("針對目錄 {} ，統計字串'{}'出現次數之結果如下：".format(path,string))
        for file in OSWALK(path):
            count = open(file,'rt',encoding='utf-8').read().count(string)
            if count > 10:
                print("檔案 {} 中，共含有 {} 個".format(file, count))
        
    if ApplyMoveFile == True:
        MoveFile()
    if ApplyCountString == True:
        CountString()
        
    raise Exception
    
def FNReplace():
    fileNameReplacer.proc(ROOTPATHList=ROOTPATHList,
                          ReplaceDict={
                              #" Issue":" Affairs",
                              #"Polar Affair":"Polar Affairs"
                              "CCP Affair":"CPC Affairs",
                              },
                          ReplaceDirNameOnly = True,
                          RemoveEmptyFolder = True)
    raise Exception


def PickSelectTxt(SrcRoot = ""):
    if SrcRoot=="":
        MES = "When try to PickSelectTxt, the SrcRoot is UNSETTED!!"
        print(MES)
    #WorkingSrcRoot
    for PickSrcSet in [["Target"],["Target","NonTarget","short"]]:
        FNPatListFile = os.path.join(SrcRoot,"select.txt")
        FNPatList = [x.rstrip('\n') for x in open(FNPatListFile,'rt',encoding='utf-8').readlines()]
        for SrcType in PickSrcSet:
            WSRoot = os.path.join(SrcRoot,SrcType)
            #從多個類型挑選，挑出來置於select子目錄
            if len(PickSrcSet) > 1:
                DesRoot = os.path.join(SrcRoot,"select")
            #從單個類型挑選，如：Target，挑出來置於Target_select子目錄
            elif len(PickSrcSet) == 1:
                DesRoot = os.path.join(SrcRoot,SrcType+"_select")
            MKDIR(DesRoot)
            CopyOrMoveWithFNList(
                SrcRoot=WSRoot, DesRoot=DesRoot,
                FNMatchingMode="Part",FNPatList=FNPatList)
    raise Exception

def setArguments(DCkwargs):
    setproctitle.setproctitle('CZJDataConvert')
    args = ClassfierOptionParser()
    args.BertDatasetSubDir,_ = datasetDirOutputDirPickers(
        args=args,rdy_for_stage="DataConverter").proc()
    #BertDatasetSubDir,outputDir = datasetDirOutputDirPickers(args=args).proc()
    #datasetDBDir = args.datasetDataBaseSubDir
    NewBertDatasetSubDir = args.BertDatasetSubDir + "_is_running_DataConverter"

    stage_banner("DataConverter", detail=f"WorkDir: {NewBertDatasetSubDir}")
    MES = f"DataConveter started. WorkDir is {NewBertDatasetSubDir}."
    args.BertDatasetSubDir = NewBertDatasetSubDir
    global MPLOGGER
    global MPLOGGER_TCFMain
    MPLOGGER = MPlogger(logSubDir=f"{args.BertDatasetSubDir}/logs")
    MPLOGGER_TCFMain = MPlogger(logSubDir=f"{args.BertDatasetSubDir}/logs",logFile="TCFMain.log")
    MPLOGGER_TCFMain.logW(MES)

    exeTimeDict["stage_start_time"] = time.time()
    #nProcess = multicoreJob().ComputeNProcess()
    #nProcessSPC = multicoreJob().ComputeSPCNProcess()
    
    #if not os.path.isdir(BertClassfierPath):
        #BertClassfierPath = "dataset"
    
    MKDIR(WorkPoolROOT)
    MKDIR(args.BertDatasetSubDir)
    
    workingPath = r"C:\Users\Bruce2\Downloads\TopicTextCrawler_reload\C_wikisourceSearch\批复\PRC_OffDoc"
    #string = "﻿第四条"
    string = "条"
    string = "第一条"
    #string = "各省、自治区"
    #string = "条约"
    #string = "批复可以指"
    #FindFileContains(workingPath, string, ApplyMoveFile = True)
    #FindFileContains(workingPath, string, ApplyCountString = True)

    from TCF_Params.TCFParameters import ROOTPATHList
    if args.train == False:
        ROOTPATHList = []
        global RemoveDumpSamples
        #RemoveDumpSamples = False

    #指定全加到測試集，不分配至訓練集的檔案目錄
    if args.FixedTestPATH == "" and args.test == True:
        FixedTestPATHList = GetFixedTestPATH(args)
    else:
        FixedTestPATHList = [args.FixedTestPATH]
    if args.WeiTechFormatInputPATH != "":
        FixedTestPATHList.append(args.WeiTechFormatInputPATH)
        

    if args.test == False:
        args.FixedTestPATH = ""
        info("Since args.test is False, set args.FixedTestPATH=''", icon="🧪")
    else:
        key_values("Fixed test detection", [("TRVPort", args.TRVPort), ("FixedTestPATHList", summarize_sequence(FixedTestPATHList, limit=4))], icon="·")
    #raise Exception
    DCkwargs.update({
        "FixedTestFileBound":args.FixedTestFileBound,
        })
    #DCkwargs["FixedTestFileBound"] = args.FixedTestFileBound
    return args,DCkwargs,ROOTPATHList,FixedTestPATHList

def loadLabels(args,DCkwargs=dict()):
    #讀取分類樹樹狀關係資料庫，並建立分類樹類別關係（邊）清單及分數表，並複製備份記錄到BertDatasetSubDir下。
    TreeBaseFNList = [x.strip() for x in args.TopicTreeFiles.split(",") if x.strip()]
    tpcTree,InfoScoreTable = SetTreeFiles(
        TreeBaseFNList=TreeBaseFNList,
        OutputPath = os.path.join(args.BertDatasetSubDir,"OnlyForRecord"),
        TreeSourceDir=args.TopicTreeDir)
    
    #取得標籤清單。
    '''
    LabelList = LabelListExtractor.proc(
        SQLFile=SQLFile,
        ROOTPATHList=ROOTPATHList+FixedTestPATHList,
        OnlyLettersDigits=OnlyLettersDigitsLabels)
    '''
    LabelList = sorted(set(flattenList(tpcTree)))

    if set(LabelList) == {"Negative","Positive"}:
        global RemoveDumpSamples
        RemoveDumpSamples = False
    
    LabelsToCorrect = ListDiff(LabelList,InfoScoreTable.keys())
    key_values("Topic tree labels", [
        ("Label count", len(LabelList)),
        ("InfoScore labels", summarize_sequence(list(InfoScoreTable.keys())[:5], limit=5)),
    ], icon="·")
    if len(LabelsToCorrect) > 0 and set(LabelList) != {"Negative","Positive"}:
        warning(f"The following Labels {LabelsToCorrect} are not in the TopicTree.csv which will lead an KeyError when applying sampleReader".
              format(LabelsToCorrect))
        raise Exception
    from DatasetConverter.ConverterParameters import RSTRLabelMode
    RSTRLabelList = GetRSTRLabelList(RSTRLabelMode)
    DCkwargs.update({
        "tpcTree":tpcTree,
        "InfoScoreTable":InfoScoreTable,
        "LabelList":LabelList,
        "RSTRLabelList":RSTRLabelList,
        })
    return DCkwargs
    #return tpcTree,InfoScoreTable,LabelList,DCkwargs
      
if __name__ == '__main__':
    exeTimeDict = dict()
    #解析並設定路徑相關參數。
    args,DCkwargs,ROOTPATHList,FixedTestPATHList = setArguments(DCkwargs)
    #讀取及建置分類樹結構、分數表、Label，並加入轉換參數。
    DCkwargs = loadLabels(args=args,DCkwargs=DCkwargs)

    #datasetDBDir = args.datasetDataBaseSubDir
    OUTPUTMAIN = os.path.join(
        args.BertDatasetSubDir, args.datasetDataBaseSubDir, "dataset_total_with_filename")
    OUTPUTMAIN_Counter = OUTPUTMAIN.replace("_with_filename","")+"_labels_count"
    OUTPUTMAIN_FT = OUTPUTMAIN+"_FixedTest"
    
    #如果是WeiTechworkID工作模式，因已有完成之test.sql3，不執行原有之文本轉換功能。
    if args.WeiTechworkID != "":
        MES = f"啓動WeiTechworkID工作模式 for workID {args.WeiTechworkID}"
        MPLOGGER_TCFMain.logW(MES)
        WTBertDatasetSubDir = os.path.join(args.WeiTechWorkPoolPATH,args.WeiTechworkID)
        #進行資料抽取轉換任務，輸出格式為CZJ_SamplesFile
        if args.ExtractionConverterTask != "":
            if args.ExtractionConverterTask not in ExtractionRuleDict.keys():
                MES = f"資料集抽取轉換任務{args.ExtractionConverterTask}設定不存在於ExtractionRule，中止。檢查ExtractionRule.py及任務名稱。"
                MPLOGGER_TCFMain.logW(MES)
                raise Exception
            else:
                JobInfo = ExtractionRuleDict[args.ExtractionConverterTask]
                JobInfo["DirName"] = WTBertDatasetSubDir
                print("JobInfo",JobInfo)
            Extractor(
                task=args.ExtractionConverterTask,
                FileNameInSQL3=False,JobInfo=JobInfo)
            MES = f"完成資料集抽取轉換任務{args.ExtractionConverterTask}for{WTBertDatasetSubDir}"
            MPLOGGER_TCFMain.logW(MES)
            
        try:
            #如果輸入是被他人預先切割好的dataset_total_with_filename_FixedTest，
            #重組回CZJCourpus格式，接續重新切割。
            WTdatasetDBDir = os.path.join(WTBertDatasetSubDir,"datasetDB")
            WTdatasetDBFT = os.path.join(WTBertDatasetSubDir,"dataset_total_with_filename_FixedTest.sql3")
            #print("WTdatasetDBFT",WTdatasetDBFT)
            #print("os.path.isfile(WTdatasetDBFT)",os.path.isfile(WTdatasetDBFT))
            if os.path.isfile(WTdatasetDBFT):
                print(f"Start to run CZJCorpusFileBuilder for {WTdatasetDBFT}")
                OutputCZJCorpusFN=os.path.join(WTBertDatasetSubDir,"CZJ_CorpusFile_FixedTest.sql3")
                CZJCorpusFileBuilder(
                    SourceCZJSampleFN=WTdatasetDBFT,
                    OutputCZJCorpusFN=OutputCZJCorpusFN,
                    ).Transformer()
                #備份WeiTech提供之依長度切割之dataset_total_with_filename.sql3及test.sql3
                for file in ["dataset_total_with_filename_FixedTest.sql3",
                             "test.tsv","test.sql3"]:
                    #shutil.move(WTdatasetDBFT,WTdatasetDBFT.replace(".sql3","_old_WT_by_len.sql3"))
                    src = os.path.join(WTBertDatasetSubDir,file)
                    des = os.path.join(WTBertDatasetSubDir,file).replace(
                        ".sql3","_old_WT_by_len.sql3").replace(
                            ".tsv","_old_WT_by_len.tsv")
                    if os.path.isfile(src):
                        shutil.move(src,des)
                #time.sleep(30)
                #raise Exception
            #if os.path.isfile(WTdatasetDBFT):    
                #MKDIR(WTdatasetDBDir)
                #des = os.path.join(WTdatasetDBDir,"dataset_total_with_filename_FixedTest.sql3")
                #shutil.move(WTdatasetDBFT,des)
            else:
                print(f"{WTdatasetDBFT} does NOT exist, skip CZJCorpusFileBuilder.")

            shutil.rmtree(args.BertDatasetSubDir) #清空工作目錄，以利更新。
            shutil.copytree(WTBertDatasetSubDir,args.BertDatasetSubDir)
            
            FixedTestPATHList = [args.BertDatasetSubDir]
            #print("FixedTestPATHList",FixedTestPATHList)
            #time.sleep(30)
        except Exception as e:
            print(e)
        key_values("WeiTech dataset handoff", [
            ("workID", args.WeiTechworkID),
            ("work pool", args.WeiTechWorkPoolPATH),
            ("dataset dir", args.BertDatasetSubDir),
        ], icon="·")
    #else:
    #依照目錄設定，由txt檔產製資料集檔案。
    section("Dataset file generation", detail="開始產製資料集檔案。", icon="🧾")
    from DatasetConverter.ConverterParameters import DataAugmentationGoal
    #print(f"{Fore.LIGHTYELLOW_EX}args.BertDatasetSubDir:{args.BertDatasetSubDir}{Fore.RESET}")
    #time.sleep(15)
    df = BuildSamplesDfFromPaths(
        datasetSubDir = args.BertDatasetSubDir,
        ROOTPATHList = ROOTPATHList,
        #SQLFile = SQLFile,
        OUTPUTMAIN = OUTPUTMAIN,
        OUTPUTMAIN_Counter = OUTPUTMAIN_Counter,
        nProcess = nProcess,
        DCkwargs = DCkwargs,
        start_time=exeTimeDict["stage_start_time"])
    
    #以下排序程式碼會將輸出依文本及檔名排序，以供快速查閱中文亂碼，僅供debug使用。
    #正式產製訓練資料時，務必mark，否則會因沒有亂數排序，導致訓練資料集label不平衡。
    #df = df.sort_values(['text', 'file'], ascending=[1, 1])

    #輸出總表，包含所有樣本之label、text及檔名資訊
    DTBJobs = []
    IndexCols = ["text", "Src"]
    DTBJobs.append(dfOutputer(df, OUTPUTMAIN, IndexCols=IndexCols))
    
    #將轉換成完成之資料集df以Sunburst視覺化方式顯示，並輸出html存檔。
    #if SQLFile != "":
        #StasticSwitch = False
    from DatasetConverter.ConverterParameters import StasticSwitch
    if StasticSwitch == True:
        DTBJobs.extend(GenStasticsVisJobs(df, args.BertDatasetSubDir))
    
    if len(df) < 2000000:
        DTBJnProcess = nProcess
    else:
        DTBJnProcess = nProcessSPC
    #將DTBJobs送入多進程執行。
    multicoreJob(DTBJobs,nProcess=DTBJnProcess).run()
    
    section("Generate dataset files", icon="📦")
    key_values("Dataset generation handoff", [
        ("elapsed seconds", f"{time.time() - exeTimeDict['stage_start_time']:.4f}"),
        ("FixedTestPATHList", summarize_sequence(FixedTestPATHList, limit=4)),
        ("OUTPUTMAIN", OUTPUTMAIN),
    ], icon="·")
    
    if args.ESDataConfigFile != "":
        #esJob = json.load(open(args.ESDataConfigFile))
        from ESDataConfigFile import esJob
    else:
        esJob = dict()
    nDict = DatasetGenerator(df,
                     OUTPUTMAIN=OUTPUTMAIN,
                     IndexCols=IndexCols,
                     DatasetRatio=DatasetRatioDict,
                     DataAugmentationGoal=DataAugmentationGoal,
                     FixedTestPATHList=FixedTestPATHList,
                     esJob = esJob,
                     DCkwargs=DCkwargs,
                     #datasetCountOFN = datasetCountOFN,
                     nProcess=nProcess,
                     datasetSubDir=args.BertDatasetSubDir).run()
    
    elapsed = time.time()-exeTimeDict["stage_start_time"]
    stage_done("DataConverter", elapsed)
    key_values("Converted sample counts", sorted(nDict.items()), icon="·")
    nTotalTrainable = nDict["train"]+nDict["validation"]
    nTotalTest = nDict["test"]+nDict["fixed_test"]+nDict["Elasticsearch"]
    nTotalConverted = nTotalTrainable+nTotalTest
    if nTotalConverted == 0:
        MES = "-"*50+"\n"
        MES += "The total number of all samples is ZERO! Something wrong and BertClassfier won't run!\n"
        MES += "Make sure that:\n"
        MES += "1.The port setting is correct and FixedTest_{port} data are fine.\n"
        MES += "2.For ElasticSearch Database, remerber to use -ESCFFile ABC\n"
        MES += "3.For WTF, remember to set -WTFInpPath {InputPath} -WTFOptPath {OutputPath} and -WTFSepWorkPool if necessary.\n"
        MPLOGGER_TCFMain.logW(MES)
        raise Exception
    if args.test == True and nTotalTest == 0:
        MES = "-"*50+"\n"
        MES += "The total number of test samples is ZERO, but test mode is enabled!\n"
        MES += "Make sure that FixedTest, Elasticsearch, or dataset test split settings provide test samples.\n"
        MPLOGGER_TCFMain.logW(MES)
        raise Exception
    #刪除資料集df，釋放記憶體。
    del df
    exeTimeDict["DataConverter"] = f"{time.time()-exeTimeDict['stage_start_time']:.2f}"
    key_values("DataConverter timing", sorted(exeTimeDict.items()), icon="·")
    TaskConnector(SrcTask="DataConverter",DesTask="RunClassfier",
                  WorkingDir=args.BertDatasetSubDir,logFile="TCFMain.log").proc()
