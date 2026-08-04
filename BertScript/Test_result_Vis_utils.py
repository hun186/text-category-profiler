from collections import Counter
import os
import re
import random
import math
import numpy as np
from statistics import mean
from statistics import stdev
from statistics import variance

#from VisParameters import ZeroSubtreeRootList
from VisParameters import LocalExemptDict
from VisParameters import GlobalExemptDict
from VisParameters import SimilarPiecesExemptMethod
from VisParameters import SimilarPiecesExemptSetting

#print("Finish loading Vis")
'''
from VisParameters_DRN import LocalExemptDict_DRN
LocalExemptDict.update(LocalExemptDict_DRN)
del(LocalExemptDict_DRN)
from VisParameters_DRN import GlobalExemptDict_DRN
GlobalExemptDict.update(GlobalExemptDict_DRN)
del(GlobalExemptDict_DRN)
'''
from utils.utilities import MKDIR
#from VisParameters import BinMissionDict
from utils.utilities import getMFNFromFN
from utils.utilities import flattenList
from utils.utilities import GetDigitElementsOfaList
from utils.utilities import removeStrSuffix
from utils.similarity_utils import SequenceSimilarity
from utils.MP_utils import multicoreJob
from utils.MP_utils import MPlogger
from utils.df_utils import dfOutputer
from ClassesTree.ClassesTree_utils import LoadTree
from ClassesTree.ClassesTree_utils import GetSubTopics
from ClassesTree.ClassesTree_utils import GetNodes
from utils.DB_utils import sqlite3Query
import difflib
#print("finish loading difflib")
'''
try:
    from cdifflib import CSequenceMatcher
    difflib.SequenceMatcher = CSequenceMatcher
except:
    pass
'''

try:
    import dash_pivottable
except Exception as e:
    MES = f"When loading the module dash_pivottable, the following error occurs:\n{e}"
    MPlogger().logW(MES, logFile="ModuleNotFoundError.log")
#print("finish loading dash_pivottable")


def getLabelFromVisCellVal(CellStr):
    #print("CellStr",CellStr)
    #print("type(CellStr)",type(CellStr))
    try:
        #LabelsList = re.match('^#T#.*#T#',CellStr)
        LabelsList = re.search('^#T#.*#T#',CellStr)
    except:
        LabelsList = None
    if LabelsList is not None:
        return LabelsList[0].strip("#T#")
    else:
        return ""

def GetInfoScoreStastic(segTuples,InfoScoreTable,
                        nScoringSegUPD = 100,
                        LeastNegScore=-20000):
    '''
    輸入segTuples=[(0,'South Sea','Hello'),(1,'Informative','World')]
    將Tags依InfoScoreTable查分後，輸出分數加總。
    '''
    segTuples = segTuples[:nScoringSegUPD]
    #如果總片數多於一片，可容許一片負分垃圾不計。
    #如果只有一片，無不計空間。
    segTags = [x[1] for x in segTuples]
    segScores = [InfoScoreTable[x] if not x.startswith("Exempt-") else 0 for x in segTags]
    #LenST = len(segTuples)
    #計算啓動豁免機制被算零分的片段以外之餘下片數，用此量來算平均。
    nPiece = len([x for x in segTags
                  if not x.startswith("Exempt-")])
    if nPiece == 0:
        nPiece = len(segTags)
    InfoScoreSum = int(sum(segScores))
    InfoScoreMean = int(InfoScoreSum/nPiece)
    #InfoScoreStd = round(np.std(segScores))
    if len(segScores) < 2:
        InfoScoreStd = 0
    else:
        InfoScoreStd = int(stdev(segScores))
    #InfoScoreVariance = round(variance(segScores))
    #InfoScoreVariance = int(variance(segScores))
    #return InfoScoreSum, InfoScoreMean
    return {
        "InfoScoreSum":InfoScoreSum,
        "InfoScoreMean":InfoScoreMean,
        #"InfoScoreVariance":InfoScoreVariance,
        "InfoScoreStd":InfoScoreStd,
        }

    
def GetClassOfMostPieces(segTuples,InfoScoreTable):
    c = Counter([stu[1] for stu in segTuples])
    try:
        MostPieces = [x for x in c.keys() if 
                      all([c[x] == max(c.values()),
                           x in InfoScoreTable.keys()])
                      ]
        MostPieces.sort(key=lambda x:InfoScoreTable[x])
        MostPiece = MostPieces[-1]
        TextWithMostPiece = ""
        for stu in segTuples:
            if stu[1] == MostPiece:
                TextWithMostPiece = stu[2]
                break
        return MostPiece,TextWithMostPiece
    except Exception as e:
        print(f"When apply GetClassOfMostPieces to {segTuples}, the following error occurs:\n{e}")
        #MostPiece = ""
        return "",""


def GetClassOfHighestScore(segTuples,InfoScoreTable):
    try:
        #LabelsWithScore = [(x[1], InfoScoreTable[x[1]]) for x in segTuples]
        #LabelsWithScore.sort(key=lambda x:x[1])
        #MaxScore = LabelsWithScore[-1][0]
        segTuplesWithScore = [(x[1],InfoScoreTable[x[1]],x[2]) for x in segTuples if x[1] in InfoScoreTable.keys()]
        segTuplesWithScore.sort(key=lambda x:x[1])
        MaxScore = segTuplesWithScore[-1][0]
        MostPiece,TextWithMostPiece = GetClassOfMostPieces(segTuples,InfoScoreTable)
        #如果最多片的分數也是最高分，則取最多片當做最高分代表，否則隨機取最高分群組中的一個做代表。
        if InfoScoreTable[MostPiece] == MaxScore:
            Highest,TextWithHighestPiece = MostPiece,TextWithMostPiece
        else:
            #Highest,TextWithHighestPiece = LabelsWithScore[-1][0]
            Highest,TextWithHighestPiece = segTuplesWithScore[-1][0],segTuplesWithScore[-1][2]
    except:
        Highest,TextWithHighestPiece = "",""
    return Highest,TextWithHighestPiece

#豁免機制
def ComputeExempt(
        segTuples,InfoScoreTable,
        printOnScreen=True,MPLOGGER=None,
        #SimilarPiecesExemptMethod = None,
        #SimilarPiecesExemptMethod = "jaro_similarity",
        #SimilarPiecesExemptMethod = "difflib",
        SimilarPiecesExemptMethod = SimilarPiecesExemptMethod,
        ):
    '''
    輸入一篇文本的切片集合segTuples清單，每一個切片格式為(切片位置,Tag,文本)
    '''
    if MPLOGGER == None:
        MPLOGGER = MPlogger(logFile="Exempt.log")
    nNegativeExempt = 0
    nNegativeExemptUBD = 1
    nExemptPieces = 0
    LenST = len(segTuples)
    segTags = [x[1] for x in segTuples]
    #nFalun = [x[1] for x in segTuples].count("Falun Gong")
    #global InfoScoreTable
    
    #片段豁免機制，如果片段tuple的輸入Tag符合正規表示式TagRe，
    #並且文本符合正規表示式TextRe，則啓動片段豁免機制將輸出標籖定為OutputTag。
    nTriggerDict = {}
    #將seaTuple排序，以使豁免機制由前面的片段至後面片段的優序執行。
    segTuples = sorted(segTuples,key = lambda x:x[0])
    for i,x in enumerate(segTuples):
        #PartNO = x[0]
        SimpleTag = x[1]
        text = x[2]
        for key in LocalExemptDict.keys():
            LocalExempt = LocalExemptDict[key]
            #如果此文本key值此類的豁免次數已達設定上限，則continue跳過，繼續下一個豁免檢驗。
            if "nTriggerUPD" in LocalExempt["condition"].keys():
                if nTriggerDict.get(key,0) >= LocalExempt["condition"]["nTriggerUPD"]:
                    continue
            TagRe = LocalExempt["condition"]["SimpleTag"]
            TextRe = LocalExempt["condition"]["text"]
            OutputTag = LocalExempt["OutputTag"]
            #檢驗豁免條件
            if re.search(TagRe,SimpleTag) is not None and any([
                re.search(TextRe,text) is not None,
                re.search(TextRe,text.replace(" ","")) is not None]):
                segTuples[i] = (x[0],OutputTag,x[2])
                nTriggerDict[key] = nTriggerDict.get(key,0)+1
                nExemptPieces +=1
                #如果豁免機制SegExempt有指定輸出標籖的分數，則進行設定。
                if "OutputTagScore" in LocalExempt.keys():
                    InfoScoreTable[OutputTag]=LocalExempt["OutputTagScore"]
                #如果觸發後的分數由負變成大於等於0，則將負分豁免片數更新加1。
                if InfoScoreTable[SimpleTag] < 0 and InfoScoreTable[OutputTag] >= 0:
                    nNegativeExempt += 1
                MES = f"for seg {x}, the Exempt \n {LocalExempt} \n is active, out seg is {segTuples[i]}"
                MPLOGGER.logW(MES,logMode = "at",printOnScreen=printOnScreen)
    #全文本豁免機制，如果輸入標籖比例若在閉區間RatioInterval中，則觸發全域豁免。
    for key in GlobalExemptDict.keys():
        GlobalExempt = GlobalExemptDict[key]
        #print("GlobalExempt",GlobalExempt)
        TagRe = GlobalExempt["condition"]["SimpleTag"]
        RatioInterval = GlobalExempt["condition"]["RatioInterval"]
        #計算符合標籖比例
        MatchNSegs = sum([re.search(TagRe,x[1]) is not None for x in segTuples])
        #如果符合標籖比例在閉區間RatioInterval中，則觸發全域豁免。
        if RatioInterval[0] <= MatchNSegs/LenST <= RatioInterval[1]:
            OutputTag = GlobalExempt["OutputTag"]
            MES = f"for input segTuplesp[0:10] {segTuples[0:10]}, the Global Exempt \n {GlobalExempt} \n is active,"
            MPLOGGER.logW(MES,logMode = "at",printOnScreen=printOnScreen)
            
            #segTuples = [x if re.search(TagRe,x[1]) is None 
                         #else (x[0],OutputTag,x[2])for x in segTuples]
            #nExemptPieces += MatchNSegs
            for i,x in enumerate(segTuples):
                if "nTriggerUPD" in GlobalExempt["condition"].keys():
                    if nTriggerDict.get(key,0) >= GlobalExempt["condition"]["nTriggerUPD"]:
                        break
                if re.search(TagRe,x[1]) is not None:
                    segTuples[i] = (x[0],OutputTag,x[2])
                    nTriggerDict[key] = nTriggerDict.get(key,0)+1
                    nExemptPieces +=1
                    MES = f"啓動{key}全域豁免,output segTuples[{i}] are  {segTuples[i]}"
                    MPLOGGER.logW(MES,logMode = "at",printOnScreen=printOnScreen)

            #如果豁免機制GlobalExempt有指定輸出標籖的分數，則進行設定。
            if "OutputTagScore" in GlobalExempt.keys():
                InfoScoreTable[OutputTag]=GlobalExempt["OutputTagScore"]
            #如果觸發後的分數由負變成大於等於0，則將負分豁免片數更新。
            if InfoScoreTable[SimpleTag] < 0 and InfoScoreTable[OutputTag] >= 0:
                nNegativeExempt += MatchNSegs

    '''
    #法輪功豁免機制，如果法輪功片段佔比小於0.3，則啓動法輪功豁免，將法輪功片段視為0零分。
    nFalun = [x[1] for x in segTuples].count("South Sea")
    if nFalun > 0:
        for i,x in enumerate(segTuples):
            SimpleTag = x[1]
            text = x[2]
            #if re.search("^Falun Gong$",text) is not None and any([
            if re.search("^South Sea$",SimpleTag) is not None and any([
                re.search("(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*",text) is not None,
                #re.search("(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*",text.replace(" ","")) is not None]):
                re.search("(?=.*第 5 卷|.*abc)(?=.*12rg4|.*肖 锋|.*3f3).*",text) is not None,
                re.search("(?=.*第 5 卷|.*abc)(?=.*12rg4|.*肖 锋|.*3f3).*",text.replace(" ","")) is not None]):
                segTuples[i] = (x[0],"Exempt-CPC Meeting",x[2])
        if nFalun/LenST < 0.3:   
            segTuples = [x if x[1]!="Falun Gong" 
                         else (x[0],"Exempt-Falun Gong",x[2])for x in segTuples]
            InfoScoreTable["Exempt-Falun Gong"] = 0
    '''
    segScores = [InfoScoreTable[x] if not x.startswith("Exempt-") else 0 for x in segTags]
    #負分豁免機制，如果由分數負轉非負的豁免機制少於nNegativeExemptUBD，則可容許片nNegativeExemptUBD-nNegativeExempt負分垃圾不計。
    if nNegativeExempt < nNegativeExemptUBD:
        #依大小排序後的原來index
        #s=[2,3,1,4,5,3]則placeList為[2,0,1,5,3,4]
        #s第k小的在原來s清單
        placeList = sorted(range(len(segScores)), key=lambda k: segScores[k])
        segPos = placeList[i]
        #將分數最少的負分片段，nNegativeExempt片豁免。
        for i in range(nNegativeExemptUBD-nNegativeExempt):
            #segT = segTuples[segPos]
            segT = list(segTuples[segPos])
            if segT[1].startswith("Exempt-") or segT[1].startswith("Keyword Neg Filter"):
                continue
            if InfoScoreTable[segT[1]] < 0:
                #segTuples[segPos] = (
                    #segT[0],"Exempt-"+segT[1],segT[2])
                segT[1] = "Exempt-" + segT[1]
                segTuples[segPos] = tuple(segT)
                nExemptPieces += 1
                InfoScoreTable["Exempt-"+segT[1]] = 0
                MES = f"啓動普通負分豁免,output segTuple are  {segT}"
                MPLOGGER.logW(MES,logMode = "at",printOnScreen=printOnScreen)
    #如果文章夠長，含有足夠切片數，例如:超過4片，則啓動最末片的短切片扣分誤扣過重豁免機制，
    #為避免錯誤啓動，再加上要求末片不計的均分需超過50。
    if len(segTuples) > 4:
        segT = list(segTuples[-1])
        if not segT[1].startswith("Exempt-"):
            if all([#末片分數小於-100
                    InfoScoreTable.get(segT[1],0) < -100,
                    #末片字數大於30
                    len(segT[2])>30,
                    #末片不計的均分大於40
                    mean([InfoScoreTable.get(x[1],0) for x in segTuples[:-1]])>40
                    ]):
                if not segT[1].startswith("Exempt-"):
                    segT[1] = "Exempt-" + segT[1]
                segTuples[-1] = tuple(segT)
                nExemptPieces += 1
                InfoScoreTable["Exempt-"+segT[1]] = 0
                MES = f"最末片的短切片扣分誤扣過重豁免,output segTuples[-1] are  {segTuples[-1]}"
                MPLOGGER.logW(MES,logMode = "at",printOnScreen=printOnScreen)
    InfoScoreSum = sum([InfoScoreTable.get(x[1],0) for x in segTuples[:-1]])
    #print("segTuples",segTuples)
    #segScores = [InfoScoreTable[x] if not x.startswith("Exempt-") else 0 for x in segTags]
    #if InfoScoreSum >= 500:
    #高相似切片豁免
    #print(f"Applying SimilarityExempt with method {SimilarPiecesExemptMethod}")
    if SimilarPiecesExemptMethod is not None:
        SPEDict = SimilarPiecesExemptSetting[SimilarPiecesExemptMethod]
        InfoScoreSumLBD = SPEDict["InfoScoreSumLBD"]
        ClassScoreUBD = SPEDict["ClassScoreUBD"]
        SegTxtLenUBD = SPEDict["SegTxtLenUBD"]
        #SimilarLBDToExempt = SPEDict["SimilarLBDToExempt"]
        SimilarIntvToExemptList = SPEDict["SimilarIntvToExemptList"]
        if InfoScoreSum >= InfoScoreSumLBD:
            for i,seg_i in enumerate(segTuples):
                FindHighSimilarity = False
                #PartNO = x[0]
                #SimpleTag = x[1]
                #text = x[2]
                segT = list(seg_i)
                seq1=segT[2]
                if not segT[1].startswith("Exempt-"):
                    if all([#類別分數較高者，可能為較特殊類別，該片不進行高相似切片豁免
                            InfoScoreTable.get(segT[1],0) <= ClassScoreUBD,
                            #切片文本長度夠長者，才進行高相似切片豁免
                            len(segT[2]) >= SegTxtLenUBD,
                            ]):
                        
                        #與前面出現過的切片進行序列相似度計算，高度相似的話，則進行豁免，計為0分。
                        for j,y in enumerate(segTuples[:i]):
                            #取消已被豁免區塊再去豁免其他區塊的能力。
                            if segTuples[j][1].startswith("Exempt-"):
                                continue
                            seq2=segTuples[j][2]
                            #print("i,j",i,j)
                            PieceSimilarity = SequenceSimilarity(
                                    seq1=seq1,seq2=seq2,
                                    method =SimilarPiecesExemptMethod,
                                    #將數字以"Ｄ"取代後，再計算相似度。
                                    #digits_assimilation=True,
                                    )
                            #非對稱的情況
                            if SimilarPiecesExemptMethod in ["difflib"]:
                                #if "公 司" in segTuples[j][2] or "公 司" in segT[2]:
                                    #print("="*50)
                                    #print("PieceSimilarity b4",PieceSimilarity)
                                PieceSimilarity = max(
                                    PieceSimilarity,SequenceSimilarity(
                                        seq1=seq2,seq2=seq1,
                                        method =SimilarPiecesExemptMethod,
                                        #將數字以"Ｄ"取代後，再計算相似度。
                                        #digits_assimilation=True,
                                        )
                                    )
                                #if "公 司" in segTuples[j][2] or "公 司" in segT[2]:
                                    #print("PieceSimilarity af",PieceSimilarity)
                            #if  PieceSimilarity >= SimilarLBDToExempt:
                            for [(charTypeLBD,charTypeUBD),
                                 (longerSeqLBD,longerSeqUBD),
                                 (similarityLBD,similarityUBD)] in SimilarIntvToExemptList:
                                if all([charTypeLBD <= max(len(set(seq1)),len(set(seq2))) <=charTypeUBD,
                                        longerSeqLBD <= max(len(seq1.lower()),len(seq2.lower())) <= longerSeqUBD,
                                        similarityLBD <= PieceSimilarity <= similarityUBD,
                                        ]):
                                    if not segT[1].startswith("Exempt-"):
                                        segT[1] = "Exempt-" + segT[1]
                                    segTuples[i] = tuple(segT)
                                    nExemptPieces += 1
                                    InfoScoreTable["Exempt-"+segT[1]] = 0
                                    strToLog1 = seq1.replace('\n','')
                                    strToLog2 = seq2.replace('\n','')
                                    MES = f"for {i},{j}-th Pieces, 啓動高相似度切片豁免 for {strToLog1} and {strToLog2} with similarity {PieceSimilarity},output segTuples[i] are  {segTuples[i]}"
                                    MES += f"\n@condition{((charTypeLBD,charTypeUBD),(longerSeqLBD,longerSeqUBD),(similarityLBD,similarityUBD))}"
                                    MPLOGGER.logW(MES,logMode = "at",printOnScreen=printOnScreen)
                                    FindHighSimilarity = True
                                    break
                            if FindHighSimilarity == True:
                                break
    return segTuples,InfoScoreTable,nExemptPieces



class BinMissionVerifier:
    '''
    BinMissionDict = {
        "CPC Meeting":{
            "InfoScoreSumInterval":[200,99999999],
            "InfoScoreMeanInterval":[-99999999,99999999],
            "Labels":{
                "SimpleTag":"(^CPC Affairs$)|(^CPC Party Development$)|(^CPC Meeting$)",
                "MatchingBlockInterval":[2,99999999],
                "RatioInterval":[0.4,1],
            }
            "KW":{
                "MatchingBlockWithKWInterval":[0,99999999],
                "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
                },
            }
        }
    '''
    def __init__(self, 
                 tpcTree = [],
                 segTuples = [],
                 InfoScoreSum = None,
                 InfoScoreMean = None,
                 BinMissionDict = {}
                 ):
        self.tpcTree = tpcTree
        self.segTuples = segTuples
        self.InfoScoreSum = InfoScoreSum
        self.InfoScoreMean = InfoScoreMean
        self.BinMissionDict = BinMissionDict
    def show(self):
        print("segTuples[:3]", self.segTuples[:3])
        print("BinMissionDict:", self.BinMissionDict)
    def singleConstraintBool(self,segTags,constraint):
        CST = constraint
        LenST = len(segTags)
        #SingleBool = True
        #檢驗分數
        if "InfoScoreSumInterval" in CST.keys():
            ISlbd = CST["InfoScoreSumInterval"][0]
            ISubd = CST["InfoScoreSumInterval"][1]
            if not ISlbd <= self.InfoScoreSum <= ISubd:
                return False
        if "InfoScoreMeanInterval" in CST.keys():
            ISMlbd = CST["InfoScoreMeanInterval"][0]
            ISMubd = CST["InfoScoreMeanInterval"][1]
            if not ISMlbd <= self.InfoScoreMean <= ISMubd:
                return False
        #檢驗符合類別片數
        if "Labels" in CST.keys():
            BMLB = CST["Labels"]
            if "SimpleTag" in BMLB.keys():
                selectedLabels = [x for x in GetNodes(self.tpcTree)
                                  if re.search(BMLB["SimpleTag"],x) is not None]
                                  #if re.search(STpat,x) is not None]
                #自動包含子類別
                #tpcTree = LoadTree(
                    #TreeFile,OnlyLettersDigitsLabels= OnlyLettersDigitsLabels)
                selectedLabels = sorted(set(flattenList(
                                [GetSubTopics([x], self.tpcTree) for x in selectedLabels]
                                )))
                patt = '|'.join(["^{}$".format(x) for x in selectedLabels])
                #如果沒有有效的patt供比對，符合切片數強制定為0，
                #以免因re判全部切片都符合pat，導致無法正確檢驗符合切片數條件。
                if patt == '':
                    nMatchingBlock = 0
                else:
                    nMatchingBlock = sum([re.search(patt,x) is not None for x in segTags])
                if "MatchingBlockInterval" in BMLB.keys():
                    nMatchingLbd =BMLB["MatchingBlockInterval"][0]
                    nMatchingUbd =BMLB["MatchingBlockInterval"][1]
                    if not nMatchingLbd <= nMatchingBlock <= nMatchingUbd:
                        return False
                if "RatioInterval" in BMLB.keys():
                    MatchingRatio = nMatchingBlock/LenST
                    RatioLbd = BMLB["RatioInterval"][0]
                    RatioUbd = BMLB["RatioInterval"][1]
                    if not RatioLbd <= MatchingRatio <= RatioUbd:
                        return False
        #如果沒有任何constraint中的條件被違反，則回傳True。
        return True
    def finalBoolRes(self,segTags,BM):
        #令邏輯式形如(M_1 and M2 and ... and M_m) and 
        #[ 
        #(S_1 or S_2 or ... or S_k) or
        #(T_11 and T_12 and .. and T_1j1) or
        #(T_21 and T_22 and .. and T_2j2) or
        #(T_31 and T_32 and .. and T_3j3) or
        #(T_41 and T_42 and .. and T_4j3) or
        #]
        #M_i收集為Must_Pool，S_i收集為Or_Pool，T_i收集為And_Pool
        #如果沒有任何constraint，Must_Pool預設輸出為True,
        #如果沒有任何constraint，Or_Pool及And_Pool_i預設Pool輸出為False
        #針對Must_Pool，必須所有constraint為True，Must_Pool輸出才為True，
        #如果Must_Pool輸出為False，key的整個result輸出則為False，early return。
        #針對Or_Pool，只要有一個constraint為True，Or_Pool輸出則為True。
        #針對And_Pool_i，必須所有constraint為True，And_Pool_i輸出才為True。
        BoolPool = {
            "Must_Pool":True,
            "Or_Pool":False,
            #"And_Pool":False,
            #"And_Pool2":False,
            #"And_Pool3":False,
            #"And_Pool4":False,
            }
        #MPBool = True
        #OPBool = False
        #APBool = False
        #對單一的constraint而言，裡面有列到的各個小條件都要成立，這個constraint輸出才為True。
        #如果constraint沒有任何小條件，則該constraint輸出為True。
        #如果Or_Pool和And_Pool皆為空，即視為沒有經過任何篩選，當做垃圾。
        if max([len(BM[x]) for x in BM.keys() if (
                x.startswith("Or_Pool") or x.startswith("And_Pool"))
                ]) == 0:
            return False
        for Btype in BM.keys():
            if not any([Btype in ["Must_Pool","Or_Pool"],
                        Btype.startswith("And_Pool")]):
                continue
            if Btype in BM.keys():
                CSTset = BM[Btype]
                for constraint in CSTset.keys():
                    SingleBool = self.singleConstraintBool(
                        segTags,CSTset[constraint])
                    if Btype == "Must_Pool":
                        if SingleBool == False:
                            return False
                    elif Btype == "Or_Pool":
                        if SingleBool == True:
                            return True
                    elif Btype.startswith("And_Pool"):
                        if SingleBool == False:
                            #return False
                            BoolPool[Btype] = False
                            break
                        else:
                            BoolPool[Btype] = True
        #Must_Pool輸出皆True 且 (Or_Pool constraint皆False或空集合)
        #檢測是否存在And_Pool_i，使得其內constraint皆成立，
        #即是否存在And_Pool_i使得BoolPool[And_Pool_i]為True，
        #如果有則early return，總輸出為True
        #如果沒有任何BoolPool[And_Pool_i]為True的情況，
        #則會執行到最後一步，總輸出為False。
        for term in [x for x in BM.keys() if x.startswith("And_Pool")]:
            if BoolPool[term] == True:
                return True
        return False


    def proc(self):
        result = {}
        LenST = len(self.segTuples)
        segTags = [x[1] for x in self.segTuples]
        #print("IN BinMissionVerifier, BinMissionDict", self.BinMissionDict)
        for key in list(self.BinMissionDict.keys()):
            BM = self.BinMissionDict[key]
            #如果沒有任何條件，即未經過任何驗證，定為未驗品垃圾，該key預設總輸出為False
            result[key] = False
            #如果active沒有設定為True，則跳過檢驗流程，該key總輸出維持False。
            if not BM.get("active",False):
                continue
            
            result[key] = self.finalBoolRes(segTags,BM)
        #print("IN BinMissionVerifier, result",result)
        return result

def VisDfToRowTagsList(df):
    DigitCols = GetDigitElementsOfaList(list(df.columns.tolist()))
    for col in DigitCols:
        df[col] = df[col].apply(lambda x:getLabelFromVisCellVal(x))
    #df['File'] = df['File'].apply(getMFNFromFN)
    if 'Src' not in df.columns:
        df['Src'] = df['File']
    df = df[['Src']+DigitCols]
    #print("df",df)
    data = [['Src','pred_Type']]
    
    for i,row in df.iterrows():
        File = row[0]
        for cellValue in row[1:]:
            if len(cellValue) == 0:
                continue
            data.append([File,cellValue])
    return data

def BuildClassesPivotTable(df, id=""):
    if set(df.columns) != {"Src", "pred_Type"}:
        data = VisDfToRowTagsList(df)
    return dash_pivottable.PivotTable(id=id,
        data=data,
        cols=["pred_Type"],
        rows=["Src"],
        vals=["Count"]
    )


def EvaluatePreference(rowDict={},BMVResult={}):
    if any([BMVResult[key] == True and key not in ["Test","FocT"] for key in BMVResult.keys()]):
        return 1
    else:
        return 0


class TwinsClassifier:
    '''
    輸入PreambleCols及Rowslist，計算類同文群。如：
    PreambleCols = ["Rating","InfoScoreSum","InfoScoreMean",
    "NumberOfMatchingBlock","NumberOfMatchingBlockWithKW",
    "Class Of Most Pieces","Class Of Highest Score",\
    "Number of Exempt Pieces","Date","Selected","Target","Twins",
    "File",#"CPC Meeting",]
    rowslist [['', 810, 202, '', '', '#T#Indo-Pacific Framework#T#',
    '#T#AUKUS#T#', 0, '20220401', '', '', '', 
    '美国欢迎日澳军事协议 表明并非剑指中国.txt', '', '', '', ''], 
    ['', 630, 210, '', '', '#T#AUKUS#T#', '#T#AUKUS#T#', 0, 
    '20220401', '', '', '', '专家：美英澳直击中共军事弱点.txt', 
    '', '', '', '']]
    '''
    '''
    輸入目標檔名及比對目標檔名pool，計算最高相似度值。如：
    '''
    def __init__(self,
                 targetFile,
                 filePool,
                 sql3File,
                 sqlCols,
                 segTagsUPD = 100,
                 segTagsLBD = 5,
                 #segTextUPD = 5,
                 TextUPD = 512,
                 PoolRandomOrder = False,
                 SimilarityMethod = "difflib",
                 TwinsAfterSort = False,
                 ReturnedFileUPD = math.inf,
                 MPLOGGER = None
                 ):
        self.targetFile = targetFile
        self.filePool = filePool
        self.sql3File = sql3File
        self.sqlCols = sqlCols
        #用切片類別計算相似度時，由第一片開始，採用的片數。
        self.segTagsUPD = segTagsUPD
        #用切片類別計算相似度時，至少需有的片數，否則因片數太少，較不具比對意義，不採用切片類別比對。
        self.segTagsLBD = segTagsLBD
        #用文字計算相似度時，由第一片開始，採用的片數。
        #self.segTextUPD = segTextUPD
        self.TextUPD = TextUPD
        #比對前是否將filePool先隨機改變排序。
        self.PoolRandomOrder = PoolRandomOrder
        #相似度計算方法
        self.SimilarityMethod = SimilarityMethod
        #在計算片段序列相似度前，是否先進行排序。
        self.TwinsAfterSort = TwinsAfterSort
        self.ReturnedFileUPD = ReturnedFileUPD
        if MPLOGGER == None:
            self.MPLOGGER = MPlogger()
        else:
            self.MPLOGGER = MPLOGGER
    def show(self):
        print("TwinsClassifier Params:")
        print("targetFile", self.targetFile)
        print("filePool[:3]", self.filePool[:3])
        return ""
    def getTagsAndText(self,file):
        colList=','.join(self.sqlCols)
        query = f'SELECT {colList} FROM sampleSrc \
            WHERE File = "{file}" AND \
                (PartNO BETWEEN {0} AND {self.segTagsUPD-1})\
                ORDER BY PartNO;'
        segTuples = []
        try:
            segTuples = list(sqlite3Query(self.sql3File,  query = query))
        except Exception as e:
            MES = f"When Apply the query {query} to build segTuples with {self.sql3File}, "
            MES += f"the following error occurs: \n {e}"
            self.MPLOGGER.logW(MES)
        if segTuples == []:
            return [],""
        #把PartNo轉成int
        if 'PartNO' in self.sqlCols:
            #idx = cols.index('PartNO')
            segTuples = [(int(float(x[0])),x[1],x[2]) for x in segTuples]
            segTuples = sorted(segTuples,key = lambda x:x[0])
        
        
        #raise Exception

                        
        #stu樣本：(0, 'AUKUS', '法媒看澳洲毁约潜舰军购 叹欧洲势衰2021/9/'）
        maxPN = max([stu[0] for stu in segTuples])
        fileTags = ['' for i in range(maxPN+1)]
        for stu in segTuples:
            fileTags[stu[0]] = stu[1]
        #print("len(fileTags),fileTags",len(fileTags),fileTags)
        #將前5片文字串接，以供後面計算短文的相似度使用。
        #fileText = ''.join(
            #[x[2] for x in segTuples[:self.segTextUPD]])
        fileText = ''
        while(len(fileText)<self.TextUPD and len(segTuples)>0):
            fileText += segTuples.pop(0)[2]
        fileText = fileText[:self.TextUPD]
        #print("fileText",fileText)
        return fileTags,fileText
    def proc(self):
        if self.PoolRandomOrder == True:
            random.shuffle(self.filePool)
        segTagsDict = {}
        segTextDict = {}
        RetFileList = []
        if len(list(filter(lambda x: x != self.targetFile, self.filePool))) == 0:
            return [[self.targetFile,"",0]]
        '''
        for file in self.filePool+[self.targetFile]:
            segTagsDict[file] = ['' for i in range(self.segTagsUPD)]
            colList=','.join(self.sqlCols)
            query = f'SELECT {colList} FROM sampleSrc \
                WHERE File = "{file}" AND \
                    (PartNO BETWEEN {0} AND {self.segTagsUPD-1})\
                    ORDER BY PartNO;'
            segTuples = []
            try:
                segTuples = list(sqlite3Query(self.sql3File,  query = query))
            except Exception as e:
                MES = f"When Apply the query {query} to build segTuples with {self.sql3File}, "
                MES += f"the following error occurs: \n {e}"
                self.MPLOGGER.logW(MES)
            #把PartNo轉成int
            if 'PartNO' in self.sqlCols:
                #idx = cols.index('PartNO')
                segTuples = [(int(float(x[0])),x[1],x[2]) for x in segTuples]
                segTuples = sorted(segTuples,key = lambda x:x[0])
            
            #raise Exception
            #將前5片文字串接，以供後面計算短文的相似度使用。
            segTextDict[file] = ''.join(
                [x[2] for x in segTuples[:self.segTextUPD]])
                            
            #stu樣本：(0, 'AUKUS', '法媒看澳洲毁约潜舰军购 叹欧洲势衰2021/9/'）
            for stu in segTuples:
                segTagsDict[file][stu[0]] = stu[1]
    
            #清除片段清單後面的空類別。
            while(segTagsDict[file][-1] ==''):
                segTagsDict[file].pop()
        '''
        #print("segTagsDict",segTagsDict)
        #Len = len(df['File'])
        #SimilarityDict = [[0 for j in range(Len)] for i in range(Len)]
        #SimilarityDict = {}
        #edges = []
        #print("df['File']",df['File'])
        #LenTG = len(segTagsDict[self.targetFile])
        

        
        TGfileTags,TGfileText = self.getTagsAndText(self.targetFile)
        
        #SeqMat = difflib.SequenceMatcher()
        #SeqMat.set_seq2(TGfileTags)
        
        for j,file in enumerate(self.filePool):
            #if "马吟风" in file and "马吟风" in self.targetFile:
                #print("self.targetFile,file",self.targetFile,file)
                #raise Exception
            #如果片段數有3片以上，則用切片類別算相似度，否則用文字算相似度。
            if file == self.targetFile:
                continue
            fileTags,fileText = self.getTagsAndText(file)
            TypeSim = TextSim = 0
            MinTagLen = min(len(fileTags),len(TGfileTags))
            #SeqMat.set_seq1(fileTags)
            #TypeSim = SeqMat.ratio()
            TypeSim = SequenceSimilarity(
                fileTags[:2*MinTagLen],TGfileTags[:2*MinTagLen],
                method = self.SimilarityMethod,
                sort_first = self.TwinsAfterSort)
            #print(TypeSim == SequenceSimilarity(fileTags,TGfileTags,method = self.SimilarityMethod))
            '''
            if not TypeSim == SequenceSimilarity(fileTags,TGfileTags,method = self.SimilarityMethod):
                print("="*50)
                print("file,self.targetFile,TypeSim",file,self.targetFile,TypeSim)
                print("SeqMat.ratio()",SeqMat.ratio())
                print("SequenceSimilarity(fileTags,TGfileTags,method = self.SimilarityMethod)",SequenceSimilarity(fileTags,TGfileTags,method = "difflib"))
                print("fileTags",fileTags)
                print("TGfileTags",TGfileTags)
                raise Exception
            '''
            #if LenSTD >=self.segTagsLBD:
            #if LenSTD >=self.segTagsLBD and TypeSim > 0.7:
            
            
            if  MinTagLen >=self.segTagsLBD \
                and TypeSim > max(0.83-MinTagLen/50,0.7):
                #sim1 = TypeSimTemp if TypeSimTemp > 0.7 else 0
                #sim1 = TypeSimTemp
                #if TypeSim > 0.7:
                    MES = f"{self.targetFile},{file},{TypeSim},{TextSim})"
                    self.MPLOGGER.logW(MES, logFile="similarity_Match.log",
                                  printOnScreen=False)

                    #return self.targetFile,file,TypeSim
                    RetFileList.append([self.targetFile,file,TypeSim])
                    if len(RetFileList) >= self.ReturnedFileUPD:
                        break
                    continue
            #如果短文的類別片數不夠，片段類別較不具代表性，若類別差別比例並非過低，
            #進一步比對文字，如果類別實在差太多，則不比對文字。
            #if TypeSim>0.1:
            #if TypeSim>min(1.6/max(len(fileTags),len(TGfileTags)),0.3):
            if TypeSim>0.3:
                #simBase = segTextDict[self.targetFile]
                #simCmp = segTextDict[file]    
                TextSim = SequenceSimilarity(
                    TGfileText,fileText,method = self.SimilarityMethod)
                #sim2 = simtemp if simtemp > 0.6 else 0
                #sim2 = simtemp
                if TextSim > 0.4:
                    MES = f"{self.targetFile},{file},{TypeSim},{TextSim})"
                    self.MPLOGGER.logW(MES, logFile="similarity_Match_TextSim_Passed.log",
                                  printOnScreen=False)
                    #return self.targetFile,file,TextSim
                    RetFileList.append([self.targetFile,file,TextSim])
                    if len(RetFileList) >= self.ReturnedFileUPD:
                        break
                else:
                    MES = f"{self.targetFile},{file},{TypeSim},{TextSim})"
                    self.MPLOGGER.logW(MES, logFile="similarity_Match_TextSim_Failed.log",
                                  printOnScreen=False)
                MES = f"{self.targetFile},{file},{TypeSim},{TextSim})"
                self.MPLOGGER.logW(MES, logFile="similarity.log",
                              printOnScreen=False)
                #SimilarityDict[self.filePool[j]] = max(TypeSim,TextSim)
            #if "马吟风" in file or "马吟风" in self.targetFile:
                        #print(MES)
        #return self.targetFile,"",0
        return RetFileList
        '''
            #提速模型，只要碰到相似度大於0.5的，就early return，剩下的不比了，故該回傳未必是最像的。
            if max(sim1,sim2) > 0.5:
                MES = f"{self.targetFile},{file},{sim1},{sim2})"
                self.MPLOGGER.logW(MES, logFile="similarity_Match.log")
                return self.targetFile,file,max(sim1,sim2)
        #print("SimilarityDict",SimilarityDict)
        #if len(SimilarityDict) == 0:
            #return self.targetFile,"",0
        similarFile,ms = sorted([
            (k,v) for k,v in SimilarityDict.items()],
            key = lambda x:x[1])[-1]
        if ms >0.5:
            return self.targetFile,similarFile,ms
        else:
            return self.targetFile,"",0
        '''

def UpdateRow(row):
    #UUID_re = "[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}"
    UUID_re = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    #if re.search(UUID_re+"_20\d{2}-\d{2}-\d{2}T",row["File"]) is not None and (row["Date"] is "" or row["Date"] is np.nan):
    if re.search(UUID_re+"_20\d{2}-\d{2}-\d{2}T",row["File"]) is not None:
        newFile, newDate = row["File"].split("_")[:2]
        newDate = removeStrSuffix(newDate,".txt")
        row["File"],row["Date"] = newFile,newDate
    return row

def UpdateFileDateFromFileField(df):
    df = df.apply(UpdateRow, axis=1)
    return df

def ExportDFAllToDatabase(
        df,
        ExportDatabasePath = "",
        ExecutionTime = "0"*14,
        nProcess=1,
        ):
    OUTPUTMAIN = os.path.join(
        ExportDatabasePath,ExecutionTime[:4],
        f"{ExecutionTime[4:6]}-{ExecutionTime[6:8]}",
        ExecutionTime[8:14],"DFPreambleCols_df_ALL")
    MKDIR(os.path.dirname(OUTPUTMAIN))
    #處理WeiTech導入帶時間之File欄位格式，抽出時間放入Data欄位，
    #並清整存至ExportDatabasePath之File欄位
    #dfForExport = df
    #FMT = "%Y-%m-%dT%H:%M:%S"
    FMT = "%Y-%m-%dT"
    #nProcess = 1
    if len(df) > 0:
        #if re.search(f"_{FMT}",df.iloc[0]['File']) is not None:
            #dfForExport = df.copy()
        #df = multicoreJob(nProcess=nProcess).parallelize_dataframe(df, UpdateFileDateFromFileField)
        df = multicoreJob(nProcess=nProcess).parallelize_dataframe(df, rowfunc=UpdateRow)

    dfOutputer(
        df,OMFN=OUTPUTMAIN,OutputFormat=["sql"],
        if_exists='append',IndexCols = ["File"],
        #index_label = ["File"]
        ).run()
    return df
    