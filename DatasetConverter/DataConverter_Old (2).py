import os
import pandas as pd
import csv
import random
import time
import sqlite3 as lite
from pandas.io import sql
import pandas as pd

#import plotly.io as pio; pio.renderers.default='notebook'
from plotly.offline import plot
import plotly.express as px
import textwrap
#from zhconv import convert
from opencc import OpenCC
import multiprocessing as mp
import numpy as np
import shutil

from utilities import OSWALK
from utilities import MKDIR
from utilities import timeNow
from utilities import ShowElapsedTime
#from df_utils import parallelize_dataframe
from df_utils import dfToTSV
from df_utils import dfToSQL
from df_utils import df_OutputMain
   
def parallelize_dataframe(df, func, n_cores=4):
    df_split = np.array_split(df, n_cores)
    pool = mp.Pool(n_cores)
    df = pd.concat(pool.map(func, df_split))
    pool.close()
    pool.join()
    return df
 
'''
import winreg
winreg.SetValueEx(
    winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE,
                     r'SYSTEM\CurrentControlSet\Control\FileSystem'),
    'LongPathsEnabled', None, winreg.REG_DWORD, 1)
'''

#import tokenization
#tokenizer = tokenization.FullTokenizer(
    #vocab_file='vocab.txt', do_lower_case=False)
  
def GetDataSRC(df):
    def MetaDataOfSample(x):
        #x = ../Books/中文文章/scrap/中文古文
        FolderList = x.split("\\")
        for label in LabelList:
            if label in x.split("\\"):
                Ind = FolderList.index(label)
                if "Books" in x.split("\\"):
                     DataSrcType = FolderList[Ind-1]
                     DataSrc = FolderList[Ind+1]
                else:
                     DataSrcType = FolderList[Ind-2]
                     DataSrc = FolderList[Ind-1]
                break
        return DataSrcType, DataSrc
    print("in getDataSRC, df is", df)
    print("in getDataSRC, df.columns is", df.columns)
    LabelList = list(df['InLabel'].unique())
    df['DataSrcType'], df['DataSrc'] = zip(
        *df['file'].apply(MetaDataOfSample))
    return df


'''
def add_features(df):
    if "The Economist" in df['file'].split("\\"):
        SampleExtractBound = nUpperBoundForSingleEconomist
    else:
        SampleExtractBound = nUpperBoundForSingleFile
    df['text_cut'] = df['file'].apply(
        lambda x:readSamepleForFile(x, width=256, Mode="FullCut")[0:SampleExtractBound])
    return df
'''    

def Launcher(Job, method="run"):
    #記錄任務log。
    Mes = "Run Job {}".format(Job)
    multicoreJob.logW(Mes=Mes)
    return getattr(Job, method)()
    
class multicoreJob:
    '''
    平行化任務執行管理器，將Job.method任務集送入平行化運算隊列；
    執行完畢後回傳res清單。
    DTBJobs：任務物件清單，任務執行方法為 Job.run()。
    '''
    def __init__(self, DTBJobs=None, method="run", MulticoreMode=True):
        self.DTBJobs = DTBJobs
        self.method = method
        self.MulticoreMode = MulticoreMode
        
    def logW(Mes=None, logFile="mp_processing_log.txt"):
        f = open(logFile, "at", encoding='utf8')
        f.write("{},{}\n".format(timeNow(FMT="%Y-%m-%d %H:%M:%S"),Mes))
        f.close()
    
    def run(self):
        DTBJobs = self.DTBJobs
        method = self.method
        print("="*50)
        print("執行multicorejob.run()函式，前3個任務為")
        for Job in DTBJobs[0:3]:
            print('-'*50)
            Job.show()
        res = []
        if len(DTBJobs) == 1:
            self.MulticoreMode = False
            print("There is only one job. Deactive Multiprocessing.")
        
        #將單一任務執行結果新增至res列表，俟所有任務完成，最後再換成DataFrame，
        #進行存檔或資料視覺化顯示。
        if self.MulticoreMode == False:
            print("="*50)
            print(f"""Multiprocessing is nonactive now and try pretest.
                  If everything is fine, try active Multiprocessing."""
                  .replace("\n",""))
            print("="*50)
            for Job in DTBJobs:
                #print("now processing", Job)
                #Job.show()
                res.append(Launcher(Job, method))
        else:
            print("="*50)
            print(f"""Start Multiprocessing, if the system is halted.
                  try inactive the Multiprocessing and make the PGM could 
                  run without Error or Exception. Otherwise the processing 
                  may call subprocess INFINITLY resulting in stucking 
                  in the multiprocess procedure!""".replace("\n",""))
            print("="*50)
            pool = mp.Pool(nProcess)
            DTBJobs = [(Job,method) for Job in DTBJobs]
            res = pool.starmap(Launcher, DTBJobs)
            pool.close()
            pool.join()
        return res
    

def customwrap(s,width=30):
    return "<br>".join(textwrap.wrap(s,width=width))

def LevelDVis(df,VisPath,method = "sunburst",HtmlOutput = "",
              FolderConstrainList = []):
    
    #LevelDataVisulization
    #df[VisPath[0]] = df[VisPath[0]].apply(customwrap)
    #df[VisPath[1]] = df[VisPath[1]].apply(customwrap)
    #df[VisPath[2]] = df[VisPath[2]].apply(customwrap)
    # BurstPath = [Column A, Column B, Column C]
    if HtmlOutput == "":
        HtmlOutput = "{}_{}.html".format(str(VisPath), method)
    '''
    if method == "sunburst":
        fig = px.sunburst(df,
                          path=VisPath)
    if method == "treemap":
        fig = px.treemap(df,
                          path=VisPath)
    '''
    fig = getattr(px, method)(df,path=VisPath, color='DataSrcType')
    #fig = getattr(px, method)(df,path=VisPath)
    #fig.show()
    #plot(fig)
        
    VisOutputSubDir = "LDVisual_"
    if FolderConstrainList == []:
        VisOutputSubDir += "all"
    else:
        VisOutputSubDir += 'Only'
        VisOutputSubDir += '_'.join([
            x.lstrip("\\").split("\\")[0] for x in FolderConstrainList])
        
    HtmlOutput = os.path.join(VisOutputSubDir,
                              HtmlOutput)
    #fig.update_layout(uniformtext=dict(minsize=10, mode='hide'))
    fig.write_html(HtmlOutput)
    
def wrap(s, w):
    return [s[i:i + w] for i in range(0, len(s), w)]
def tokenization_wrap(s, w):
    tokens = tokenizer.tokenize(s)
    print(tokens)
    raise Exception
    return [s[i:i + w] for i in range(0, len(s), w)]


class SampleReader():
    def __init__(self, file, LabelList, width = 1024, 
                 Mode = "FullCut", ConvertToSpec = None,
                 nBound = {"default":5000}, sampleLenLBD = 128,
                 LabelConvertDict = {},
                 #TreeBinaryMode = False,
                 TreeBinaryTarget = None
                 ):
        self.file = file
        self.LabelList = LabelList
        self.width = width
        self.Mode = Mode
        self.ConvertToSpec = ConvertToSpec
        self.nBound = nBound
        self.sampleLenLBD = sampleLenLBD
        self.LabelConvertDict = LabelConvertDict,
        #self.TreeBinaryMode = TreeBinaryMode,
        #self.TreeBinaryTarget = TreeBinaryTarget,
                               
    def show(self,):
        print("="*50)
        print("FileName:", self.file)
        print("LabelList:", self.LabelList)
        print("width:", self.width)
        print("Mode:", self.Mode)
        print("ConvertToSpec:", self.ConvertToSpec)
        
    def run(self,):
        MES = "Dealing file {}.\n".format(self.file)
        multicoreJob.logW(MES)
        #依子目錄名，決定label。
        InLabel = ""
        #如果完整檔名路徑含有特定Label，則該檔切出樣本使用該Label。
        for term in self.LabelList:
            if term in self.file.split("\\"):
                InLabel = term
                break
        #如果完整檔名路徑不含有任何Label，回傳空列表，表示無取出樣本。
        if InLabel == "":
            return []
        #讀取文本。
        try:
            text = open(
                self.file, mode="rt", encoding="utf-8").read()
        except UnicodeDecodeError:
            MES = "Reading Error occur when dealing file {}.\n".format(
                self.file)
            multicoreJob.logW(MES)
            text = open(
                self.file, mode="rt").read()
        except:
            pass
            MES = "Unknown Error occur when extracting samples from file {}.\n".format(
                self.file)
            multicoreJob.logW(MES)
            return []
        #text = Fulltext.replace("\n","")
        #去除斷行。
        text = text.replace("\n", "")
        #若遇連續空白，只留下一個空白。
        text = ' '.join(text.split())
        
        #依設定決定，要將整份文檔是否全部等長切割後，全部標註回傳。    
        #或者僅回傳第一個區塊及標註。
        if self.Mode == "FullCut":
            #全文切割為多個樣本。
            textList = wrap(text, self.width)
        else:
            #每一份txt只取前width個字元，生成一個樣本。
            textList = [text[:self.width]]
        result = []
        for text in textList:
            #如果有簡繁轉碼設定，則使用OpenCC模組進行轉換。
            if self.ConvertToSpec != None:
                cc = OpenCC(self.ConvertToSpec)
                text = cc.convert(text)
            #樣本文字大於self.sampleLenLBD，才輸出。
            if len(text) > self.sampleLenLBD-1:
                if len(self.LabelConvertDict) > 0:
                    #print("In read, label is {} and LabelConvertDict is {}"
                          #.format(label,self.LabelConvertDict))
                    OutLabel = self.LabelConvertDict[0][InLabel]
                else:
                    OutLabel = InLabel
                #print("label af is {}".format(label))
                sample = {
                    "InLabel": InLabel,
                    "OutLabel": OutLabel,
                    "text": text,
                    "file": self.file
                    }
                result.append(sample)
        if InLabel in self.nBound.keys():
            result = result[0:self.nBound[InLabel]]
        else:
            result = result[0:self.nBound["default"]]
        #回傳取出樣本。[{'label': 'xxxx', 'text': 'xxxxxx', 'file':'xxxxxx'},{...},{...},...]
        return result


def LoadTree(file):
    result = []
    with open(file,'rt',encoding='utf-8') as f:
        for line in f:
            terms = line.strip().split(",")
            if len(terms)<3:
                continue
            result.append(terms[0:2])
    return result

def GetSubTopics(topic,tree):
    result = [topic]
    subtpcFound = True
    while(subtpcFound):
        subtpcFound = False #reset
        for [tpc,subtpc] in tree:
            if tpc in result:
                result.append(subtpc)
                tree.remove([tpc,subtpc])
                subtpcFound = True
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

    

if __name__ == '__main__':
    start_time = time.time()
    nProcess = mp.cpu_count()-1
    nProcess = 1
    print("""進程數設定為{}，請依硬體CPU資源數量，
          妥善設定進程數量，以免程式崩潰！如果沒有把握，請將進程數設為1，以策安全。""".
          format(nProcess))
    if nProcess > 1:
        MulticoreMode = True
    else:
        MulticoreMode = False

    path = r"C:\Users\Bruce2\Desktop\PRC_OffDoc"
    path = r"C:\Users\Bruce2\Downloads\TopicTextCrawler_reload\C_wikisourceSearch\通知\PRC_Law"
    path = r"C:\Users\Bruce2\Downloads\TopicTextCrawler_reload\C_wikisourceSearch\通知\PRC_Law\checked"
    path = r"C:\Users\Bruce2\Downloads\TopicTextCrawler_reload\C_wikisourceSearch\通知\PRC_Law\条例"
    path = r"C:\Users\Bruce2\Downloads\TopicTextCrawler_reload\C_wikisourceSearch\通知\PRC_OffDoc\checking"
    path = r"C:\Users\Bruce2\Downloads\TopicTextCrawler_reload\C_wikisourceSearch\批复\PRC_OffDoc"
    #string = "﻿第四条"
    string = "条"
    string = "第一条"
    #string = "各省、自治区"
    #string = "条约"
    #string = "批复可以指"
    #FindFileContains(path, string, ApplyMoveFile = True)
    #FindFileContains(path, string, ApplyCountString = True)
    
    ConvertToSpec = None
    #ConvertToSpec = 'tw2s'
    ConvertToSpec = 'tw2sp'
    
    TreeFile = "TopicTree.txt"
    TreeBinaryMode = True
    #TreeBinaryMode = False
    TreeBinaryTarget = 'PRC_OffDoc'
    TreeBinaryTarget = 'PRC_Document'

    ROOTPATHList = [
        #"..\\C_GoogleSearch\\",
        #"..\\Books\\",
        #r"..\Books\中共官方及智庫報告\PRC_Think\中国工程院",
        #"..\\Books\\外國智庫",
        #"..\\Books\\英文書籍\\Foreign_Think\\The Economist",
        #"..\\C_wikisourceSearch\\",
        r"..\C_wikisourceSearch\五年规划纲要\PRC_WReport",
        #"..\\DataConv_Test\\"
        ]
    
    LabelList = ["PRC_OffDoc", "PRC_WReport",
                 "PRC_Think", "South_Sea", 
                 "CN-US_relations", 
                 #"Economist", 
                 "PRC_MediaW",
                 "Meeting",
                 "PRC_Document",
                 "COVID-19", "Foreign_Think",
                 "PRC_Law", "TW_Law", "Global_Law",
                 "informative", "scrap"]
    LabelConvertDict = {}
    
    if TreeBinaryMode == True:
        tpcTree = LoadTree(TreeFile)
        subTpcs = GetSubTopics(TreeBinaryTarget, tpcTree)
        print("subTpcs of topic {} are {}.".format(
            TreeBinaryTarget, subTpcs))
        for tpc in LabelList:
            if tpc in subTpcs:
                LabelConvertDict[tpc] = TreeBinaryTarget
            else:
                LabelConvertDict[tpc] = "Negative"
    else:
        for tpc in LabelList:
            LabelConvertDict[tpc] = tpc
    print("LabelConvertDict Mapping:")
    for key in sorted(LabelConvertDict.keys()):
        print("{:<15s} : {:>15s}".format(key, LabelConvertDict[key]))


    #指定全加到測試集的檔案目錄
    FixedTestPATHList = []
    #FixedTestPATHList = ["..\\FixedTest\\"]

    OUTPUTMAIN = "dataset_total_with_filename"

    #限定讀取目錄設定
    FolderConstrainList = []
    #FolderConstrainList = ["\\Books\\"]

    #單一檔案取樣上限
    nUpperBoundForSingleFile = 5000
    nUpperBoundForSingleEconomist = 1000 
    nBound = {"default": 5000, "Economist":1000, "Other_Think":1000}

    #樣本切割長度
    WIDTH = 256
    #全文切割模式:"FullCut"
    Mode = "FullCut"
    #取樣長度下限
    sampleLenLBD = 128
    
    #print("="*50)
    #print("Listing")
    #print(OSWALK("..\\Books\\英文書籍\\Foreign_Think\\The Economist", Extension = "txt"))
    #print(OSWALK("..\\Books\\英文書籍\\", Extension = "txt"))
    #print(os.listdir("..\\Books\\英文書籍\\"))
    #print("="*50)
    #raise Exception
    DTBJobs = []
    for PATH in ROOTPATHList:
        for file in OSWALK(PATH, Extension = "txt"):
            Job = SampleReader(file, LabelList, WIDTH,
                               Mode, ConvertToSpec, nBound,
                               sampleLenLBD = sampleLenLBD,
                               LabelConvertDict = LabelConvertDict,
                               )
            DTBJobs.append(Job)
            #Job.run()
    random.shuffle(DTBJobs)
    
    #將DTBJobs送入多進程執行。
    rows_list = multicoreJob(DTBJobs, MulticoreMode = MulticoreMode).run()
    print("Finshed loading samples as a list of list of samples.")
    print(ShowElapsedTime(start_time))
    rows_list = sum(rows_list, [])
    print("Finshed join the list of list of samples.")
    print(ShowElapsedTime(start_time))
    
    print("="*50)
    print("Finshed Constructing Row_List.")
    print(ShowElapsedTime(start_time))
    rows_list = list(filter((None).__ne__, rows_list))
    print("="*50)
    print("finished remove empty list of Row_List")
    print(ShowElapsedTime(start_time))
    random.shuffle(rows_list)
    print("="*50)
    print("Finished shffling Row_List.")
    print(ShowElapsedTime(start_time))    
    print("="*50)
    print("The first 3 of rows_list:")
    for x in rows_list[0:3]:
        print(str(x)+"\n")
    df = pd.DataFrame(rows_list)
    #df.LabelList = LabelList
    #print(df.LabelList)
    #raise Exception
    #去除重複樣本
    df = df[~df.duplicated('text')]
    print("finished remove duplicated")
    print(ShowElapsedTime(start_time))
    
    if df.shape[0] == 0:
        print("WARNING!! Dataframe df is empy!! ABORT!")
        raise Exception
    df = df.reset_index(drop=True)
    print("df af remov dup", df)
    print("df.columns af remov dup", df.columns)
    #依書籍或google蒐索爬文所獲情況，決定DataSrc及DataSrcType。
    df = parallelize_dataframe(df, GetDataSRC, n_cores=nProcess)
    #df['DataSrcType'], df['DataSrc'] = zip(
        #*df['file'].apply(MetaDataOfSample))
    #print(df['file'].apply(MetaDataOfSample))
    print("Finished constructing dataSrc and type column.")
    print(ShowElapsedTime(start_time))
    
    #以下排序程式碼會將輸出依文本及檔名排序，以供快速查閱中文亂碼，僅供debug使用。
    #正式產製訓練資料時，務必mark，否則會因沒有亂數排序，導致訓練資料集label不平衡。
    #df = df.sort_values(['text', 'file'], ascending=[1, 1])
    #將轉換成完成之資料集df存入SQL資料庫，以加速存取。
    #dfToSQL(OUTPUT.replace(".txt",".sql3"), 
                 #df,
                 #df.columns.values)
    #輸出總表，包含所有樣本之label、text及檔名資訊
    #df.to_csv(OUTPUT, sep = '\t', index = False,
              #quoting=csv.QUOTE_NONE, quotechar="", escapechar="\\")

    df_OutputMain(df, OUTPUTMAIN)
    #將轉換成完成之資料集df以Sunburst視覺化方式顯示，並輸出html存檔。
    for VisPath in [['DataSrcType', 'DataSrc', 'InLabel'],
                    ['InLabel', 'DataSrcType', 'DataSrc'],
                    ['DataSrcType', 'DataSrc', 'OutLabel'],
                    ['OutLabel', 'DataSrcType', 'DataSrc']]:
        LevelDVis(df, VisPath, method = "sunburst", 
                  FolderConstrainList = FolderConstrainList)
        LevelDVis(df, VisPath, method = "treemap",
                  FolderConstrainList = FolderConstrainList)

    #計算樣本標記數量
    print("="*50)
    if df.shape[0] > 0:
        print("出現的類別標籤數量分布為\n{}".format(df["OutLabel"].value_counts()))
    else:
        print("When loading {}, the resulting df is empty".
              format(ROOTPATHList))
    print("="*50)

    #統計輸出樣本數量
    print("There are totally {} samples converted, cf {} or {} for filename."
          .format(df.shape[0], OUTPUTMAIN+".tsv", OUTPUTMAIN+".sql3"))
    print("="*50)
    #return df

    #df = LoadSamplesMain(ROOTPATHList,
                             #FixedTestPATHList,
                             #OUTPUT,
                             #FolderConstrainList = FolderConstrainList)

    #設定訓練集、驗證集及測試集比例。
    TrainSetRatio = 0.7
    ValidationSetRatio = 0.2
    TestSetRatio = 0.1

    #依照比例分配資料點至訓練集、驗證集及測試集。
    nDataset = df.shape[0]
    if len(ROOTPATHList) > 0:
        nTestSet = int(nDataset*TestSetRatio)
        nTrainSet = int(nDataset*TrainSetRatio)
        nValidationSet = nDataset - nTestSet - nTrainSet
    else:
        nTestSet = nDataset
        nTrainSet = 0
        nValidationSet = 0
    nDict = {"train":nTrainSet, "validation":nValidationSet, "test":nTestSet}
    #FNDdict = {"train":"train.tsv", "validation":"dev.tsv", "test":"test.tsv"}
    MFNDdict = {"train":"train", "validation":"dev", "test":"test"}

    Used = 0
    #生成各資料集。
    for key in nDict.keys():
        print("="*50)
        print("Generating {} set, the source is as following:".format(key))
        Partdf = df[Used:Used+nDict[key]]
        
        '''
        if key == "test":
            FT_df = LoadSamplesMain(
                FixedTestPATHList,
                OUTPUT.replace(".txt","_fixedtest.txt"),
                FolderConstrainList = [])
            Partdf = pd.concat([Partdf, FT_df], ignore_index=True)
            print("Adding Fixed Test Samples with {}".
                  format(FixedTestPATHList))
        '''
        if Partdf.shape[0] == 0:
            continue
        Partdf['text'] = Partdf['text'].str.replace('\0','')
        Partdf['text'] = Partdf['text'].str.replace('\u3000','')
        Partdf['text'] = Partdf['text'].str.replace('\t','')
        #輸出各資料集，FNDdict[key]為各資料集之輸出檔名。
        #Partdf[['label','text']].to_csv(
            #FNDdict[key], sep = '\t', index = False,
            #quoting=csv.QUOTE_NONE, quotechar="", escapechar="\\",
            #header = False, encoding="utf-8")
        
        df_OutputMain(Partdf[['OutLabel','text']], MFNDdict[key])
        #累加已分配樣本之記數器，以記錄下一個分配資料集的正確起點。
        Used += nDict[key]
        print("Used no for set {} is {}".format(key,Used))
        if '\0' in open(MFNDdict[key]+".tsv", encoding="utf-8").read():
            print("you have null bytes in your input file")
        else:
            print("you don't have null bytes in your input file")


            


            
