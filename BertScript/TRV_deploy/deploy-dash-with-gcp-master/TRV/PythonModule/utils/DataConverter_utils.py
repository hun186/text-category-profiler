import os
import re
import platform
import sqlite3 as lite
import glob
import shutil
import argparse
import json
import collections
import time
import pathlib
import numpy as np

from utils.utilities import CapWords
from utils.utilities import OSWALK
#from utils.utilities import pathSeqFromFN
from utils.utilities import pathSpliter
from utils.utilities import PathSEP
from utils.utilities import UniqueList
from utils.utilities import ListDiff
from utils.MP_utils import MPlogger


def LoadTree(file, OnlyLettersDigitsLabels = False):
    result = []
    with open(file,'rt',encoding='utf-8') as f:
        for line in f:
            terms = line.split("#")[0].strip().split(",")
            terms = [x.strip() for x in terms]
            if len(terms)<3:
                continue
            result.append(terms[0:2])
    result = [
        LabelNormalizer.proc(x,
                             UniqueSorted = False,
                             OnlyLettersDigits = OnlyLettersDigitsLabels,
                             ) for x in result]
    return result

def GetRoots(tree, OnlyLettersDigitsLabels = False):
    print("tree", tree)
    print("OnlyLettersDigitsLabels",OnlyLettersDigitsLabels)
    result = []
    for [tpc,subtpc] in tree:
        if all([tpc.lower()!=subtpc2.lower() for [tpc2,subtpc2] in tree]):
            result.append(tpc)
    #result = UniqueList(result)
    result = LabelNormalizer.proc(result,
                                  OnlyLettersDigits = OnlyLettersDigitsLabels)
    return result

def GetNodes(tree):#, OnlyLettersDigitsLabels = False):
    #print("tree", tree)
    #print("OnlyLettersDigitsLabels",OnlyLettersDigitsLabels)
    result = []
    for [tpc,subtpc] in tree:
        result.extend([tpc,subtpc])
    #result = LabelNormalizer.proc(result,
                                  #OnlyLettersDigits = OnlyLettersDigitsLabels)
    return result

                
def GetSubTopics(topicList,tree):
    #result = []
    Parents = topicList.copy()
    result = Parents.copy()
    while(Parents != []):
        #print("In while, tpcTree",tpcTree)
        #print("In while, len(tpcTree)",len(tpcTree))
        NextLVNodes = GetSubNodes(tree,Parents)
        result.extend(NextLVNodes)
        Parents = NextLVNodes.copy()
    '''
    subtpcFound = True
    while(subtpcFound):
        subtpcFound = False #reset
        for [tpc,subtpc] in tree:
            if tpc in result:
                result.append(subtpc)
                tree.remove([tpc,subtpc])
                subtpcFound = True
    '''
    return result

#回傳下一級節點，不包含出發節點。
def GetSubNodes(tree,Parents):
    '''
    Parameters
    ----------
    tree : List of Edges (a List of edge in form of [src,des])
        DESCRIPTION.
    Parents : List of nodes
        DESCRIPTION.

    Returns
    -------
    result : TYPE
        DESCRIPTION.

    '''
    result = []
    #print("IN GSN, Par", Parents)
    #print("IN GSN tree", tree)
    for [tpc,subtpc] in tree:
        #print("tpc,subtpc", tpc,subtpc)
        #print("tpc in Parents", tpc in Parents)
        #print("="*50)
        if tpc in Parents:
            result.append(subtpc)
    result = UniqueList(result)
    return result

def GetInducedSubgraph(tree, NodeSet):
    result = []
    for [tpc,subtpc] in tree:
        if all([x in NodeSet for x in [tpc,subtpc]]):
            result.append([tpc,subtpc])
    return result

def GetClosestMatchingParent(tree, node, MatchingNodeSets,
                             ReturnOnlyOneClosestParent = True):
    if node in MatchingNodeSets:
        return [node]
    ReversedTree = [[subtpc,tpc] for [tpc,subtpc] in tree]
    result = []
    CurrentChildren = [node]
    while CurrentChildren != [] :
        candidates = GetSubNodes(ReversedTree, CurrentChildren)
        for candi in candidates:
            if candi in MatchingNodeSets:
                result.append(candi)
                if ReturnOnlyOneClosestParent == True:
                    return result
        CurrentChildren = candidates
    return result
        

def BuildInfoScoreTable(TreeFile,
                        OnlyLettersDigitsLabels = False,
                        datasetSubDir = ""
                        ):
    result = {}
    tpcTree = LoadTree(TreeFile,
                       OnlyLettersDigitsLabels= OnlyLettersDigitsLabels)
    RootTopics = GetRoots(tpcTree,
                          OnlyLettersDigitsLabels = OnlyLettersDigitsLabels)
    print("RootTopics",RootTopics)
    #print("tpcTree",tpcTree)
    #print("len(tpcTree)",len(tpcTree))
    tpcs = GetSubTopics(RootTopics,tpcTree)
    '''
    tpcs = []
    for root in RootTopics:
        tpcs.extend(GetSubTopics([root],tpcTree))
    '''
    #print("tpcTree af",tpcTree)
    #print("len(tpcTree) af",len(tpcTree))
    AllTpcs = UniqueList(tpcs)
    #LeftEdges = tpcTree
    VisitedEdges = []
    VisitedNodes = []
    Roots = RootTopics.copy()
    #定義根節點分數
    NodeScoreTable = {
        "Scrap":{"NodeScore":-500,"ChildBonus":10},
        "Uncertainty":{"NodeScore":0,"ChildBonus":0},
        "Informative":{"NodeScore":100,"ChildBonus":10}}
    for node in Roots:
        if node not in NodeScoreTable.keys():
            NodeScoreTable[node] = {"NodeScore":10,"ChildBonus":10}
    print("Roots",Roots)
    #RTSourceScoreTable = RootScoreTable.copy()
    #for node in Roots:
        #if node not in RootScoreTable.keys():
            #RTSourceScoreTable[node] = {"NodeScore":10,"ChildBonus":10}
    for RT in Roots:
        Parents = [RT]
        while(Parents != []):
            #print("In while, tpcTree",tpcTree)
            #print("In while, len(tpcTree)",len(tpcTree))
            NextLVNodes = GetSubNodes(tpcTree,Parents)
            #print("Parents", Parents)
            print("="*50)
            print("NextLVNodes", NextLVNodes)
            for [tpc,subtpc] in tpcTree:
                #print("result",result)
                #print("1st phase, {}".format([tpc,subtpc]))
                if all([tpc in Parents,
                        subtpc in NextLVNodes,
                        ]):
                #if subtpc in NextLVNodes:
                    #print("tpc,subtpc",tpc,subtpc)
                    if subtpc not in NodeScoreTable.keys():
                        NodeScoreTable[subtpc] = {}
                    NodeScoreTable[subtpc]["NodeScore"] = NodeScoreTable[tpc]["NodeScore"]+NodeScoreTable[tpc]["ChildBonus"]
                    NodeScoreTable[subtpc]["ChildBonus"] = NodeScoreTable[tpc]["ChildBonus"]
                    VisitedEdges.append([tpc,subtpc])
                
            #LeftEdges = ListDiff(LeftEdges,VisitedEdges)
            for [tpc,subtpc] in tpcTree:
                #print("2nd phase, {}".format([tpc,subtpc]))
                #print("result",result)
                if all([tpc in NextLVNodes,
                        subtpc in NextLVNodes,
                        ]):
                    if NodeScoreTable[subtpc]["NodeScore"] <= NodeScoreTable[tpc]["NodeScore"]:
                        print(f"{tpc},{subtpc} are boths in NextLVNodes with score subtpc] <= tpc, updating score of subtpc.")
                        NodeScoreTable[subtpc]["NodeScore"] = NodeScoreTable[tpc]["NodeScore"] + NodeScoreTable[tpc]["ChildBonus"]
                        #result[subtpc] = result[tpc]+10
                VisitedEdges.append([tpc,subtpc])
            Parents = NextLVNodes.copy()
        #LeftEdges = ListDiff(LeftEdges,VisitedEdges)
    #print("results", result)        
    #raise Exception
    for key in NodeScoreTable.keys():
        result[key] = NodeScoreTable[key]["NodeScore"]
    result = collections.OrderedDict(sorted(result.items()))
    if datasetSubDir != "":
        f = open(os.path.join(datasetSubDir,"InfoScoreTable.json"), "w")
        json.dump(result, f, indent=4)
        f.close()
    return result

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
            '''
            if "\\" in FilePath:
                LabelMarker = "\\#T#\[.*?\]"
            else:
                LabelMarker = "/#T#\[.*?\]"
            '''
            LabelMarker = PathSEP(FilePath)+"#T#\[.*?\]"
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
        outputDir = outputDirs[-1]
        for outdir in outputDirs:
            if any([x.startswith("model") for x in os.listdir(outdir)
                    if "000" not in x or 
                    time.time()-pathlib.Path(
                        os.path.join(outdir,x)).stat().st_ctime>60*20]):
                outputDir = outdir
                #BatCMD += "--output_dir={} {}".format(
                    #f"./{outputDir}/", LineBreaker)
                MES = f"Using the model in {outputDir} to predict."
                MPlogger.logW(MES)
                break
        return datasetDir,outputDir
    
class NewestModelMainFileNamePickers:
    def proc(OldOutputDir=None):
        r = re.compile("^model\.ckpt-\d+.*$")
        ModelMFN = sorted(set([
            ".".join(x.split(".")[0:2]) for x in list(filter(r.match, A))]))[-1]
        MES = f"Using the model {ModelMFN} in {OldOutputDir} to transferring training."
        MPlogger.logW(MES)
        return ModelMFN
    
def ClassfierOptionParser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--TRVPort", help="Input the port for hosting the web.",
        type=int, default=8050)
    parser.add_argument(
        "-pub", "--public", help="Publish the web.", action="store_true")
    
    parser.add_argument(
        "-tr", "--train", help="Train the model.", action="store_true")
    parser.add_argument(
        "-ts", "--test", help="Predict the test set.", action="store_true")
    parser.add_argument(
        "-mdlDir", "--modelDir", help="Use the model in the dir to predict test set.",
        type=str, default="")
    parser.add_argument(
        "-FB", "--FixedTestFileBound", help="Input the bound for the number of file for Fixed Test Dir.",
        type=int, default=0)
    parser.add_argument(
        "-ISlbd", "--InfoScoreSumLowerBound", help="Input the lower bound for InfoScoreSum.",
        type=int, default=-999999999)
    
    args = parser.parse_args()
    return args

