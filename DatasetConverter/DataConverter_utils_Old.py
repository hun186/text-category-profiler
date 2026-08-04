import os
import re
import platform
import sqlite3 as lite
import glob
import shutil

from utils.utilities import CapWords
from utils.utilities import OSWALK
#from utils.utilities import pathSeqFromFN
from utils.utilities import pathSpliter
from utils.utilities import PathSEP
from utils.utilities import UniqueList
from utils.utilities import ListDiff
from utils.MP_utils import MPlogger


def LoadTree(file):
    TACAPaths = []
    TACAPaths.extend(glob.glob("C:/Users/*/Documents/*/python codes"))
    for DirPath in TACAPaths:
        src = os.path.join(DirPath,"TACA","DB","ZMRAND","Imported","TopicTree.txt")
        if os.path.isfile(src):
            #shutil.delete(file)
            try:
                os.remove(file)
            except:
                pass
            shutil.copy(src,file)
    result = []
    with open(file,'rt',encoding='utf-8') as f:
        for line in f:
            terms = line.split("#")[0].strip().split(",")
            terms = [x.strip() for x in terms]
            if len(terms)<3:
                continue
            result.append(terms[0:2])
    return result

def GetRoots(tree):
    #print("tree", tree)
    result = []
    for [tpc,subtpc] in tree:
        #print("tpc is {}, len(tree) = {}".format(tpc,len(tree)))
        if all([tpc.lower()!=subtpc2.lower() for [tpc2,subtpc2] in tree]):
            result.append(tpc)
    #result = UniqueList(result)
    result = LabelNormalizer.proc(result)
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

#回傳下一級節點，不包含出發節點。
def GetSubNodes(tree,Parents):
    result = []
    for [tpc,subtpc] in tree:
        if tpc in Parents:
            result.append(subtpc)
    result = UniqueList(result)
    return result


def BuildInfoScoreTable(TreeFile):
    result = {}
    tpcTree = LoadTree(TreeFile)
    print("TreeFile",TreeFile)
    print("tpcTree", tpcTree)
    RootTopics = GetRoots(tpcTree)
    print("RootTopics",RootTopics)
    tpcs = []
    for root in RootTopics:
        tpcs.extend(GetSubTopics(root,tpcTree))
    AllTpcs = UniqueList(tpcs)
    #LeftEdges = tpcTree.copy()
    print("2nd observatioin, tpcTree", tpcTree)
    Visited = [False]*len(tpcTree)
    #VisitedEdges = []
    VisitedNodes = []
    Parents = RootTopics
    for node in Parents:
        result[node] = 10
    #while(LeftEdges != []):
    print("Visited", Visited)
    while(any([x == False for x in Visited])):
        print("Visited", Visited)
        NextLVNodes = GetSubNodes(tpcTree,Parents)
        for i,[tpc,subtpc] in enumerate(tpcTree):
            if Visited[i] == True:
                pass
            else:
                #print("result",result)
                #print("1st phase, {}".format([tpc,subtpc]))
                if subtpc in NextLVNodes:
                    result[subtpc] = result[tpc]+10
                    #VisitedEdges.append([tpc,subtpc])
                Visited[i] = True
            
        #LeftEdges = ListDiff(LeftEdges,VisitedEdges)
        for i,[tpc,subtpc] in enumerate(tpcTree):
            if Visited[i] == True:
                pass
            else:
                print("2nd phase, {}".format([tpc,subtpc]))
                print("result",result)
                if all([tpc in NextLVNodes,
                        subtpc in NextLVNodes,
                        ]):
                    if result[subtpc] >= result[tpc]:
                        result[subtpc] = result[tpc]+10
                        Visited[i] = True
            #VisitedEdges.append([tpc,subtpc])
        Parents = NextLVNodes
        #LeftEdges = ListDiff(LeftEdges,VisitedEdges)
    print("results", result)        
    raise Exception

class LabelNormalizer:
    def proc(LabelList):
        LabelList = [' '.join([CapWords(SW, ignorePreposition = False)
                               for SW in x.split(" ")]) for x in LabelList]
        LabelList = list(filter((None).__ne__, LabelList))
        return sorted(set(LabelList))

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
    def proc(LabelsString):
        #e.g.:"['BI', 'EXT', 'Tai']"
        Labels = [label.strip().strip("'") for label in LabelsString[1:-1].split(",")]
        #Labels = [' '.join([CapWords(SW) for SW in  x.split(" ")]) for x in Labels]
        #Labels = [x.strip("'") for x in Labels]
        return LabelNormalizer.proc(LabelList=Labels)
    
class FilePathLabelsPurifier:
    def proc(FilePath,LabelMarker=None):
        if LabelMarker == None:
            '''
            if "\\" in FilePath:
                LabelMarker = "\\#T#\[.*?\]"
            else:
                LabelMarker = "/#T#\[.*?\]"
            '''
            LabelMarker = PathSEP(FilePath)+"#T#\[.*?\]"
        return re.sub(LabelMarker,"",FilePath)
    
def getLabelsFromFileName(filePath):
    Labels = []
    #pathSeq = pathSeqFromFN(file)
    pathSeq = pathSpliter.proc(filePath)
    for x in pathSeq:
        if x.startswith("#T#["):
            Labels += LabelsStringReader.proc(LabelsString=x[3:])
            #Labels += [CapWords(label) for label in x[4:-1].split(",")]
    return LabelNormalizer.proc(LabelList=Labels)

def getLabelsFromOSWALK(ROOTPATHList):
    result = []
    for PATH in ROOTPATHList:
        for file in OSWALK(PATH, Extension = "txt"):
            #標籤x格式：#T#[PRC_Think]
            result += getLabelsFromFileName(file)
            result = sorted(set(result))
    if len(result) == 0:
        print("WARNING! There is no detected labels under function"
              "(getLabelsFromOSWALK)! Check the setting ROOTPATHList.")
    return LabelNormalizer.proc(LabelList=result)

class LabelListExtractor:
    def proc(SQLFile="", ROOTPATHList=[]):
        if SQLFile != "":
            conn = lite.connect(SQLFile)
            label_query = 'SELECT topics FROM Corpus where topics != "[]"'
            topicsPool = [x[0] for x in conn.execute(label_query).fetchall()]
            LabelList = []
            for tpcList in topicsPool:
                LabelList.extend(LabelsStringReader.proc(tpcList))
            LabelList = LabelNormalizer.proc(LabelList=LabelList)
            conn.close()
            LabelSrc = "目錄及檔名"
        elif SQLFile == "":
            LabelList = getLabelsFromOSWALK(ROOTPATHList)
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
      
def getSrcFromFileName(FileName, LabelList):
    #x = ../Books/中文文章/scrap/中文古文
    #print("path is ", x)
    FolderList = [CapWords(fold) for fold in pathSpliter.proc(FileName)]
    #print("FolderList",FolderList)
    #raise Exception
    SrcType, Src = None, None
    #print("="*50)
    #print("FileName", FileName)
    #print("getLabelsFromFileName(FileName)", getLabelsFromFileName(FileName))
    for label in LabelList:
        #print("label", label)
        if label in getLabelsFromFileName(FileName):
            #Ind = FolderList.index(label)
            for i,fold in enumerate(FolderList):
                if fold.startswith("#T#") and label in getLabelsFromFileName(fold):
                    Ind = i
                    break
            #if "Books" in pathSeqFromFN(FileName):
            if "Books" in pathSpliter.proc(FileName):
                 SrcType = FolderList[Ind-1]
                 Src = FolderList[Ind+1]
            else:
                #print("FolderList",FolderList)
                SrcType = FolderList[Ind-2]
                Src = FolderList[Ind-1]
            break
    #print("SrcType, Src",SrcType, Src)
    return SrcType, Src

class datasetDirOutputDirPickers:
    def proc(ROOTPATH=None):
        r = re.compile("dataset_\d+$")
        datasetDirs = list(filter(r.match, os.listdir(ROOTPATH)))
        datasetDirs = sorted(datasetDirs, reverse=True)
        datasetDir = datasetDirs[0]
        r = re.compile("output_\d+$")
        outputDirs = list(filter(r.match, os.listdir()))
        outputDirs = sorted(outputDirs, reverse=True)
        for outdir in outputDirs:
            if any([x.startswith("model") for x in os.listdir(outdir)]):
                outputDir = outdir
                #BatCMD += "--output_dir={} {}".format(
                    #f"./{outputDir}/", LineBreaker)
                MES = f"Using the model in {outputDir} to predict."
                MPlogger.logW(MES)
                break
        return datasetDir,outputDir