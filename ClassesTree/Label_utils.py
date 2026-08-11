import os
import re
import sqlite3 as lite

from text_category_profiler.core.utilities import CapWords
from text_category_profiler.core.utilities import PathSEP
from text_category_profiler.core.utilities import pathSpliter
from text_category_profiler.core.utilities import OSWALK
from text_category_profiler.concurrency.MP_utils import MPlogger

class LabelNormalizer:
    def proc(LabelList, 
             UniqueSorted = True,
             OnlyLettersDigits = False):#, CapOnly = False):
        #CapWords:單字第一個字母大寫
        LabelList = [' '.join([CapWords(SW, ignorePreposition = False)
                               for SW in x.split(" ")]) for x in LabelList]
        #除去空白Label
        LabelList = list(filter((None).__ne__, LabelList))
        #unique並排序
        if UniqueSorted == True:
            LabelList = sorted(set(LabelList))
        if OnlyLettersDigits == True:
            LabelList = [re.sub(r'\W+', '', x).replace("_","") for x in LabelList]
        return LabelList


class LabelsQuerent:
    def proc(sql3cursor,
             Table = "Corpus",
             LabelCol = "topics", 
             HashCol = "ArticleHash",
             HashVal = "",
             FilePathCol = "FilePath",
             FilePath = ""
             ):
        conn = sql3cursor
        if FilePath != "":
            field = FilePathCol
            fieldVal = FilePath
        elif HashVal != "":
            field = HashCol
            fieldVal = HashVal         
        query = 'SELECT {} FROM {} WHERE {}=?'.format(
            LabelCol, Table, field)
        conn.commit()
        QueryRes = conn.execute(query, [fieldVal]).fetchall()
        Labels = []
        for x in QueryRes:
            #print(x[0],type(x[0]))
            readerRes = LabelsStringReader.proc(LabelsString=x[0])
            Labels += readerRes
            #print("type(ReaderRes)",type(readerRes))
            #print("ReaderRes",readerRes)
        #raise Exception
        #Labels = [
            #LabelsStringReader.proc(LabelsString=x[0]) for x in ]
        return Labels

class LabelsStringReader:
    def proc(LabelsString,
             UniqueSorted = True,
             OnlyLettersDigits = False):
        #e.g.:"['BI', 'EXT', 'Tai']"
        Labels = [label.strip().strip("'") for label in LabelsString[1:-1].split(",")]
        #Labels = [' '.join([CapWords(SW) for SW in  x.split(" ")]) for x in Labels]
        #Labels = [x.strip("'") for x in Labels]
        return LabelNormalizer.proc(LabelList=Labels,
                                    UniqueSorted=UniqueSorted,
                                    OnlyLettersDigits=OnlyLettersDigits)
    
class FilePathLabelsPurifier:
    def proc(FilePath,LabelMarker=None):
        if LabelMarker == None:
            r'''
            if "\\" in FilePath:
                LabelMarker = "\\#T#\[.*?\]"
            else:
                LabelMarker = "/#T#\[.*?\]"
            '''
            LabelMarker = PathSEP(FilePath)+r"#T#\[.*?\]"
        return re.sub(LabelMarker,"",FilePath)
    
def getLabelsFromFileName(filePath,
                          UniqueSorted = True,
                          OnlyLettersDigits = False):
    Labels = []
    #pathSeq = pathSeqFromFN(file)
    pathSeq = pathSpliter.proc(filePath)
    for x in pathSeq:
        if x.startswith("#T#["):
            Labels += LabelsStringReader.proc(LabelsString=x[3:])
            #Labels += [CapWords(label) for label in x[4:-1].split(",")]
    return LabelNormalizer.proc(LabelList=Labels,
                                UniqueSorted = UniqueSorted,
                                OnlyLettersDigits = OnlyLettersDigits)

def getLabelsFromOSWALK(ROOTPATHList,
                        OnlyLettersDigits=False):
    result = []
    for PATH in ROOTPATHList:
        for file in OSWALK(PATH, Extension = "txt"):
            #標籤x格式：#T#[PRC_Think]
            result += getLabelsFromFileName(file)
            result = sorted(set(result))
    if len(result) == 0:
        print("WARNING! There is no detected labels under function"
              "(getLabelsFromOSWALK)! Check the setting ROOTPATHList.")
    return LabelNormalizer.proc(
        LabelList=result,
        OnlyLettersDigits=OnlyLettersDigits)

class LabelListExtractor:
    def proc(SQLFile="", ROOTPATHList=[],
             OnlyLettersDigits=False):
        if SQLFile != "":
            conn = lite.connect(SQLFile)
            label_query = 'SELECT topics FROM Corpus where topics != "[]"'
            topicsPool = [x[0] for x in conn.execute(label_query).fetchall()]
            LabelList = []
            for tpcList in topicsPool:
                LabelList.extend(LabelsStringReader.proc(tpcList))
            LabelList = LabelNormalizer.proc(
                LabelList=LabelList,
                OnlyLettersDigits=OnlyLettersDigits)
            conn.close()
            LabelSrc = "目錄及檔名"
        elif SQLFile == "":
            LabelList = getLabelsFromOSWALK(
                ROOTPATHList,
                OnlyLettersDigits=OnlyLettersDigits)
            LabelSrc = "目錄及檔名"
        MES = "="*50
        MES += "由{}取得新增標籤，共計{}個，如下：{}".format(
            LabelSrc,len(LabelList),LabelList)
        MPlogger.logW(MES)
        return LabelList

class LabelListLoader:
    def proc(LabelFile):
      """See base class."""
      LabelList = []
      if os.path.isfile(LabelFile):
          with open(LabelFile,'rt',encoding='utf-8') as f:
              for line in f:
                  LabelList.append(line.strip())
          #print("lab", LabelList)
          #raise Exception
          return LabelList
      else:
          print("WARNING! LabelList File can not be found")

def GetCTOfLabel(ClassTable,Label):
    return ClassTable.get(Label,dict()).get("CT",Label)
