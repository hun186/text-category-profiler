from PackageImport import PackageImporter
PackageImporter.proc()

import os
import math
import pandas as pd
import collections
import glob
#import shutil

from utils.utilities import UniqueList
from utils.utilities import flattenList
from utils.utilities import DictSaver
from utils.utilities import MKDIRandCopy
from utils.utilities import DictIndentPrint
from utils.df_utils import dfOutputer
from utils.DataConverter_utils_Parameters import ZeroSubtreeRootList
from utils.DataConverter_utils_Parameters import SPECNodeScoreTable
#from utils.DataConverter_utils import LabelNormalizer
#import utils.DataConverter_utils as DataConverter_utils
from ClassesTree.Label_utils import LabelNormalizer

def CountDegree(edges=[],allow_multiple_edge=True):
    edges = [tuple(edge[:2]) for edge in edges]
    if allow_multiple_edge == False:
        edges = set(edges)
    nodes = set(flattenList([[x,y] for x,y in edges]))
    res = {
        "In":dict(),
        "Out":dict(),
        "In_Out":dict(),
        }
    for x in nodes:
        for key in res.keys():
            res[key][x] = 0
    for x,y in edges:
        res["In"][y] = res["Out"].get(y,0)+1
        res["Out"][x] = res["Out"].get(x,0)+1
        res["In_Out"][x] = res["In_Out"].get(x,0)+1
        res["In_Out"][y] = res["In_Out"].get(y,0)+1
    return res

def SetTreeFiles(
        TreeBaseFNList = ["TopicTree.csv","TopicTree_AK4.csv"],
        OutputPath="",
        OnlyLettersDigitsLabels=False
        ):
    '''
    Parameters
    ----------
    TreeBaseFNList : list, optional
        DESCRIPTION. 分類樹樹狀關係資料庫檔名清單。
    OutputPath : str, optional
        DESCRIPTION. 分類樹樹狀關係資料庫複製目的地。
    OnlyLettersDigitsLabels : bool, optional
        DESCRIPTION. 是否將Label名稱轉換為只有字母跟數字，現已無使用必要。

    Returns
    -------
    tpcTree : list
        DESCRIPTION. 分類樹結構。
    InfoScoreTable : dict
        DESCRIPTION. 分數字典。

    '''
    if OutputPath == "":
        print("There is no input BertDatasetSubDir! Abort the function SetTreeFile in ClassesTree_utils.")
        return
    #讀取分類樹樹狀關係資料庫，並建立分類樹類別關係（邊）清單。
    tpcTree = LoadTree(TreeBaseFNList)
    #計算分數表InfoScoreTable
    InfoScoreTable = BuildInfoScoreTable(
            tpcTree = tpcTree,
            OnlyLettersDigitsLabels=OnlyLettersDigitsLabels,
            OutputPath = OutputPath)
    #複製分類樹資料庫。
    CopyTreeFiles(TreeBaseFNList=TreeBaseFNList,desDir=OutputPath)
    print(f"SetTreeFiles ({TreeBaseFNList},InfoScoreTable) in {OutputPath}.")
    return tpcTree,InfoScoreTable

    
def GetTreeFilePath(TreeBaseFN = "TopicTree.csv"):
    TACAParPaths = []
    TACAParPaths.extend(glob.glob("./"))
    TACAParPaths.extend(glob.glob("C:/Users/*/Documents/*/python codes"))
    TACAParPaths.extend(glob.glob("C:/Users/*/Documents"))
    
    
    for DirPath in TACAParPaths:
        src = os.path.join(DirPath,"TACA","DB","ZMRAND","Imported",TreeBaseFN)
        if os.path.isfile(src):
            TreeFile = src
            return TreeFile
            break
    
    DBTreeFile = os.path.join(
        "C:/Users/*/Documents/TACA/DB/ZMRAND/Imported",TreeBaseFN)
    if os.path.isfile(DBTreeFile) == True:
        TreeFile = DBTreeFile
    else:
        TreeFile = os.path.join(
            "../TACA/DB/ZMRAND/Imported",TreeBaseFN)
    return TreeFile

def CopyTreeFiles(TreeBaseFNList,desDir):
    for file in TreeBaseFNList:
        des = os.path.join(desDir,file)
        MKDIRandCopy(GetTreeFilePath(file), des)

def LoadTree(FNList, OnlyLettersDigitsLabels = False):
    result = []
    if isinstance(FNList,str):
        FNList = [FNList]
    InfoScoreTable = dict()
    for file in FNList:
        if not os.path.isfile(file):
            file = GetTreeFilePath(TreeBaseFN = file)
        with open(file,'rt',encoding='utf-8') as f:
            for line in f:
                terms = line.split("#")[0].strip().split(",")
                terms = [x.strip() for x in terms]
                #如果沒有母節點,子節點,加入日期等三項，跳過。
                if len(terms)<3:
                    continue
                result.append(terms[0:2])
    result = [LabelNormalizer.proc(x,
                             UniqueSorted = False,
                             OnlyLettersDigits = OnlyLettersDigitsLabels,
                             ) for x in result]
    result = list(filter(None,result))
    return result

def GetRoots(tree, OnlyLettersDigitsLabels = False):
    #print("tree[:10]+...+[:10]", tree[:10]+tree[:10])
    #print("OnlyLettersDigitsLabels",OnlyLettersDigitsLabels)
    result = []
    #print(f"tree in GR,{tree}")
    tree = [edge[0:2] for edge in tree]
    #print(f"tree[:10] in GetRoots: {tree[:10]}")
    tree = list(filter(None,tree))
    #for [tpc,subtpc] in tree:
    #print(f"tree in GetRoots: {tree}")
    #for edge in tree:
        #if len(edge) != 2:
            #print("edge in DC_utils, GetRoots",edge)
            #print("len(edge)",len(edge))
    for edge in tree:
        #print("edge in DC_utils, GetRoots",edge)
        tpc,subtpc = edge
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
    result = UniqueList(result)
    return result

                
def GetSubTopics(topicList,tree,depth = math.inf, GroupByDepth = False):
    '''
    Parameters
    ----------
    topicList : list or string
        DESCRIPTION. list of parents or a string of single parent
    tree : list
        DESCRIPTION. list of edges of tree
    depth : nonnegative integer, optional
        DESCRIPTION. The default is math.inf. The maximum distance of the subtopic from parents.
    GroupByDepth : boolean, optional
        DESCRIPTION. The default is False. Return the result with grouping by distance or not.

    Returns
    -------
    result : dict or list
        DESCRIPTION. dict of subtopics grouping by depth or a list of all subtopics.

    '''
    #result = []
    #如果輸入是字串，判定可能是某個節點的名字，自動補成單一元素的清單計算。
    if isinstance(topicList,str):
        topicList = [topicList]
    Parents = topicList.copy()
    result = dict()
    result[0] = Parents.copy()
    depthct = 0
    Visted = set()
    while(Parents != [] and depthct < depth):
        depthct += 1
        NextLVNodes = GetSubNodes(tree,Parents)
        NextLVNodes = UniqueList(list(filter(
                lambda x:x not in Visted,NextLVNodes)))
        if NextLVNodes != []:
            result[depthct] = NextLVNodes.copy()
            Visted = Visted.union(result[depthct])
        Parents = NextLVNodes.copy()

    for depth in result.keys():
        result[depth] = UniqueList(result[depth])
    if GroupByDepth == False:
        result = UniqueList(flattenList([result[depth] for depth in result.keys()]))
    return result

def BuildSubTopicsDict(tree=[],depth = math.inf):
    '''
    邊為用[x,y]表示之對，tree為用邊清單表示的list。
    '''
    Nodes = GetNodes(tree)
    SubTopicsDict = dict()
    for node in Nodes:
        SubTopicsDict[node] = GetSubTopics(
            node,tree,depth=depth,GroupByDepth=True)
    #for tpc in SubTopicsDict.keys():
        #SubTopicsDict[tpc] = list(set(SubTopicsDict[tpc]))
    return SubTopicsDict
    
    
#回傳下一級節點，不包含出發節點。
def GetSubNodes(tree,Parents):
    '''
    Parameters
    ----------
    tree : list
        DESCRIPTION. List of Edges (a List of edge in form of [src,des])
    Parents : list
        DESCRIPTION. List of parents.

    Returns
    -------
    result : list
        DESCRIPTION. The subnode of the parents.

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


def BuildInfoScoreTable(TreeFile = "",
                        tpcTree =[],
                        OnlyLettersDigitsLabels = False,
                        OutputPath = "",
                        ZeroSubtreeRootList = ZeroSubtreeRootList,
                        SPECNodeScoreTable = SPECNodeScoreTable
                        ):
    result = {}
    if tpcTree == []:
        tpcTree = LoadTree(TreeFile,
                           OnlyLettersDigitsLabels= OnlyLettersDigitsLabels)
    RootTopics = GetRoots(tpcTree,
                          OnlyLettersDigitsLabels = OnlyLettersDigitsLabels)
    #print(f"After loading {TreeFile}, RootTopics is {RootTopics}")
    
    #print("tpcTree",tpcTree)
    #print(f"RootTopics is {RootTopics}")
    #time.sleep(10)
    #print("len(tpcTree)",len(tpcTree))
    tpcs = GetSubTopics(RootTopics,tpcTree)
    #print("tpcTree af",tpcTree)
    #print("len(tpcTree) af",len(tpcTree))
    AllTpcs = UniqueList(tpcs)
    #LeftEdges = tpcTree
    VisitedEdges = []
    VisitedNodes = []
    Roots = RootTopics.copy()
    #定義根節點分數
    NodeScoreTable = {
        #"Scrap":{"NodeScore":-500,"ChildBonus":10,"SPEC":True},
        #"Uncertainty":{"NodeScore":0,"ChildBonus":0,"SPEC":True},
        #"Informative":{"NodeScore":100,"ChildBonus":10,"SPEC":True},
        #"Keyword Neg Filter":{"NodeScore":-1000000,"ChildBonus":10,"SPEC":True},
        }

    for node in ZeroSubtreeRootList:
        NodeScoreTable[node] = {"NodeScore":0,"ChildBonus":0.000001,"SPEC":True}
    NodeScoreTable.update(SPECNodeScoreTable)

    for node in Roots:
        if node not in NodeScoreTable.keys():
            NodeScoreTable[node] = {"NodeScore":10,"ChildBonus":10}
    #print(f"After loading {TreeFile}, Roots is {Roots}")
    #time.sleep(10)
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
            #print("="*50)
            #print("NextLVNodes[:10]", NextLVNodes[:10])
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
                    if NodeScoreTable[subtpc].get("SPEC",False) == False:
                        NodeScoreTable[subtpc]["NodeScore"] = max(
                            NodeScoreTable[tpc]["NodeScore"]+NodeScoreTable[tpc]["ChildBonus"],
                            #NodeScoreTable[subtpc].get("NodeScore",-500))
                            NodeScoreTable[subtpc].get("NodeScore",-math.inf))
                        NodeScoreTable[subtpc]["ChildBonus"] = max(
                            NodeScoreTable[tpc]["ChildBonus"],
                            #NodeScoreTable[subtpc].get("ChildBonus",0))
                            NodeScoreTable[subtpc].get("ChildBonus",-math.inf))
                    VisitedEdges.append([tpc,subtpc])
                
            #LeftEdges = ListDiff(LeftEdges,VisitedEdges)
            for [tpc,subtpc] in tpcTree:
                #print("2nd phase, {}".format([tpc,subtpc]))
                #print("result",result)
                if all([tpc in NextLVNodes,
                        subtpc in NextLVNodes,
                        ]):
                    if NodeScoreTable[subtpc].get("SPEC",False) == False:
                        #如果計算下層節點分數時，發現存在同層互連情況，進行極化，取導流結果及原值中絕對值較大者。
                        #if NodeScoreTable[subtpc]["NodeScore"] <= NodeScoreTable[tpc]["NodeScore"]:
                        '''
                        if abs(NodeScoreTable[subtpc]["NodeScore"]) <= abs(NodeScoreTable[tpc]["NodeScore"]):
                            print(f"{tpc},{subtpc} are boths in NextLVNodes with score subtpc] <= tpc, updating score of subtpc.")
                            NodeScoreTable[subtpc]["NodeScore"] = NodeScoreTable[tpc]["NodeScore"] + NodeScoreTable[tpc]["ChildBonus"]
                        '''
                        challenger = NodeScoreTable[tpc]["NodeScore"] + NodeScoreTable[tpc]["ChildBonus"]
                        if abs(NodeScoreTable[subtpc]["NodeScore"]) < abs(challenger):
                            #print(f"{tpc},{subtpc} are boths in NextLVNodes with abs(score[subtpc]) < abs(score[tpc]+childBounus[tpc]), updating score of subtpc.")
                            NodeScoreTable[subtpc]["NodeScore"] = challenger
                        
                VisitedEdges.append([tpc,subtpc])
            Parents = NextLVNodes.copy()

    for key in NodeScoreTable.keys():
        result[key] = NodeScoreTable[key]["NodeScore"]
    result = collections.OrderedDict(sorted(result.items()))
    if OutputPath != "":
        OMFN = os.path.join(OutputPath,"InfoScoreTable")
        DictSaver.proc(result,OMFN=OMFN, filefmt = 'json')
        df = pd.DataFrame.from_dict(result,orient='index',columns=["InfoScore"])
        dfOutputer(df, OMFN,
           tsvIndex=True,SQL_table="InfoScoreTable").run()
    return result

def SubTopicsDictTest():
    tpcTree = LoadTree(["TopicTree.csv","TopicTree_AK4.csv"])
    print("tpcTree",tpcTree)
    tpcList = [
        "Navigational Warning",
        "Climate And Resource Security",
        #"Cross-Strait Relations"
        ]
    depth = math.inf
    #depth = 3
    print("paraentTpcList",tpcList)
    subTpcs = GetSubTopics(tpcList,tpcTree,depth = depth, GroupByDepth = False)    
    print("="*50)
    print("subTpcs GroupByDepth False:")
    DictIndentPrint(subTpcs)
    subTpcs = GetSubTopics(tpcList,tpcTree,depth = depth, GroupByDepth = True)
    print("="*50)
    print("subTpcs GroupByDepth True:")
    DictIndentPrint(subTpcs)
    print("="*50)
    SubTopicsDict = BuildSubTopicsDict(tpcTree)
    DictIndentPrint(SubTopicsDict["Climate And Resource Security"])
    
if __name__=='__main__':
    #SubTopicsDictTest()
    edges = [['a','b'],['a','c'],['b','d',1]]
    #DictIndentPrint(CountDegree(edges=edges,allow_multiple_edge=True))
    SubTopicsDictTest()