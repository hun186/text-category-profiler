import os
if os.getcwd().split(os.path.sep)[-1] in [
        #"DatasetConverter","BertScript",
        "EXTConverter"]:
    os.chdir("../../")
    print(f"Change working directory to {os.getcwd()}")
from PackageImport import PackageImporter
PackageImporter.proc()

import math
import re
import tqdm

#try:
    #from ExtractionRule import ExtractionRuleDict
    #from ExtractionRule import CombinationRuleDict
#except Exception as e:
    #print(e)
from DatasetConverter.EXTConverter.ExtractionRule import ExtractionRuleDict
from DatasetConverter.EXTConverter.ExtractionRule import CombinationRuleDict
from text_category_profiler.core.utilities import removeStrPrefix
from text_category_profiler.core.utilities import removeStrSuffix
from text_category_profiler.core.utilities import OSWALK
from text_category_profiler.core.utilities import MKDIR
from text_category_profiler.core.utilities import pathSpliter
from text_category_profiler.core.utilities import fileNameNormalizer
from text_category_profiler.core.utilities import getMFNFromFN
from text_category_profiler.core.utilities import getFNFromFullPath
from text_category_profiler.core.utilities import RemoveIlleagalCharForFileName
from text_category_profiler.core.utilities import DomainNameExtractor
from text_category_profiler.data.df_utils import DictRowsListToDF
from text_category_profiler.data.df_utils import dfOutputer


def ComputeOutputLabel(
        InputLabel,
        text,
        Map=dict(),
        InputLabelReMap=dict(),
        KeepUnseenInMapKey=False,
        LabPref=""):
    r'''
    Parameters
    ----------
    InputLabel : str,
        DESCRIPTION. 輸入標註。
    text : str,
        DESCRIPTION. 輸入樣本文本。
    Map : dict(), optional
        DESCRIPTION. 輸出標註及輸出標註之對應字典。例如：
        "Mapping":{
            "good":"Benign Web Link",
            "bad":{"default":"Phishing Web Link",
                   ".*\.exe$":"Malware Web Link"},
            }
    KeepUnseenInMapKey : boolean, optional
        DESCRIPTION. 如果輸出標註不在Map鍵值，是否處理此筆樣本。
    LabPref : str, optional
        DESCRIPTION. 是否對Label進行前置詞加註後，再做為最終輸出。

    Returns
    -------
    Label : str
        DESCRIPTION. 最終輸出Label。

    '''
    if KeepUnseenInMapKey is False and InputLabel not in Map.keys():
        return None
    '''
    以說明示例假定Map(Mapping)如例，
    如果原始標註InputLabel在Map的鍵值中，則取出Map[InputLabel]=MapValue計算，
    如果MapValue是一個字串(如"good"對應的value)，則輸出Label為該字串，
    如果MapValue是一個字典(如"bad"對應的value)
    ，則比對MapValue的key值（正規表示式），如果有被滿足，則輸出Label為MapValue[key]，
    否則輸出Label為MapValue["default"]
    '''
    Label = ""
    #print("InputLabelReMap",InputLabelReMap)
    if InputLabel in Map.keys():
        MapValue = Map[InputLabel]
        if isinstance(MapValue,dict):
            #初始化MatchNonDefault變數為False，如果跑完key的迴圈，
            #還沒有命中任何條件，則輸出預設值MapValue["default"]
            MatchNonDefault = False
            for key in MapValue.keys():
                if key == "default":
                    continue
                if re.search(key,text) is not None:
                    Label = MapValue[key]
                    MatchNonDefault = True
                    break
            if MatchNonDefault == False:
                Label = MapValue["default"]
        elif isinstance(MapValue,str):
            Label = MapValue
    elif len(InputLabelReMap)>0:
        for key in InputLabelReMap.keys():
            if re.search(key,InputLabel) is not None:
                candi = InputLabelReMap[key]
                #如果value是"UseInLabelAsOutLabel"，則使用輸入Label做為OutLabel，否則使用字典value。
                if candi == "UseInLabelAsOutLabel":
                    Label = InputLabel
                else:
                    Label = candi
                #如果有命中InputLabelReMap的key，則early break
                break
    #如果KeepUnseenInMapKey設定為True，且原始標註InputLabel不在Map的key值中，則直接使用原始標註做為輸出Label。
    else:
         Label = InputLabel
    Label = LabPref+Label
    return Label

def Extractor(task,FileNameInSQL3 = False, ExtractionRuleDict = dict(),
              JobInfo = dict()):
    #變數名稱轉換
    if JobInfo == dict():
        JobInfo = ExtractionRuleDict[task]
    DirName = JobInfo.get("DirName","./")
    if DirName != "":
        cwdDir = os.getcwd()
        cwdDirList = pathSpliter.proc(os.getcwd())
        tarDirList = pathSpliter.proc(DirName)
        tarRoot = tarDirList[0]       
        while(len(cwdDirList)>0):
            if cwdDirList[-1] != tarRoot:
                cwdDirList.pop()
            else:
                break
        os.chdir('/'.join(cwdDirList+tarDirList[1:]))
    print("cwd",os.getcwd())
    fileNames = JobInfo["fileNames"]
    #OUTPUTMAIN = JobInfo.get("OUTPUTMAIN","")
    #OverWriteOutput = JobInfo.get("OverWriteOutput",True)
    CZJ_SamplesFileFormatOutput = JobInfo.get("CZJ_SamplesFileFormatOutput",True)
    TestSetFormatOutput = JobInfo.get("TestSetFormatOutput",False)
    CZJ_CorpusFileFormatOutput = JobInfo.get("CZJ_CorpusFileFormatOutput",False)
    FileNameInSQL3 = JobInfo.get("FileNameInSQL3",False)
    #skipHeader = JobInfo["header"]
    Sep = JobInfo["Sep"]
    nCSVCol =  JobInfo["nCSVCol"]
    TextCol = JobInfo["TextCol"]
    LabelInfo = JobInfo["LabelInfo"]
    LabCol = LabelInfo["nCol"]
    Map = LabelInfo.get("Mapping",dict())
    InputLabelReMap = LabelInfo.get("InputLabelReMapping",dict())
    KeepUnseenInMapKey = LabelInfo.get("KeepUnseenInMapKey",True)
    LabPref = LabelInfo.get("Prefix","")
    SingleTypeUPD =  JobInfo.get("SingleTypeUPD",math.inf)
    print("-"*50)
    print(f"Start to run task {task} with {fileNames}")
    
    nCount = dict()
    #for file in OSWALK(task):
    for file in OSWALK("./"):
        #print("file",file)
        OUTPUTMAIN = JobInfo.get("OUTPUTMAIN","")
        skipHeader = JobInfo["header"]
        rows_list = []
        if any([
                re.search(FN,getFNFromFullPath(file)) for FN in fileNames
                ]):
            print("="*50)
            print(f"開始執行ExtractionConverter之Extractor，以轉換檔案{file}樣本為CZJ樣本檔SQLite格式。")
            print("CZJ欄位：file、InLabel、OutLabel、text、PartNO")
            print(f"是否保留讀入標籤不在標籤轉換映射的資料：{'是' if KeepUnseenInMapKey else '否'}")
            
            if OUTPUTMAIN == "":
                OUTPUTMAIN = os.path.splitext(file)[0]
                if SingleTypeUPD != math.inf:
                    OUTPUTMAIN += f"_SingleTypeUPD_{SingleTypeUPD}"
                OUTPUTMAIN += "_CZJ_SamplesFile"
                if FileNameInSQL3 == True:
                    OUTPUTMAIN += "_WithFN"
            
            else:
                OUTPUTMAIN = f"{os.path.dirname(file)}/{OUTPUTMAIN}"
            f=open(file,'rt',encoding = "utf-8")
            for line in f:
                #print("line",line)
                line = line.rstrip()
                try:
                    if line.startswith("#"):
                        continue
                    #依是否含有標題列設定，來決定是否略過首列。
                    if skipHeader == True:
                        skipHeader = False
                        continue
                    if nCSVCol == 2:
                        #有些CSV原始檔首欄未處理好，有出現","，故以下列方式補救。
                        rpar = line.rpartition(Sep)
                        ent = [rpar[0],rpar[2]]
                    else:
                        ent = line.split(Sep)
                    if isinstance(nCSVCol,int) == True:
                        if len(ent) != nCSVCol and LabCol != math.inf:
                            continue
                    elif isinstance(nCSVCol,list) == True:
                        if len(ent) not in nCSVCol and LabCol != math.inf:
                            continue
                        #當nCSVCol有多個容許值時，如果ent長度過短，導致ent[LabCol]無法取到時，則將其補滿到足夠取值的長度。
                        elif len(ent) in nCSVCol and len(ent) <= LabCol:
                            ent.extend([""]*(LabCol+1-len(ent)))
                    #有的檔案欄位值後面有多一個\n，將其移除。
                    ent = [x.rstrip() for x in ent]
                    text = ""
                    for col in TextCol:
                        text += ent[col]
                    FN = RemoveIlleagalCharForFileName(
                        text.replace(":","：").replace("/","／"))[:70]+".txt"
                    FN = FN[:100]
                    if LabCol == math.inf:
                        InputLabel = ""
                    else:
                        InputLabel = ent[LabCol]
                    #print("InputLabel",InputLabel)
                    Label = ComputeOutputLabel(
                        InputLabel=InputLabel,
                        text=text,
                        Map=Map,
                        InputLabelReMap=InputLabelReMap,
                        KeepUnseenInMapKey=KeepUnseenInMapKey,
                        LabPref=LabPref)
                    if any([Label is None,
                            Label == "",
                            len(text)<5,
                            nCount.get(Label,0) >= SingleTypeUPD
                            ]):
                        continue
                    if Label in nCount:
                        nCount[Label] += 1
                    else:
                        nCount[Label] = 1
                    
                    if FileNameInSQL3 == True:
                        #fileCol = SaveFN
                        fileCol = FN
                        #InLabel = Label
                        InLabel = None
                    else:
                        fileCol = None
                        InLabel = None
                    for pat in ['"',"'"]:
                        text = removeStrSuffix(removeStrPrefix(text,pat),pat)
                    sampleExpansionSet = {text}
                    if task not in ["SDSMS_Train","SDSMS_Prediction"]:
                        DN = DomainNameExtractor(link = text).proc()
                        #print("text",text)
                        #print("DN",DN)
                        sampleExpansionSet.add(DN)
                    for ctx in sampleExpansionSet:
                        sample = {
                            "file":fileCol,
                            "InLabel":InLabel,
                            "OutLabel":Label,
                            "text":ctx,
                            "PartNO":0,
                            }
                        #print("sample",sample)
                        rows_list.append(sample)
                    
                except Exception as e:
                    print(f"when handling {line}, the following error occurs:\n{e}")
            df = DictRowsListToDF(rows_list)
            print("-"*50)
            print("file",file)
            print("OUTPUTMAIN for main",OUTPUTMAIN)
            if CZJ_SamplesFileFormatOutput == True:
                dfOutputer(df, OUTPUTMAIN, OutputFormat=["sql"]).run()
            #輸出Bert測試集格式
            if TestSetFormatOutput == True:
                OUTPUTMAIN = f"{os.path.dirname(file)}/test"
                print("*"*50)
                print("OUTPUTMAIN for test",OUTPUTMAIN)
                print("-"*50)
                df_Save = df[["OutLabel","text"]]
                dfOutputer(df_Save, OUTPUTMAIN, OutputFormat=["sql","tsv"]).run()
            if CZJ_CorpusFileFormatOutput == True:
                OUTPUTMAIN = f"{os.path.dirname(file)}/CZJ_CorpusFile_{task}_FixedTest"
                print("*"*50)
                print("OUTPUTMAIN for CZJ_CorpusFileFormatOutput",OUTPUTMAIN)
                print("-"*50)
                df_Save = df[["InLabel","text"]]
                df_Save["title"] = df["file"]
                df_Save = df_Save[["title","InLabel","text"]]
                dfOutputer(df_Save, OUTPUTMAIN, OutputFormat=["sql"], SQL_table="Corpus").run()
                #import time
                #time.sleep(30)
                
    os.chdir(cwdDir)        
    
if __name__=='__main__':
    for task in [
        #"Malicious URLs dataset",
        #"DGA Detection",
        #"Phishing Site URLs",
        #"SelfDownload/C2",
        #"SelfDownload/Alexa Top 1M",
        #"SelfDownload/OpenPhish", #Updated regularlly
        #"SelfDownload/URLhaus",
        #"SelfDownload/PhishTank",
        #"===DRNData/VirusTotal_Converting/Benign Web Link", #Updated regularlly
        #"===DRNData/VirusTotal_Converting/Malicious Web Link", #Updated regularlly
        #"RealTestData/rdy to convert",
        #"LetterGreetings",
        #"SDSMS_Train",
        #"SDSMS_Prediction",
        ]:
        if task in ["RealTestData"]:
            FileNameInSQL3 = True
        else:
            FileNameInSQL3 = False
        Extractor(task,FileNameInSQL3=False,ExtractionRuleDict=ExtractionRuleDict)
        
    for task in [
        "EmbassyPages-Located Country",
        ]:
        nSubtaskUBD = math.inf
        #nSubtaskUBD = 1
        CombinationRuleDict[task]["processor"](nSubtaskUBD=nSubtaskUBD).proc()
