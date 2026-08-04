from ConverterParameters import * #載入參數設定
from ConverterParameters import DataAugmentationGoal
from ConverterParameters import RemoveDumpSamples
from ConverterParameters import RBDict
from ConverterParameters import DataCleanerRePatternDict
from PackageImport import PackageImporter
PackageImporter.proc()
import sys
import os
import ntpath
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

#import plotly.io as pio; pio.renderers.default='notebook'
from plotly.offline import plot
import plotly.express as px
import textwrap
#from zhconv import convert
from opencc import OpenCC
import multiprocessing as mp

import shutil
import argparse

from utils.utilities import CapWords
from utils.utilities import OSWALK
from utils.utilities import MKDIR
#from utilities import ShowElapsedTime


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
from sampleHandler import SampleReader

#from utilities import hash
from utils.df_utils import dfOutputer
from utils.MP_utils import multicoreJob
from utils.MP_utils import MPlogger
from utils.Dash_utils import LevelDVisProcessor
#from utilities_RAND import LoadTree
from utilities_RAND import RANDLoader

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
                 nProcess = 1,
                 fileList = [],
                 FixedTestFileBound=6000,
                 SQLFile = "", 
                 ReadQuery = "",
                 WIDTH = 256,
                 Mode = "FullCut", #全文切割模式:"FullCut"
                 ConvertToSpec = None, #繁轉簡及慣用語轉換，None,'tw2s'
                 LabelList = None,
                 nBound = {
                     "default": 5000, 
                     "Economist":1000, 
                     "Other_Think":1000
                     },
                 sampleLenLBD = 128,
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
        self.datasetSubDir = "dataset"
        self.ROOTPATHList = ROOTPATHList
        self.SQLFile = SQLFile
        self.nProcess = nProcess
        #self.start_time = start_time
        #self.nProcess = nProcess
        self.fileList = fileList
        self.FixedTestFileBound = FixedTestFileBound
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
        self.nBound = nBound
        self.sampleLenLBD = sampleLenLBD
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
        
    def BuildFileList(self):
        fiL = []
        start_time = time.time()
        MES = "Start to remove duplicated article."
        if self.SQLFile == "":
            for PATH in self.ROOTPATHList:
                filePaths = OSWALK(PATH, Extension = "txt")
                filePaths = [x for x in filePaths 
                             if "UnTagged".lower() not in x.lower() and 
                              "UnSpec".lower() not in x.lower() ]
                fiL.extend(filePaths)
            #ShowElapsedTime(self.start_time)
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
            nOri = sum([len(mydict) for mydict in hashDictList])
            
        elif self.SQLFile != "":
            conn = lite.connect(SQLFile)
            FilePath_query = 'SELECT FilePath,ArticleHash FROM Corpus WHERE topics IS NOT "[]";'
            FHP = conn.execute(FilePath_query).fetchall()
            conn.close()
            fiL = [x[0] for x in FHP]
            hashDict = {}
            for file, hashVal in FHP:
                hashDict[hashVal] = file
            fiL = list(hashDict.values())
            nOri = len(FHP)
           
        nDiff = nOri - len(fiL)
        MES = f"After remove {nDiff} duplicated article from {nOri},"
        MES += f" there are still totally {len(hashDict)} files left.\n"
        MES += "Finished removing duplicated article."
        MPlogger.logW(MES)
        #ShowElapsedTime(self.start_time)
        ShowStepCostTime(start_time, "removing duplicated article.")
        
        #如果檔案數過多，大於FixedTestFileBound，則將FixedTest_xxx目錄下
        #的檔案隨機選取一部份留下，FixedTest_xxx下其他檔案略過，以免癱瘓片段推論結果可視化介面。
        if self.FixedTestFileBound!=0 and len(fiL)>self.FixedTestFileBound:
            PartFixedTest = [x for x in fiL if "FixedTest_" in x]
            PartNonFixedTest = [x for x in fiL if "FixedTest_" not in x]
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
        for key in sorted(LabelConvertDict.keys()):
            MES += "{:<35s} : {:>35s}\n".format(key, LabelConvertDict[key])
            #print("{:<35s} : {:>35s}".format(key, LabelConvertDict[key]))
        #print(f"共有{len(LabelConvertDict.keys())}個標籤。")
        MES += f"共有{len(LabelConvertDict.keys())}個標籤。"
        print("MES",MES)
        MPlogger.logW(
            MES=MES,logFile=
            os.path.join(self.datasetSubDir, "dataset.txt"))
        with open(os.path.join(self.datasetSubDir, "TopicAnalysis_LabelList.txt"),
             'wt',encoding='utf-8') as f:
            #for y in sorted(set([LabelConvertDict[x] for x in DNTags])):
            for y in sorted(set([LabelConvertDict[x] for x in LabelList])):
                f.write(y+"\n")
        return LabelConvertDict
    
    def run(self):
        DTBJobs = []
        for file in self.fileList:
            if "FixedTest_" in file:
                RBActiveFin = False
            else:
                RBActiveFin = self.RBActive
            Job = SampleReader(
                file, self.LabelList, self.WIDTH,
                self.Mode, self.ConvertToSpec, self.nBound,
                sampleLenLBD = self.sampleLenLBD,
                LabelConvertDict = self.LabelConvertDict,
                RBDict = self.RBDict,
                UniqueLabel = self.UniqueLabel,
                SQLFile = self.SQLFile,
                InfoScoreTable = self.InfoScoreTable,
                UniqueSortedLabels = self.UniqueSortedLabels,
                OnlyLettersDigitsLabels = self.OnlyLettersDigitsLabels,
                RBActive = RBActiveFin,
                DataCleanerRePatternDict = self.DataCleanerRePatternDict
                )
            DTBJobs.append(Job)
        #random.shuffle(DTBJobs)
        return DTBJobs

def ArticleRowsListToDF(rows_list):
    rows_list = list(filter((None).__ne__, rows_list))
    print("="*50)
    print("finished remove empty list of Row_List")
    print(ShowElapsedTime(start_time))
    random.shuffle(rows_list)
    print("="*50)
    print("Finished shuffling Row_List.")
    print(ShowElapsedTime(start_time))    
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
        print(ShowElapsedTime(start_time))
        print("df af remov dup", df)
        print("df.columns af remov dup", df.columns)
    
    if df.shape[0] == 0:
        print("WARNING!! Dataframe df is empy!! ABORT!")
        #raise Exception
    df = df.reset_index(drop=True)    
    return df

def BuildSamplesDfFromPaths(
    ROOTPATHList = [],
    SQLFile = "",
    OUTPUTMAIN = os.path.join(
        "dataset", "dataset_total_with_filename"),
    #nProcess = 1,
    DCkwargs = {},
    DataAugmentationGoal=0):

    MES = "IN BSDF, DCkwargs \n" + str(DCkwargs)
    MPlogger.logW(MES)
    DCJG = DataConvertJobGenerater(
        ROOTPATHList=ROOTPATHList,
        SQLFile = SQLFile,
        #nProcess = nProcess,
        **DCkwargs
        )
    datasetCountOFP = open(datasetCountOFN,mode='at',encoding='utf-8')
    DTBJobs = DCJG.run()
    #將DTBJobs送入多進程執行。
    MPresult = multicoreJob(
        DTBJobs, nProcess=nProcess).run()
    if MPresult == []:
        rows_list = []
    else:
        rows_list, MultiLabelCountList = zip(*MPresult)
    print("Finshed loading samples as a list of list of samples.")
    print(ShowElapsedTime(start_time))
    rows_list = flattenList(rows_list)
    print("Finshed join the list of list of samples.")
    print(ShowElapsedTime(start_time))
    print("="*50)
    print("Finshed Constructing Row_List.")
    print(ShowElapsedTime(start_time))
    
    #c = 
    #print("c",c)
    #計算樣本標記數量。
    df_Counter = pd.DataFrame.from_dict(
        Counter([row['OutLabel'] for row in rows_list]),
        orient='index')
    df_Counter.columns = ["Loaded Samples Count"]
    print("df_Counter b4",df_Counter)
    df_Counter.sort_values(by='Loaded Samples Count',ascending=False, inplace=True)
    print("df_Counter af",df_Counter)
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
        #del OutLabels
        #print("rows_list af",rows_list)
        random.shuffle(rows_list)
        #MES = "="*50
        #MES += f"\nOutLabel Counter after Data Augmentation:\n{c}"
        #datasetCountOFP.write(MES)
    #os.path.join(datasetSubDir, "dataset_count")
    OUTPUTMAIN_Counter = os.path.join(os.path.dirname(OUTPUTMAIN),"dataset_count")
    dfOutputer(df_Counter, OUTPUTMAIN_Counter,
               tsvIndex=True,SQL_table="sampleCount_Main").run()
    ShowElapsedTime(start_time)
    df = ArticleRowsListToDF(rows_list)
    #依書籍或google蒐索爬文所獲情況，決定Src及SrcType。
    if df.shape[0] != 0:
        df = multicoreJob(nProcess=nProcess).parallelize_dataframe(df, GetDataSRC)

    print("Finished constructing Src and type column.")
    print(ShowElapsedTime(start_time))
    
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
                 DCkwargs = {},
                 datasetCountOFN = "dataset/dataset.txt",
                 nProcess = 1
                 ):
        self.df = df
        self.OUTPUTMAIN = OUTPUTMAIN
        self.OUTPUTMAIN_FT = OUTPUTMAIN+"_FixedTest"
        self.IndexCols = IndexCols
        self.datasetSubDir = datasetSubDir
        self.DatasetRatio = DatasetRatio
        self.FixedTestPATHList = FixedTestPATHList
        self.DCkwargs = DCkwargs
        self.logFile = datasetCountOFN
        self.nProcess = nProcess
        self.InfoScoreTable = InfoScoreTable
        
    def show(self):
        print("df:\n", self.df)
        print("FixedTestPATHList", self.FixedTestPATHList)
        print("logFile", self.logFile)
        print("OUTPUTMAIN", self.OUTPUTMAIN)
        
    def run(self):
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
            FixfiL.extend(OSWALK(Path, Extension = "txt"))
        #生成各資料集。
        DTBJobs = []
        for key in nDict.keys():
            Partdf = self.df.loc[Used:Used+nDict[key],:].copy()
            MES = "\nGenerating {} set,\n".format(key)
            MPlogger.logW(MES=MES,logFile=self.logFile)
            
            if key == "test":
                if len(FixfiL) > 0:
                    FT_df = BuildSamplesDfFromPaths(
                        ROOTPATHList = self.FixedTestPATHList,
                        OUTPUTMAIN = self.OUTPUTMAIN_FT,
                        #nProcess = self.nProcess,
                        DCkwargs = self.DCkwargs)
                else:
                    FT_df = pd.DataFrame()
                print("Adding Fixed Test Samples with {} \n".
                      format(self.FixedTestPATHList))
                Partdf = pd.concat([Partdf, FT_df], ignore_index=True)
                print("Start to output FT_df to MainFN {} \n".
                      format(self.OUTPUTMAIN_FT))
                dfOutputer(FT_df, self.OUTPUTMAIN_FT, IndexCols=self.IndexCols).run()
                
            if Partdf.shape[0] == 0:
                continue
            #將文本正規化，去除'\0','\u3000','\t', '\ufeff'等字元。
            #for removeChar in ['\0','\u3000','\t', '\ufeff']:
                #Partdf.text = Partdf.text.str.replace(removeChar,'')
            
            Partdf = multicoreJob(nProcess=1).parallelize_dataframe(Partdf, TextNormalize)
            #dfOutputer(Partdf[['OutLabel','text']], MFNDdict[key]).run()
            #累加已分配樣本之記數器，以記錄下一個分配資料集的正確起點。
            Used += nDict[key]

            #輸出各資料集至檔案，MFNDdict[key]為各資料集之輸出主檔名。
            DTBJobs.append(
                self.Outputer(Partdf,
                              OUTPUTMAIN = os.path.join(self.datasetSubDir, MFNDdict[key]),
                              logFile = self.logFile))
        nDict["fixed_test"] = len(FT_df)
        for key in ["train","validation","test"]:
            if key in ["train","validation"]:
                nsamples = "{}".format(nDict[key])
                MES = "For {} set, there are totally {} samples.\n".format(
                    key,nsamples)
            elif key in ["test"]:
                MES = "For test set, there are totally {} samples where {} samples are from Fixted_Test source.\n".format(
                    nDict["test"]+nDict["fixed_test"], nDict["fixed_test"])
            MPlogger.logW(MES=MES,logFile=self.logFile)
            

        #使用多進程儲存train、dev、test資料集。
        #樣本數太多時(如400萬筆)，如啓用狀態條，使用新的istarmap時，在第25行:
        #return (item for chunk in result for item in chunk)
        #可能會出現struct.error: 'i' format requires -2147483648 <= number <= 2147483647錯誤
        #故此處使用SafeMode
        if nDataset>4000000:
            nDFOPTProcess = 1
        else:
            nDFOPTProcess = nProcess
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

def GetTreeFilePath():
    TACAPaths = []
    TACAPaths.extend(glob.glob("C:/Users/*/Documents/*/python codes"))
    TACAPaths.extend(glob.glob("C:/Users/*/Documents"))
    
    for DirPath in TACAPaths:
        src = os.path.join(DirPath,"TACA","DB","ZMRAND","Imported","TopicTree.txt")
        if os.path.isfile(src):
            TreeFile = src
            break
    
    DBTreeFile = "C:/Users/*/Documents/TACA/DB/ZMRAND/Imported/TopicTree.txt"
    if os.path.isfile(DBTreeFile) == True:
        TreeFile = DBTreeFile
    else:
        TreeFile = "../TACA/DB/ZMRAND/Imported/TopicTree.txt"
    return TreeFile

def GetRSTRLabelList(RSTRLabelMode):
    if RSTRLabelMode == True:
        RSTRDBTreeFile = "C:/Users/*/Documents/TACA/DB/ZMRAND/Imported/TopicTree_PAK.txt"
        if os.path.isfile(RSTRDBTreeFile) == True:
            RSTRTreeFile = RSTRDBTreeFile
        else:
            RSTRTreeFile = "../TACA/DB/ZMRAND/Imported/TopicTree_PAK.txt"
        
        RSTRLabelList = sorted(set(GetNodes(LoadTree(
            RSTRTreeFile,OnlyLettersDigitsLabels= OnlyLettersDigitsLabels))))
    else:
        RSTRLabelList = []
    return RSTRLabelList

def GetFixedTestPATH(args):
    FixedTestPATHList = [
                        "Using",
                         ]
    #FixedTestPATHList = []
    FixedTestSubDir = "../FixedTest/FixedTest_"+str(args.TRVPort)
    #FTSCand = os.path.join(TopicTextCrawlerROOT,FixedTestSubDir)
    #if os.path.isdir(FTSCand) != True:
        #FixedTestSubDir = "../FixedTest"
        #FTSCand = os.path.join(TopicTextCrawlerROOT,FixedTestSubDir)
    FixedTestPATHList = [os.path.join(FixedTestSubDir,x)
                         for x in FixedTestPATHList]       
    #FixedTestPATHList = [os.path.join(TopicTextCrawlerROOT,"FixedTest",x)
                         #for x in FixedTestPATHList]
    return FixedTestPATHList

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
    #SrcRoot = r"D:\shared\TopicClassification\DatasetConverter\PickSelectTxt"
    #PickSelectTxt(SrcRoot=SrcRoot)
    args = ClassfierOptionParser()
    if args.ModelType not in ["TF15Bert","PytorchXLM"]:
        MES = "The setting ModelType is not available,"
        MES += "only TF15Bert(default) or PytorchXLM is avaliable"
        print(MES)
        raise Exception
    start_time = time.time()
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
        
    datasetSubDir = "dataset"
    MKDIR(datasetSubDir)
    
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


    InfoScoreTable = BuildInfoScoreTable(
        TreeFile,OnlyLettersDigitsLabels,
        datasetSubDir = datasetSubDir)

    #LOADRAND = True
    #if LOADRAND == True:
        #RANDLoader().show()
    #raise Exception
    
    if TrainAfterConvert == False:
        ROOTPATHList = []
        RemoveDumpSamples = False
    '''
    else:
        ROOTPATHList = [
            r"TrainSamples",
            #"../THUCNews",
            #"../DRNData",
            #r"Books",
            #r"C_GoogleSearch",
            #r"C_wikisourceSearch",
            r"C_wikisourcePortal",
            ]
    '''
    ROOTPATHList = [fileNameNormalizer.proc(TopicTextCrawlerROOT+x)
                    if "../" not in x else x for x in ROOTPATHList]
    #FNReplace()
    
    SQLFile = ""
    #SQLFile = "Books_Metadata.sql3"

    #指定全加到測試集的檔案目錄
    if args.FixedTestPATH == "":
        FixedTestPATHList = GetFixedTestPATH(args)
    else:
        FixedTestPATHList = [args.FixedTestPATH]
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
        print("The following Labels {} are not in the TopicTree.txt which will lead an KeyError when applying sampleReader".
              format(LabelsToCorrect))
        raise Exception

    OUTPUTMAIN = os.path.join(datasetSubDir, "dataset_total_with_filename")
    OUTPUTMAIN_FT = OUTPUTMAIN+"_FixedTest"

    #限定讀取目錄設定
    FolderConstrainList = []
    #FolderConstrainList = ["\\Books\\"]
  
    RSTRLabelList = GetRSTRLabelList(RSTRLabelMode)
    
    '''
    if TrainAfterConvert == True:
        RBActive = True
    else:
        if len(ListDiff(RBDict.values(),LabelList)) > 0:
            RBActive = False
        else:
            RBActive = True
    '''
    '''
    print("RBDict.values()", RBDict.values())
    print("="*50)
    print("LabelList", LabelList)
    print("="*50)
    print("="*50)
    print("ListDiff(RBDict.values(),LabelList)", ListDiff(RBDict.values(),LabelList))
    print("="*50)
    print("RBActive",RBActive)
    raise Exception
    '''
    DCkwargs = {
        "FixedTestFileBound":args.FixedTestFileBound,
        "WIDTH" : WIDTH, #樣本切割長度
        "Mode" : "FullCut", #全文切割模式:"FullCut"
        "ConvertToSpec" : ConvertToSpec,
        "LabelList" : LabelList,
        "nBound" : nBound,
        "sampleLenLBD" : sampleLenLBD,#取樣長度下限
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

    
    datasetCountOFN = os.path.join(datasetSubDir, "dataset.txt")
    open(datasetCountOFN,mode='wt',encoding='utf-8').close()
    
    #依照目錄設定，由txt檔產製資料集檔案。
    MES = "開始產製資料集檔案。"
    MPlogger.logW(MES)
    df = BuildSamplesDfFromPaths(
        ROOTPATHList = ROOTPATHList,
        SQLFile = SQLFile,
        OUTPUTMAIN = OUTPUTMAIN,
        #nProcess = nProcess,
        DCkwargs = DCkwargs,
        DataAugmentationGoal = DataAugmentationGoal)
    
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
        DTBJobs.extend(GenStasticsVisJobs(df, datasetSubDir))
   
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
    print(ShowElapsedTime(start_time))

    nDict = DatasetGenerator(df,
                     OUTPUTMAIN=OUTPUTMAIN,
                     IndexCols=IndexCols,
                     DatasetRatio=DatasetRatioDict,
                     FixedTestPATHList=FixedTestPATHList,
                     DCkwargs=DCkwargs,
                     datasetCountOFN = datasetCountOFN).run()
    
    print("All job are finished.")
    print(ShowElapsedTime(start_time))
    
    execTime = timeNow()
    if args.BertDatasetSubDir != "":
        BertDatasetSubDir = os.path.join(
            BertClassfierPath, args.BertDatasetSubDir)
    else:
        BertDatasetSubDir = os.path.join(
            BertClassfierPath,f"dataset_{execTime}_{args.ModelType}")
    if args.BertDatasetSubDirExt != "":
        BertDatasetSubDir += "_"+args.BertDatasetSubDirExt

    MKDIR(BertDatasetSubDir)
    MES = "Move {} as {}".format(datasetSubDir, BertDatasetSubDir)
    MPlogger.logW(MES)
    for file in OSWALK(datasetSubDir):
        #if getMFNFromFN(file) in ["train","dev","test"]:
        des = os.path.join(BertDatasetSubDir,getFNFromFullPath(file))
        shutil.move(file, des)
    #print("BertDatasetSubDir",BertDatasetSubDir)
    #os.system("pause")
    if TrainAfterConvert == False and TestAfterConvert == False:
        TestAfterConvert = True
    #開始進行模型訓練或推論。
    if TrainAfterConvert == False and TestAfterConvert == False:
        print("Dataset Conversion are finished and Both of args.train and args.test are False. Return.")
        os.system("pause")
        system.quit()
        
    os.chdir(BertClassfierPath)
    if TrainAfterConvert == True:
        outputDir = f"output_{execTime}_{args.ModelType}"
        MKDIR(outputDir)
        #BatCMD += ("--init_checkpoint=./chinese_rbtl3_L-3_H-1024_A-16/bert_model.ckpt"+LineBreaker)
        
        for file in [
                "TopicAnalysis_LabelList.txt", "dataset.txt",
                "InfoScoreTable.json"]:
            src = os.path.join(BertDatasetSubDir,file)
            #WaitUntilFileIsStable(src,WatchedTimeBound=10)
            des = os.path.join(outputDir,file)
            shutil.copy(src, des)

        
    #使用TF1.5 Bert模型(roberta)
    if args.ModelType == "TF15Bert":        
        WindowsAnacondaPath = 'd:/ProgramData/Anaconda3'
        WindowsAnacondaPromptCMD = os.path.join(
            WindowsAnacondaPath,'Scripts/activate.bat')
        
        if "windows" in platform.system().lower():
            LineBreaker = " ^\n"
        else:
            LineBreaker = " \\\n"
            
        BatFile = "run_classifier_script_automatic_dynamic.bat"
        BatFileTemplateFile = "run_classifier_script_automatic_dynamic_template.txt"
        #BatCMD = open(BatFile,'rt',encoding='utf-8').read()
        BatCMD = open(BatFileTemplateFile,'rt',encoding='utf-8').read()
        if "windows" in platform.system().lower():
            BatCMD = "call activate TF1.5\n\n" + BatCMD
        else:
            BatCMD = BatCMD.replace("^\n","\\\n")
    
        if TrainAfterConvert == True:
            BatCMD += ("--do_train=True"+LineBreaker)
            #BatCMD += "--output_dir={} {}".format(
                #f"./output_{execTime}/", LineBreaker)
            
        else:
            #BatCMD = BatCMD.replace("--do_train=True", "--do_train=False")
            BatCMD += ("--do_train=False"+LineBreaker)
            datasetDir, outputDir = datasetDirOutputDirPickers.proc(modelType = args.ModelType)
            if args.modelDir != "":
                outputDir = args.modelDir
            MES = f"Using the model in {outputDir} to predict."
            MPlogger.logW(MES)
        BatCMD += "--output_dir={} {}".format(f"./{outputDir}/", LineBreaker)
        BatCMD += (f"--do_predict={TestAfterConvert}"+LineBreaker)
        BatCMD += "--data_dir={} {}".format(
            f"./{BertDatasetSubDir}/", LineBreaker)
    
        #if "windows" in platform.system().lower():
            #BatCMD +=  "> server.log 2>&1 & \n\n"
        #else:
            #BatCMD +=  "2>&1 | tee server.log \n\n"
        BatCMD +=  "> server.log 2>&1 & \n\n"
    
        #BatCMD = open(BatFile,'wt',encoding='utf-8').write(BatCMD)
        MES = "\n {}\n BatCMD:\n{}\n".format("="*50, BatCMD)
        MPlogger.logW(MES)
        open(BatFile,'wt',encoding='utf-8').write(BatCMD)
        if "windows" in platform.system().lower():
            os.system(WindowsAnacondaPromptCMD)
        else:
            os.system(f"chmod 700 {BatFile}")
            BatFile = "."+os.path.sep+BatFile
        #如果之前其他推有留下的test_results或predict.tf_record，將其刪除，以免干擾後續程式驗判。
        for filename in [
                "predict.tf_record","test_results.tsv"]:
            src = os.path.join(outputDir, filename)
            if os.path.isfile(src):
                os.remove(src)
        os.system(BatFile)
        testResFile = ["predict.tf_record","test_results.tsv"]
        #假設每秒至少推論60個樣本，且至少設為20秒給推論。
        #runclassifier.py的write example速度則假設每秒至少600個
        WatchedTimeBound = max((nDict["test"]+nDict["fixed_test"])//60,20)+(
            nDict["test"]+nDict["fixed_test"])//500
    elif args.ModelType == "PytorchXLM":
        action_str = ""
        if TrainAfterConvert == True:
            action_str += "-tr "
        else:
            datasetDir, outputDir = datasetDirOutputDirPickers.proc(modelType = args.ModelType)
            if args.modelDir != "":
                outputDir = args.modelDir
        if TestAfterConvert == True:
            action_str += "-ts "
        os.system(f"python TextClassification_XLM.py \
                  -mdlDir {outputDir} -BertDataDir {BertDatasetSubDir} \
                      {action_str}")
        #if TestAfterConvert == True:
            #os.system(f"python TextClassification_XLM_Pred.py -mdlDir {outputDir}")
        testResFile = ["test_results.tsv"]
        WatchedTimeBound = 6000
    
    print("testResFile",testResFile)
    print("nDict",nDict)

    
    #WatchedTimeBound = 6000
        
    #將預測完的輸出結果移至資料集目錄。    
    if TestAfterConvert == True:
        for filename in testResFile:
            WatchedFN = os.path.join(outputDir, filename)
            WaitUntilFileIsStable(
                WatchedFN,WatchedTimeBound=WatchedTimeBound)
        for filename in testResFile:
            src = os.path.join(outputDir, filename)
            des = os.path.join(BertDatasetSubDir, filename)
            shutil.move(src,des)

        os.system(f"python count_test_accuracy.py \
                  -mdlDir {outputDir} -BertDataDir {BertDatasetSubDir}\
                      -mdlType {args.ModelType}")
        if args.public == True:
            publicOpt = "-pub"
        else:
            publicOpt = ""
        
        print("Run_Test_result_Vis",args.Run_Test_result_Vis)
        if args.Run_Test_result_Vis == True:
            os.system(f"python Test_result_Vis.py -p {args.TRVPort} \
                      {publicOpt} -ISlbd {args.InfoScoreSumLowerBound}\
                    -TRVHost {args.TRVWebHost} -VisSelf {args.VisSelfService}\
                        -mdlDir {outputDir} -BertDataDir {BertDatasetSubDir}\
                            -mdlType {args.ModelType}")
        #subprocess.call("count_test_accuracy.py", shell=True)
        #subprocess.call("Test_result_Vis.py", shell=True)
    
    #sys.exit(datasetSubDir)
    #os.system("pause")
