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

def OSWALK(ROOTPATH):
    result = []
    for dirPath, dirNames, fileNames in os.walk(ROOTPATH):
        for f in fileNames:
            result.append(os.path.join(dirPath, f))
    return result

def timeNow(FMT = "%Y%m%d%H%M%S"):
    return time.strftime(FMT, time.localtime())

def ShowElapsedTime(start_time):
    elapsed_time = time.time() - start_time
    print("It has been passed for {:.4f} seconds".format(elapsed_time))

def dfToSQL(SQLname, df, SavingDfColumns = []):
    #SavingDfColumns = ['Column Name A','Column Name B','Column Name C']
    if len(SavingDfColumns) == 0:
        SavingDfColumns = df.columns.values
    #連結sqlite資料庫
    cnx = lite.connect(SQLname)
    
    #選取dataframe 要寫入的欄位名稱
    #欄位名稱需與資料庫的欄位名稱一樣 才有辦法對照寫入
    sql_df=df.loc[:,SavingDfColumns]
    
    #if_exists 選擇 replace，若是Daily_Record 這個 table 已存在資料庫
    #將Daily_Record 表刪除並重新創建 寫入 sql_df 的資料
    sql_df.to_sql(name='sampleSrc', con=cnx, if_exists='replace')
    #創造index，以提升讀取速度。
    createSecondaryIndex = 'CREATE INDEX "text_Index" ON "sampleSrc"("text");'
    cnx.execute(createSecondaryIndex)

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

def readSameple(file, width = 1024, Mode = "FullCut"):
    #依子目錄名，決定label。
    label = ""
    for term in LabelList:
        if term in file.split("\\"):
            label = term
            break
    if label == "":
        return []
    '''
    if "informative" in file:
        label = "informative"
    elif "scrap" in file:
        label = "scrap"
    else:
        return []
    '''
    #with open(file, mode="rt", encoding="gb2312") as f:
        #text = f.read()
        
    try:
        with open(file, mode="rt", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        print("file {}, utf-8 fail".format(file))
        try:
            with open(file, mode="rt", encoding="utf-16-le") as f:
            #with open(file, mode="rt") as f:
            #with open(file, mode="rt", encoding="gb2312") as f:
                text = f.read()
                #print("text", text[0:100])
        except:
            print("file {}, utf-8 and utf-16-le fail".format(file))
            pass
            return []
    except:
        pass
        return []
             
    #text = Fulltext.replace("\n","")
    #去除斷行。
    text = text.replace("\n", "")
    #若遇連續空白，只留下一個空白。
    text = ' '.join(text.split())
    

    #依設定決定，要將整份文檔是否全部等長切割後，全部標註回傳。    
    #或者僅回傳第一個區塊及標註。
    if Mode == "FullCut":
        #全文切割為多個樣本。
        textList = wrap(text, width)
    else:
        #每一份txt只取前1024個字元，生成一個樣本。
        textList = [text[:1024]]
    result = []
    for text in textList:
        if ConvertToSpec != None:
            cc = OpenCC(ConvertToSpec)
            text = cc.convert(text)
            
        if len(text)>128:
            sample = {
                "label": label,
                "text": text,
                "file": file
                }
            result.append(sample)
    return result
        
def LoadSamplesInPath(ROOTPATH, FolderConstrainList):
    result = []
    print("OSWALK", OSWALK(ROOTPATH))
    for file in OSWALK(ROOTPATH):
        #限定讀取目錄
        if "/test/" not in file and len(FolderConstrainList) > 0:
            RdyToLoad = False
            for folder in FolderConstrainList:
                if folder in file:
                    RdyToLoad = True
            if RdyToLoad == False:
                continue
        with open("LoadedList.txt", "at", encoding='utf-8') as f:
            f.write("Loaded file {}\n".format(file))
        if "The Economist" in file.split("\\"):
            SampleExtractBound = nUpperBoundForSingleEconomist
        else:
            SampleExtractBound = nUpperBoundForSingleFile
        Samples = readSameple(file, width=256, Mode="FullCut")[
            0:SampleExtractBound]
        result.extend(Samples)
    return result

def LoadSamplesMain(ROOTPATHList,
                    FixedTestPATHList,
                    OUTPUT, FolderConstrainList = []):
    #return a dataframe of samples from files 
    #under ROOTPATH in ROOTPATHList
    #Also save the df to OUTPUT file
    #df.columns = text, label, filename
    rows_list = []
    
    for ROOTPATH in ROOTPATHList:
        print("Start to load samples for file in {}".format(ROOTPATH))
        Samples = LoadSamplesInPath(ROOTPATH, FolderConstrainList)
        rows_list.extend(Samples)  
    
    #打亂樣本順序，以達到隨機分配效果。
    random.seed(9527)
    random.shuffle(rows_list)
    
    #FixedTestPath路徑下的資料集固定排在最後，不亂數排，以固定加入測試集。

    for FixedTestPath in FixedTestPATHList:
        Samples = LoadSamplesInPath(FixedTestPath,
                                    FolderConstrainList=[])
        #print("Fixed samples", Samples)
        rows_list.extend(Samples)
        
    rows_list = list(filter((None).__ne__, rows_list))

    df = pd.DataFrame(rows_list)
    print("df",df)
    #去除重複樣本
    df = df[~df.duplicated('text')]
    df = df.reset_index(drop=True)
    
    return df

    #依書籍或google蒐索爬文所獲情況，決定DataSrc及DataSrcType。
    df['DataSrcType'], df['DataSrc'] = zip(
        *df['file'].apply(MetaDataOfSample))
    #print(df['file'].apply(MetaDataOfSample))

    #將轉換成完成之資料集df存入SQL資料庫，以加速存取。
    dfToSQL(OUTPUT.replace(".txt",".sql3"), 
                 df,
                 df.columns.values)
    #將轉換成完成之資料集df以Sunburst視覺化方式顯示，並輸出html存檔。
    for VisPath in [['DataSrcType', 'DataSrc', 'label'],
                    ['label', 'DataSrcType', 'DataSrc']]:
        LevelDVis(df, VisPath, method = "sunburst", 
                  FolderConstrainList = FolderConstrainList)
        LevelDVis(df, VisPath, method = "treemap",
                  FolderConstrainList = FolderConstrainList)

    #計算樣本標記數量
    print("="*50)
    if len(df) > 0:
        print(df["label"].value_counts())
    else:
        print("When loading {}, the resulting df is empty".
              format(ROOTPATHList))
    print("="*50)
    #輸出總表，包含所有樣本之label、text及檔名資訊
    df.to_csv(OUTPUT, sep = '\t', index = False,
              quoting=csv.QUOTE_NONE, quotechar="", escapechar="\\")
    #統計輸出樣本數量
    print("There are totally {} samples converted, cf {} for filename.".format(
        len(df), OUTPUT))
    print("="*50)
    return df

ConvertToSpec = None
#ConvertToSpec = 'tw2s'
ConvertToSpec = 'tw2sp'


ROOTPATHList = [
    #"..\\C_GoogleSearch\\",
    #"..\\Books\\",
    #"..\\C_wikisourceSearch\\",
    #"..\\C_DRC\\",
    #"..\\C_CAS\\",
    #"..\\FakeTraingPath\\"
    ]

LabelList = ["PRC_OffDoc", "PRC_Think", "South_Sea", 
             "CN-US_relations", "Economist", "PRC_MediaW",
             "informative", "scrap", "Falun Gong"]

#指定全加到測試集的檔案目錄
FixedTestPATHList = []
FixedTestPATHList = ["..\\FixedTest\\"]

OUTPUT = "dataset_total_with_filename.txt"

#限定讀取目錄設定
FolderConstrainList = []
#FolderConstrainList = ["\\Books\\"]

#單一檔案取樣上限
nUpperBoundForSingleFile = 5000
nUpperBoundForSingleEconomist = 1000 

df = LoadSamplesMain(ROOTPATHList,
                         FixedTestPATHList,
                         OUTPUT,
                         FolderConstrainList = FolderConstrainList)

#設定訓練集、驗證集及測試集比例。
TrainSetRatio = 0.8
ValidationSetRatio = 0.2
TestSetRatio = 0.0

TrainSetRatio = 0
ValidationSetRatio = 0
TestSetRatio = 1

#依照比例分配資料點至訓練集、驗證集及測試集。
nDataset = len(df)
if len(ROOTPATHList) > 0:
    nTestSet = int(nDataset*TestSetRatio)
    nTrainSet = int(nDataset*TrainSetRatio)
    nValidationSet = nDataset - nTestSet - nTrainSet
else:
    nTestSet = nDataset
    nTrainSet = 0
    nValidationSet = 0
nDict = {"train":nTrainSet, "validation":nValidationSet, "test":nTestSet}
FNDdict = {"train":"train.tsv", "validation":"dev.tsv", "test":"test.tsv"}

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
    Partdf[['label','text']].to_csv(
        FNDdict[key], sep = '\t', index = False,
        quoting=csv.QUOTE_NONE, quotechar="", escapechar="\\",
        header = False, encoding="utf-8")
    #累加已分配樣本之記數器，以記錄下一個分配資料集的正確起點。
    Used += nDict[key]

    if '\0' in open(FNDdict[key], encoding="utf-8").read():
        print("you have null bytes in your input file")
    else:
        print("you don't have null bytes in your input file")


        


        
