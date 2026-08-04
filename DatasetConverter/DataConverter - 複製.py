from PackageImport import PackageImporter
PackageImporter.proc()
#載入DatasetConverter參數設定
try:
    import DatasetConverter.ConverterParameters as ConverterParameters
except:
    pass
from TCF_Params.TCFParameters import WorkPoolROOT
from TCF_Params.TCFParameters import TopicTextCrawlerROOT
from TCF_Params.TCFParameters import DatasetConverterROOT
from TCF_Params.TCFParameters import ROOTPATHList
from TCF_Params.TCFParameters import BertClassfierPath

try:
    from ConverterParameters import RBDict
    from ConverterParameters import DataCleanerRePatternDict
    #from ConverterParameters import TopicTextCrawlerROOT
    #from ConverterParameters import ROOTPATHList
    from ConverterParameters import StasticSwitch
    #from ConverterParameters import BertClassfierPath
    from ConverterParameters import ConvertToSpec
    from ConverterParameters import TreeBinaryTarget
    from ConverterParameters import UniqueLabel
    from ConverterParameters import UniqueSortedLabels
    from ConverterParameters import RSTRLabelMode
    from ConverterParameters import RemoveDumpSamples
    from ConverterParameters import OnlyLettersDigitsLabels
    from ConverterParameters import DatasetRatioDict
    from ConverterParameters import WIDTH
    #from ConverterParameters import sampleLenLBD
    #from ConverterParameters import nBound
    from ConverterParameters import sampleMethod
    from ConverterParameters import DataAugmentationGoal
    from ConverterParameters import RemoveDumpArticle_FT
except:
    from DatasetConverter.ConverterParameters import RBDict
    from DatasetConverter.ConverterParameters import DataCleanerRePatternDict
    #from DatasetConverter.ConverterParameters import TopicTextCrawlerROOT
    #from DatasetConverter.ConverterParameters import ROOTPATHList
    from DatasetConverter.ConverterParameters import StasticSwitch
    #from DatasetConverter.ConverterParameters import BertClassfierPath
    from DatasetConverter.ConverterParameters import ConvertToSpec
    from DatasetConverter.ConverterParameters import TreeBinaryTarget
    from DatasetConverter.ConverterParameters import UniqueLabel
    from DatasetConverter.ConverterParameters import UniqueSortedLabels
    from DatasetConverter.ConverterParameters import RSTRLabelMode
    from DatasetConverter.ConverterParameters import RemoveDumpSamples
    from DatasetConverter.ConverterParameters import OnlyLettersDigitsLabels
    from DatasetConverter.ConverterParameters import DatasetRatioDict
    from DatasetConverter.ConverterParameters import WIDTH
    #from DatasetConverter.ConverterParameters import sampleLenLBD
    #from DatasetConverter.ConverterParameters import nBound
    from DatasetConverter.ConverterParameters import sampleMethod
    from DatasetConverter.ConverterParameters import DataAugmentationGoal
    from DatasetConverter.ConverterParameters import RemoveDumpArticle_FT



import sys
import os
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
from utils.utilities import mem_report
from utils.TCF_utils import GetTreeFilePath
from utils.TCF_utils import GetRSTRLabelList


from utils.DataConverter_utils import ClassfierOptionParser
from utils.DataConverter_utils import getLabelsFromOSWALK
from utils.DataConverter_utils import getLabelsFromFileName
from utils.DataConverter_utils import getSrcFromFileName
from utils.DataConverter_utils import LabelsStringReader
from utils.DataConverter_utils import LabelListExtractor
from utils.DataConverter_utils import datasetDirOutputDirPickers
from utils.DataConverter_utils import LoadTree
from utils.DataConverter_utils import GetNodes
from utils.DataConverter_utils import GetSubTopics
from utils.DataConverter_utils import GetClosestMatchingParent
from utils.DataConverter_utils import GetInducedSubgraph
from utils.DataConverter_utils import BuildInfoScoreTable
from utils.DataConverter_utils import GetFixedTestPATH
from utils.DataConverter_utils import RANDLoader
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
from utils.utilities import freeGPUConformer
from utils.TextProcessor_utils import textReader
from utils.TextProcessor_utils import TxtFileHashDictBuilder

from utils.DB_utils import sqlite3Query
from utils.DB_utils import getESData
#from utils.Tika_pdf_to_txt import ExtractTxt
'''
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
                 FixedTestFileBound=6000,
                 SQLFile = "",
                 esJob = dict(), #es_token,indexname,startDay,endDay
                 RemoveDumpArticle = True,
                 ReadQuery = "",
                 WIDTH = 256,
                 Mode = "FullCut", #全文切割模式:"FullCut"
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
                 ):
        self.datasetSubDir = datasetSubDir
        self.ROOTPATHList = ROOTPATHList
        self.SQLFile = SQLFile
        self.esJob = esJob
        self.RemoveDumpArticle = RemoveDumpArticle
        self.nProcess = nProcess
        #self.start_time = start_time
        #self.nProcess = nProcess
        self.fileList = fileList
        self.FixedTestFileBound = FixedTestFileBound
        
        #if len(self.esJob)>0:# != {}:
        if self.esJob != dict():
            #print("self.esJob",self.esJob)
            #getESData回傳為[{"id":3234},{"id":1356},{"id":1263}]
            self.esJob["retItem"] = {"id"}
            self.ESidList = [x['id'] for x in getESData(self.esJob)]
            #print("self.ESidList",self.ESidList)
            self.esSelectedJob = self.esJob.copy()
            #self.esSelectedJob["selectedMessage"] = False
            self.esSelectedJob["selectedMessage"] = True
            self.esSelectedJob["retItem"] = {"id","subject"}
            self.ESSelectedDictList = {
                x['id']:x['subject'] for x in getESData(self.esSelectedJob)}
            #print("self.ESSelectedidList",self.ESSelectedDictList)
            from collections import Counter
            df_selectedMessage = pd.DataFrame.from_dict(
                self.ESSelectedDictList, 
                #Counter(self.ESidList),
                orient='index',columns = ["subject"])
            #df_selectedMessage.reset_index()
            #print("df_selectedMessage",df_selectedMessage)
            #print("df_selectedMessage.columns",df_selectedMessage.columns)
            df_selectedMessage.columns = ["subject"]
            #OUTPUTMAIN = os.path.join("dataset", "ESselect")
            OUTPUTMAIN = os.path.join(self.datasetSubDir, "ESselect")
            dfOutputer(df_selectedMessage, OMFN=OUTPUTMAIN,
                       tsvIndex=True,SQL_table="selectedMessage").run()
     
        
            #time.sleep(10)
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
        if self.fileList == []:
            self.fileList = self.BuildFileList()
        
        self.ReadQuery = ReadQuery
        #print(self.fileList[0:10])
        #print(len(self.fileList))
        #raise Exception
        self.WIDTH = WIDTH
        self.Mode = Mode
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
        

        
    def show(self):
        print("開始生成資料集轉換任務工作物件。")
        print("共輸入{}個目錄，前三個為{}".format(
            len(ROOTPATHList),ROOTPATHList[:3]))
    
    def RemoveDumpArt(self,fiL):
        MES = "Start to remove duplicated article."
        #ShowElapsedTime(self.start_time)
        nOri = len(fiL)
        DTBJobs = [
            TxtFileHashDictBuilder(fiLCK, hashalg = "sha1")
            for fiLCK in SplitList(fiL, nChunks=self.nProcess)]
        hashDictList = multicoreJob(
            DTBJobs, nProcess=self.nProcess).run()
        #print("="*50)
        #print("hashDictList",hashDictList)
        #raise Exception
        hashDict = hashDictList[0].copy()
        for mydict in hashDictList[1:]:
            hashDict.update(mydict)
        hashDict = {value : key for (key, value) in hashDict.items()}
        fiL = list(hashDict.values())
        #nOri = sum([len(mydict) for mydict in hashDictList])
                       
        return fiL
    
    def BuildFileList(self):
        fiL = []
        start_time = time.time()
        print("="*50)
        print("self.ROOTPATHList",self.ROOTPATHList)
        if self.SQLFile == "":
            for PATH in self.ROOTPATHList:
                filePaths = OSWALK(PATH, Extension = ["txt","AI2"])
                #print("filePaths",filePaths)
                #排除路徑內有UnTagged或UnSpec的檔案。
                filePaths = [x for x in filePaths 
                             if "UnTagged".lower() not in x.lower() and 
                              "UnSpec".lower() not in x.lower() ]
                fiL.extend(filePaths)
            nOri = len(fiL)
            if self.RemoveDumpArticle == True:
                fiL = self.RemoveDumpArt(fiL)
            #print("fiL",fiL)
            
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
                
        if self.RemoveDumpArticle == True:
            nDiff = nOri - len(fiL)
            MES = f"After remove {nDiff} duplicated article from {nOri},"
            MES += f" there are still totally {len(fiL)} files left.\n"
            MES += "Finished removing duplicated article."
            MPlogger.logW(MES)
            #ShowElapsedTime(self.start_time)
            ShowStepCostTime(start_time, "removing duplicated article.")

        else:
            MES = "RemoveDumpArticle_FT is False, "
            MES += f"there are still totally {len(fiL)} files.\n"
            MPlogger.logW(MES)
        #print("fiL",fiL)
        #raise Exception
        #time.sleep(8)
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
            for node in sorted(set(GetNodes(tpcTree))):
                CMPNodeList = GetClosestMatchingParent(
                    tpcTree, node, RSTRLabelList,
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
        MES="LabelConvertDict Mapping:\n"
        if sum([LabelConvertDict[x] != x for x in LabelConvertDict.keys()]) == 0:
            MES += "Identity Map\n"
        else:
            for key in sorted(LabelConvertDict.keys()):
                MES += "{:<35s} : {:>35s}\n".format(key, LabelConvertDict[key])
                #print("{:<35s} : {:>35s}".format(key, LabelConvertDict[key]))
        #print(f"共有{len(LabelConvertDict.keys())}個標籤。")
        MES += f"共有{len(LabelConvertDict.keys())}個標籤。"
        MKDIR(self.datasetSubDir)
        MPlogger.logW(
            MES=MES,logSubDir=self.datasetSubDir,logFile="dataset.txt")
        with open(os.path.join(self.datasetSubDir, "TopicAnalysis_LabelList_Including_NonOccuring.txt"),
             'wt',encoding='utf-8') as f:
            #for y in sorted(set([LabelConvertDict[x] for x in DNTags])):
            for y in sorted(set([LabelConvertDict[x] for x in LabelList])):
                f.write(y+"\n")
        return LabelConvertDict
    
    def run(self):
        DTBJobs = []
        ESidSet = set(self.ESidList)
        for (file,esJob) in [
                (file,{}) for file in self.fileList]+[
                    (id,self.esJob) for id in self.ESidList]:
            if "FixedTest_" in file or file in ESidSet:
                RBActiveFin = False
            else:
                RBActiveFin = self.RBActive
            Job = SampleReader(
                file = file,
                LabelList = self.LabelList, 
                width = self.WIDTH,
                Mode = self.Mode, 
                ConvertToSpec = self.ConvertToSpec, 
                #nBound = self.nBound,
                #sampleLenLBD = self.sampleLenLBD,
                sampleMethod = self.sampleMethod,
                LabelConvertDict = self.LabelConvertDict,
                RBDict = self.RBDict,
                UniqueLabel = self.UniqueLabel,
                SQLFile = self.SQLFile,
                esJob = esJob,
                InfoScoreTable = self.InfoScoreTable,
                UniqueSortedLabels = self.UniqueSortedLabels,
                OnlyLettersDigitsLabels = self.OnlyLettersDigitsLabels,
                RBActive = RBActiveFin,
                DataCleanerRePatternDict = self.DataCleanerRePatternDict
                )
            DTBJobs.append(Job)
        #random.shuffle(DTBJobs)
        return DTBJobs

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
    for x in rows_list[0:3]:
        print(str(x)+"\n")
    df = pd.DataFrame(rows_list)
    #RemoveDumpSamples = False
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
    start_time=None):
    
    if "nProcess" in DCkwargs.keys():
        nProcess = DCkwargs["nProcess"]
    else:
        nProcess = 1
    LabelList = DCkwargs["LabelList"]
    if datasetCountOFN == None:
        datasetCountOFN = os.path.join(datasetSubDir,"dataset.txt")
    MES = "IN BSDF, DCkwargs \n" + str(DCkwargs)
    MPlogger.logW(MES,printOnScreen=False)
    DCJG = DataConvertJobGenerater(
        datasetSubDir=datasetSubDir,
        ROOTPATHList=ROOTPATHList,
        
        SQLFile = SQLFile,
        esJob = esJob,
        RemoveDumpArticle = RemoveDumpArticle,
        #nProcess = nProcess,
        **DCkwargs
        )
    
    datasetCountOFP = open(datasetCountOFN,mode='at',encoding='utf-8')
    DTBJobs = DCJG.run()
    #將DTBJobs送入多進程執行。
    print("Start to load samples as a list of list of samples:MPresult.")
    ShowElapsedTime(start_time)
    MPresult = multicoreJob(
        DTBJobs, nProcess=nProcess).run()
    print("Finshed loading samples as a list of list of samples:MPresult.")
    print("Start to zip *MPresult as rows_list, MultiLabelCountList.")
    ShowElapsedTime(start_time)
    if MPresult == []:
        rows_list = []
    else:
        rows_list, MultiLabelCountList = zip(*MPresult)
    print("Finshed loading samples as a list of list of samples.")
    ShowElapsedTime(start_time)
    rows_list = flattenList(rows_list)
    print("Finshed join the list of list of samples.")
    ShowElapsedTime(start_time)
    print("="*50)
    print("Finshed Constructing Row_List.")
    ShowElapsedTime(start_time)
    
    #計算樣本標記數量。
    if len(rows_list) > 0:
        df_Counter = pd.DataFrame.from_dict(
            Counter([row['OutLabel'] for row in rows_list]),
            orient='index')
        df_Counter.columns = ["Loaded Samples Count"]
        df_Counter.sort_values(by='Loaded Samples Count',ascending=False, inplace=True)
        #樣本擴增
        if DataAugmentationGoal > 0:
            #print("OutLabel Counter before Data Augmentation",c)
            #print(f"DataAugmentationGoal is {DataAugmentationGoal}, Start to apply Data Augmentation.")        
            #MES = "="*50
            #MES += f"\nOutLabel Counter before Data Augmentation:\n{c}\n"
            #datasetCountOFP.write(MES)        
            AguPoolDict = {}
            for i,row in enumerate(rows_list):
                if row['OutLabel'] not in AguPoolDict:
                    AguPoolDict[row['OutLabel']] = [i]
                elif len(AguPoolDict[row['OutLabel']]) < DataAugmentationGoal:
                    AguPoolDict[row['OutLabel']].append(i)
            for Label in AguPoolDict:
                Len = len(AguPoolDict[Label])
                ct = Len
                #print(f"for {Label} ct is {ct}")
                AugPointer = 0
                while(ct< DataAugmentationGoal):
                    idx = AguPoolDict[Label][AugPointer % Len]
                    text = rows_list[idx]['text']
                    
                    rows_list.append({'OutLabel':Label,
                                      'text':f"{ct}_{text}"
                        })
                    AugPointer += 1
                    ct += 1
            
            #OutLabels = [row['OutLabel'] for row in rows_list]
            #c = Counter(OutLabels)
            #print("OutLabel Counter after Data Augmentation",c)
            #import pprint
            #pprint.pprint(c)
            
            df_Counter_Aug = pd.DataFrame.from_dict(
                Counter([row['OutLabel'] for row in rows_list]),
                orient='index')
            df_Counter_Aug.columns = ["Augmentated Samples Count"]
            df_Counter = pd.concat([df_Counter, df_Counter_Aug],axis=1)                    
            del AguPoolDict
            random.shuffle(rows_list)
        if OUTPUTMAIN_Counter is None:
            OUTPUTMAIN_Counter = OUTPUTMAIN.replace("_with_filename","")+"_labels_count"
        dfOutputer(df_Counter, OUTPUTMAIN_Counter,
                   tsvIndex=True,SQL_table=Count_SQL_table).run()
        ShowElapsedTime(start_time)
    else:
        print("When loading {}, the resulting row_list is empty".
              format(ROOTPATHList))


    df = ArticleRowsListToDF(rows_list,start_time=start_time)
    #依書籍或google蒐索爬文所獲情況，決定Src及SrcType。
    if df.shape[0] != 0:
        df = multicoreJob(nProcess=nProcess).parallelize_dataframe(df, GetDataSRC)

    print("Finished constructing Src and type column.")
    ShowElapsedTime(start_time)
    
    #儲存標籤映射函數。
    for y in sorted(set([DCJG.LabelConvertDict[x] for x in LabelList])):
        datasetCountOFP.write(y+"\n")
    '''
    #計算樣本標記數量。
    print("="*50)
    #print("df",df)
    if df.shape[0] > 0:
        MES = "="*50
        MES += "\n出現的類別標籤數量分布為\n{}\n".format(
            df["OutLabel"].value_counts().to_string())
        MES += "-"*50
        MES += "\n共有{}個標籤".format(len(df["OutLabel"].value_counts()))
        MES += "\n具多標籤的樣本數量統計結果為\n{}".format(
            MultiLabCt(MultiLabelCountList))
        print(MES)
        datasetCountOFP.write(MES)
    else:
        print("When loading {}, the resulting df is empty".
              format(ROOTPATHList))
    print("="*50)
    '''
    #統計輸出樣本數量
    MES = "\nThere are totally {} samples converted, cf {} or {} for filename.".format(
        df.shape[0], OUTPUTMAIN+".tsv", OUTPUTMAIN+".sql3")
    MES += "\n"+"="*50+"\n"
    print(MES)
    datasetCountOFP.write(MES)
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

def TextNormalize(df):
    for removeChar in ['\0','\u3000','\t', '\ufeff']:
        df.text = df.text.str.replace(removeChar,'')
    df.text = df.text.replace('"','“')
    df.text = df.text.replace("'","’")
    return df

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
    class Outputer:
        def __init__(self, df, OUTPUTMAIN, logFile, 
                     IndexCols=[],DataAugmentationGoal=0):
            self.df = df
            self.OUTPUTMAIN = OUTPUTMAIN
            self.logFile = logFile
            self.IndexCols = IndexCols
            self.DataAugmentationGoal = DataAugmentationGoal
        def show(self):
            print("df:\n", self.df)
            print("OUTPUTMAIN", self.OUTPUTMAIN)
        def run(self):
            dfOutputer(self.df[['OutLabel','text']],
                       self.OUTPUTMAIN, IndexCols=self.IndexCols).run()
            if '\0' in open(self.OUTPUTMAIN+".tsv", encoding="utf-8").read():
                CheckResult = "are"
            else:
                CheckResult = "are not"
            MES = ("For {}, there {} null bytes in your input file").format(
                self.OUTPUTMAIN+".tsv", CheckResult)
            MPlogger.logW(MES=MES,logFile=self.logFile)

            
    def __init__(self, df,
                 OUTPUTMAIN = "",
                 IndexCols = [],
                 datasetSubDir = "dataset",
                 DatasetRatio = {},
                 FixedTestPATHList = [],
                 esJob = dict(),
                 DCkwargs = {},
                 datasetCountOFN = None,
                 nProcess = 1
                 ):
        self.df = df
        self.OUTPUTMAIN = OUTPUTMAIN
        self.OUTPUTMAIN_FT = OUTPUTMAIN+"_FixedTest"
        self.OUTPUTMAIN_es = OUTPUTMAIN+"_ES"
        self.IndexCols = IndexCols
        self.datasetSubDir = datasetSubDir
        self.DatasetRatio = DatasetRatio
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

        
    def show(self):
        #print("df:\n", self.df)
        print("FixedTestPATHList", self.FixedTestPATHList)
        print("logFile", self.logFile)
        print("OUTPUTMAIN", self.OUTPUTMAIN)
        print("="*50)
    def run(self):
        self.show()
        #設定訓練集、驗證集及測試集比例。
        TrainSetRatio = self.DatasetRatio["Train"]
        ValidationSetRatio = self.DatasetRatio["Validation"]
        TestSetRatio = self.DatasetRatio["Test"]
        #依照比例分配資料點至訓練集、驗證集及測試集。
        nDataset = self.df.shape[0]
        nTestSet = int(nDataset*TestSetRatio)
        nTrainSet = int(nDataset*TrainSetRatio)
        nValidationSet = nDataset - nTestSet - nTrainSet
        nDict = {"train":nTrainSet, "validation":nValidationSet, "test":nTestSet}
        #FNDdict = {"train":"train.tsv", "validation":"dev.tsv", "test":"test.tsv"}
        MFNDdict = {"train":"train", "validation":"dev", "test":"test"}
    
        Used = 0
        #計算強制做為測試集的txt檔清單。
        FixfiL = []
        for Path in self.FixedTestPATHList:
            FixfiL.extend(OSWALK(Path, Extension = ["txt","AI2"]))
        #生成各資料集。
        DTBJobs = []
        for key in nDict.keys():
            Partdf = self.df.loc[Used:Used+nDict[key],:].copy()
            MES = "\nGenerating {} set,\n".format(key)
            MPlogger.logW(MES=MES,logFile=self.logFile)
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
                print("Adding Fixed Test Samples with {} \n".
                      format(self.FixedTestPATHList))
                #print("Partdf bf add FT",Partdf)
                Partdf = pd.concat([Partdf, FT_df], ignore_index=True)
                print("Start to output FT_df to MainFN {} \n".
                      format(self.OUTPUTMAIN_FT))
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
                    print("Adding ES Test Samples with {} \n".
                          format(self.esJob["indexname"]))
                    #print("Partdf bf con es",Partdf)
                    #Partdf = pd.concat([Partdf, es_df], ignore_index=True)
                    #print("Partdf af es",Partdf)
                    #raise Exception
                else:
                    es_df = pd.DataFrame()
                #print("Partdf bf add ES",Partdf)
                Partdf = pd.concat([Partdf, es_df], ignore_index=True)
                #print("Partdf af add ES",Partdf)
                #raise Exception
                print("Start to output es_df to MainFN {} \n".
                      format(self.OUTPUTMAIN_es))
                dfOutputer(es_df, self.OUTPUTMAIN_es, IndexCols=self.IndexCols).run()
                #print("Partdf",Partdf)
                #print(Partdf.columns)
                #print("Src",Partdf["Src"])
                #print("file",Partdf["file"])
                #raise Exception
            if Partdf.shape[0] == 0:
                continue
            #Partdf["dataType"] = key
            #Partdf["dataType"] = Partdf["dataType"].astype("category")
            #print("Partdf",Partdf)
            #time.sleep(8)
            #將文本正規化，去除'\0','\u3000','\t', '\ufeff'等字元。
            #for removeChar in ['\0','\u3000','\t', '\ufeff']:
                #Partdf.text = Partdf.text.str.replace(removeChar,'')
            
            #Partdf = multicoreJob(nProcess=1).parallelize_dataframe(Partdf, TextNormalize)
            Partdf = multicoreJob(nProcess=self.nProcess).parallelize_dataframe(Partdf, TextNormalize)
            #dfOutputer(Partdf[['OutLabel','text']], MFNDdict[key]).run()
            #累加已分配樣本之記數器，以記錄下一個分配資料集的正確起點。
            Used += nDict[key]

            #輸出各資料集至檔案，MFNDdict[key]為各資料集之輸出主檔名。
            DTBJobs.append(
                self.Outputer(Partdf,
                              OUTPUTMAIN = os.path.join(self.datasetSubDir, MFNDdict[key]),
                              logFile = self.logFile))
        nDict["fixed_test"] = len(FT_df)
        nDict["Elasticsearch"] = len(es_df)
        for key in ["train","validation","test"]:
            if key in ["train","validation"]:
                nsamples = "{}".format(nDict[key])
                MES = "For {} set, there are totally {} samples.\n".format(
                    key,nsamples)
            elif key in ["test"]:
                MES = "For test set, there are totally {} samples".format(
                    nDict["test"]+nDict["fixed_test"]+nDict["Elasticsearch"])
                MES += f"where {nDict['fixed_test']} samples are from Fixted_Test source and \n"
                MES += f"{nDict['Elasticsearch']} samples are from Elasticsearch source.\n"
            MPlogger.logW(MES=MES,logFile=self.logFile)
            

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
        return nDict
    
def GenStasticsVisJobs(df, datasetSubDir):
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
        MES = f"When try to PickSelectTxt, the SrcRoot is UNSETTED!!"
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
    
if __name__ == '__main__':
    if "DatasetConverter" in os.getcwd():
        os.chdir("../")
    #SrcRoot = r"D:\shared\TopicClassification\DatasetConverter\PickSelectTxt"
    #PickSelectTxt(SrcRoot=SrcRoot)
    #print(type(sys.argv[2]))
    #if type(sys.argv[2]) is Namespace:
        #args = sys.argv[2]
    #else:
    args = ClassfierOptionParser()
    if args.ESDataConfigFile != "":
        #esJob = json.load(open(args.ESDataConfigFile))
        from ESDataConfigFile import esJob
    else:
        esJob = dict()
    #if args.ModelType not in ["TF15Bert","PytorchXLM"]:
        #MES = "The setting ModelType is not available,"
        #MES += "only TF15Bert(default) or PytorchXLM is avaliable"
        #print(MES)
        #raise Exception
    if args.ModelType == "TF15Bert":
        testResFile = ["predict.tf_record","test_results.tsv"]       
    elif args.ModelType == "PytorchXLM":
        testResFile = ["test_results.tsv"]
    else:
        MES = "The setting ModelType is not available,"
        MES += "only TF15Bert(default) or PytorchXLM is avaliable"
        print(MES)
        raise Exception        
    execTime = timeNow()
    start_time = time.time()
    stage_time_cost = []
    '''
    nCPU = mp.cpu_count()
    if nCPU > 30:
        nProcess = int(nCPU*1.3)
    else:
        nProcess = 10
    
    print("""進程數設定為{}，請依硬體CPU資源數量，
          妥善設定進程數量，以免程式崩潰！如果沒有把握，請將進程數設為1，以策安全。""".
          format(nProcess))
    '''
    nProcess = multicoreJob().ComputeNProcess()
    nProcessSPC = multicoreJob().ComputeSPCNProcess()
    #未指定 -tr的話，ClassfierOptionParser會將TrainAfterConvert設為False
    TrainAfterConvert = getattr(args,"train")
    #TrainAfterConvert = False
    ContinueTrainAfterConvert = False
    TestAfterConvert = getattr(args,"test")
    #TestAfterConvert = True
    
    if not os.path.isdir(BertClassfierPath):
        BertClassfierPath = "dataset"
    
    #datasetSubDir = "dataset"
    MKDIR(WorkPoolROOT)
    if args.BertDatasetSubDir != "":
        BertDatasetSubDir = args.BertDatasetSubDir
    else:
        BertDatasetSubDir = os.path.join(
            WorkPoolROOT,f"dataset_{execTime}_{args.ModelType}_pt{args.TRVPort}")
        if TrainAfterConvert == True:
            BertDatasetSubDir += "_tr"
    #WorkPoolROOT
    MKDIR(BertDatasetSubDir)
    
    path = r"C:\Users\Bruce2\Downloads\TopicTextCrawler_reload\C_wikisourceSearch\批复\PRC_OffDoc"
    #string = "﻿第四条"
    string = "条"
    string = "第一条"
    #string = "各省、自治区"
    #string = "条约"
    #string = "批复可以指"
    #FindFileContains(path, string, ApplyMoveFile = True)
    #FindFileContains(path, string, ApplyCountString = True)

    TreeFile = GetTreeFilePath()
    
    tpcTree = LoadTree(
        TreeFile,OnlyLettersDigitsLabels= OnlyLettersDigitsLabels)


    des = os.path.join(BertDatasetSubDir,"TopicTree.csv")
    shutil.copy(TreeFile, des)
    
    InfoScoreTable = BuildInfoScoreTable(
        TreeFile,OnlyLettersDigitsLabels,
        OutputPath = BertDatasetSubDir)

    #LOADRAND = True
    #if LOADRAND == True:
        #RANDLoader().show()
    #raise Exception
    
    if TrainAfterConvert == False:
        ROOTPATHList = []
        RemoveDumpSamples = False

    '''
    ROOTPATHList = [fileNameNormalizer.proc(TopicTextCrawlerROOT+x)
                    if "../" not in x else x for x in ROOTPATHList]
    '''
    #FNReplace()
    
    SQLFile = ""
    #SQLFile = "Books_Metadata.sql3"

    #指定全加到測試集，不分配至訓練集的檔案目錄
    if args.FixedTestPATH == "":
        FixedTestPATHList = GetFixedTestPATH(args)
    else:
        FixedTestPATHList = [args.FixedTestPATH]
    if args.WeiTechFormatInputPATH != "":
        FixedTestPATHList.append(args.WeiTechFormatInputPATH)
    print("="*50)
    print(f"According the TRVPort argument {args.TRVPort}, \
          the detected FixedTestPATHList is", FixedTestPATHList)
    print("="*50)
    
    #FixedTestPATHList = []
    #取得標籤清單。
    '''
    LabelList = LabelListExtractor.proc(
        SQLFile=SQLFile,
        ROOTPATHList=ROOTPATHList+FixedTestPATHList,
        OnlyLettersDigits=OnlyLettersDigitsLabels)
    '''
    LabelList = sorted(set(flattenList(tpcTree)))
    #print("LabelList", LabelList)

    if set(LabelList) == {"Negative","Positive"}:
        RemoveDumpSamples = False
    
    #print("="*50)
    #print("InfoScoreTable",InfoScoreTable)
    LabelsToCorrect = ListDiff(LabelList,InfoScoreTable.keys())
    #print("set(LabelList)", set(LabelList))
    if len(LabelsToCorrect) > 0 and set(LabelList) != {"Negative","Positive"}:
        print("The following Labels {} are not in the TopicTree.csv which will lead an KeyError when applying sampleReader".
              format(LabelsToCorrect))
        raise Exception

    OUTPUTMAIN = os.path.join(BertDatasetSubDir, "dataset_total_with_filename")
    OUTPUTMAIN_Counter = OUTPUTMAIN.replace("_with_filename","")+"_labels_count"
    OUTPUTMAIN_FT = OUTPUTMAIN+"_FixedTest"

    #限定讀取目錄設定
    FolderConstrainList = []
    #FolderConstrainList = ["\\Books\\"]
  
    RSTRLabelList = GetRSTRLabelList(RSTRLabelMode)

    DCkwargs = {
        "FixedTestFileBound":args.FixedTestFileBound,
        "WIDTH" : WIDTH, #樣本切割長度
        "Mode" : "FullCut", #全文切割模式:"FullCut"
        "ConvertToSpec" : ConvertToSpec,
        "LabelList" : LabelList,
        "sampleMethod" : sampleMethod,
        #"nBound" : nBound,
        #"sampleLenLBD" : sampleLenLBD,#取樣長度下限
        "TreeBinaryTarget" : TreeBinaryTarget,
        "UniqueLabel" : UniqueLabel,
        "nProcess" : nProcess,
        "InfoScoreTable":InfoScoreTable,
        "UniqueSortedLabels":UniqueSortedLabels, #讀取Label清單字串時，是否進行Label Unique
        "OnlyLettersDigitsLabels":OnlyLettersDigitsLabels, #讀取Label清單字串時，是否去除非字母或數字字符
        "tpcTree":tpcTree, #類別樹
        "RSTRLabelList":RSTRLabelList,
        "RBDict":RBDict, #Rule-Based字典，key為正規表示式，vallue為類別。
        "RBActive":True, #Rule-Based標籤轉換，暫定為active
        "DataCleanerRePatternDict":DataCleanerRePatternDict, #輸入txt後的資料清理字典
        }
    
    #依照目錄設定，由txt檔產製資料集檔案。
    MES = "開始產製資料集檔案。"
    MPlogger.logW(MES)
    df = BuildSamplesDfFromPaths(
        datasetSubDir = BertDatasetSubDir,
        ROOTPATHList = ROOTPATHList,
        SQLFile = SQLFile,
        DataAugmentationGoal = DataAugmentationGoal,
        OUTPUTMAIN = OUTPUTMAIN,
        OUTPUTMAIN_Counter = OUTPUTMAIN_Counter,
        #nProcess = nProcess,
        DCkwargs = DCkwargs,
        start_time=start_time)
    
    #以下排序程式碼會將輸出依文本及檔名排序，以供快速查閱中文亂碼，僅供debug使用。
    #正式產製訓練資料時，務必mark，否則會因沒有亂數排序，導致訓練資料集label不平衡。
    #df = df.sort_values(['text', 'file'], ascending=[1, 1])

    #輸出總表，包含所有樣本之label、text及檔名資訊
    DTBJobs = []
    IndexCols = ["text", "Src"]
    DTBJobs.append(dfOutputer(df, OUTPUTMAIN, IndexCols=IndexCols))
    
    #將轉換成完成之資料集df以Sunburst視覺化方式顯示，並輸出html存檔。
    if SQLFile != "":
        StasticSwitch = False
    if StasticSwitch == True:
        DTBJobs.extend(GenStasticsVisJobs(df, BertDatasetSubDir))
   
    #將DTBJobs送入多進程執行。
    '''
    AvaMem = psutil.virtual_memory().available
    nProcessSPC = nProcess
    if len(df) > 2000000:
        nProcessSPC = int(AvaMem/(3*1024*1024*1024))
        print("nProcessSPC is", nProcessSPC)
    '''

    if len(df) < 2000000:
        DTBJnProcess = nProcess
    else:
        DTBJnProcess = nProcessSPC

    multicoreJob(DTBJobs,nProcess=DTBJnProcess).run()
    print("Start to Generate dataset files.")
    stage_start_time = time.time()
    print(ShowElapsedTime(start_time))
    
    nDict = DatasetGenerator(df,
                     OUTPUTMAIN=OUTPUTMAIN,
                     IndexCols=IndexCols,
                     DatasetRatio=DatasetRatioDict,
                     FixedTestPATHList=FixedTestPATHList,
                     esJob = esJob,
                     DCkwargs=DCkwargs,
                     #datasetCountOFN = datasetCountOFN,
                     nProcess=nProcess,
                     datasetSubDir=BertDatasetSubDir).run()

    print("All DatasetConverter job are finished.")
    print(ShowElapsedTime(start_time))
    print(time.time()-stage_start_time)
    stage_time_cost.append((f"DataConverter Stage",f"{time.time()-stage_start_time:.2f}"))
    
    print("nDict",nDict)
    nTotalTest = nDict["test"]+nDict["fixed_test"]+nDict["Elasticsearch"]
    if nTotalTest == 0:
        MES = "-"*50+"\n"
        MES += "The total number of all samples is ZERO! Something wrong and BertClassfier won't run!"
        MES += "Make sure that:\n"
        MES += "1.The port setting is correct and FixedTest_\{port\} data are fine.\n"
        MES += "2.For ElasticSearch Database, remerber to use -ESCFFile ABC\n"
        MES += "3.For WTF, remember to set -WTFInpPath \{InputPath\} -WTFOptPath \{OutputPath\} and -WTFSepWorkPool if necessary.\n"
        MES = "-"*50+"\n"
        MPlogger.logW(MES)
        raise Exception
    
    #刪除資料集df，釋放記憶體。
    del df
    
    
    
    
    
    
    
