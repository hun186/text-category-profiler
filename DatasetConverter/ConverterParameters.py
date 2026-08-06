from PackageImport import PackageImporter
PackageImporter.proc()

#A = 'From: a23@cc.com(jusec), b2@cc.com(jomde), c四@dd.ne, e@ldfd.com cc:dmoed@twma.org Subjcet: eg3fd3m3k3lsag;agadi3jifj 一二二三 From: a@cc.com(jusec), b@cc.com(好棒棒), c@dd.ne, e@ldfd.com Subject: f3om 3o3mdlo3,gFroma23@cc.com(jusec), b2@cc.com(jomde), c四@dd.ne, e@ldfd.com cc:dmoed@twma.org Subjcet:今天@台北,play 3.gorfor a long time From:hello@get.org Subject:YOYOYOY Good Game'
#re.findall("(?:\w{,20}@\w{1,20}?\.[^@]{2,12}){0,}(?:\w{,20}@\w{1,20}?\.[^@]{2,3})",A)
#"((?:(\w{,20}\.){0,}\w{,20}@\w{1,20}?\.[^@]{2,30}){0,}(?:(\w{,20}\.){0,}\w{,20}@\w{1,20}?\.[^@]{2,3}))|((.{1}件人|抄送)(?:.{1,30}(com|;)){1,})|(From(?:.{1,30};){1,})"
import platform
#import tensorflow as tf
import math
import GPUtil
from utils.concurrency.MP_utils import multicoreJob

GPUDevices = GPUtil.getAvailable()
WIDTH = 48 #for short sentence detection
WIDTH = 256
#目標標籤必須已經有加到TopicTree.csv後，才會發生作用，否則在程式中會直接自RBDict排除該item。
#RBDict會在DataCleanerRePatternDict作用後才套用。
RBDict = {
    ("\w*?@.*?\.\w{2,3}",(max(WIDTH/40,6),math.inf)):"Email Header-Email Address",
    ("\w*?@huawei.com",(max(WIDTH/40,6),math.inf)):"Huawei Email Address",
    #"\w*?h":"RBT",
    #"\w*?Economic":"RBT2",
    ("^\w{0,5}.{0,3}\w{12,26}\.cloudfront\.net/{0,1}$",(1,math.inf)):"CDN Web Link-CloudFront",
    }

DataCleanerRePatternDict = {
    "EmailAddress Remover":
        {"SrcPat":["(?:(\w{,20}\.){0,}\w{,20}@\w{1,20}?\.[^@]{2,20}){0,}(?:(\w{,20}\.){0,}\w{,20}@\w{1,20}?\.[^@]{2,3})",
                   "(.{1}件人|抄送)(?:.{1,20}(com|;)){1,}",
                   "From(?:.{1,30};){1,}"
                   ],
         "ReplacedResult":"",
         "ExemptInLabelList":[
             "Email Header-Email Address","Email Header"]
         },
    "&nbsp Remover":
        {"SrcPat":["&nbsp;",
                   "&nbsp"
                   ],
         "ReplacedResult":" ",
         }
    }
TopicTextCrawlerROOT = "../TopicTextCrawler/"

StasticSwitch = False
#設定Bert分類器訓練程式路徑，以進行資料集相關檔案輸出至該路徑，如果不存在，則暫時設為dataset子目錄存放。
BertClassfierPath = '../BertScript'


ConvertToSpec = None
#ConvertToSpec = 'tw2s'
ConvertToSpec = 'tw2sp'


TreeBinaryTarget = 'PRC-OffDoc'
TreeBinaryTarget = 'PRC Document'
TreeBinaryTarget = 'Scrap'
TreeBinaryTarget = None
UniqueLabel = True
nProcess = multicoreJob().ComputeNProcess(log=False)
nProcessSPC = multicoreJob().ComputeSPCNProcess(log=False)
UniqueSortedLabels = True #讀取Label清單字串時，是否進行Label Unique

RSTRLabelMode = True
RSTRLabelMode = False

#設定是否轉換標籤，只留大小寫字母及數字
OnlyLettersDigitsLabels = False

DatasetRatioDict = {
    "Train": 0.7,
    "Validation": 0.2,
    "Test": 0.1,
    }

#WIDTH = 256
#sampleLenLBD = 1
sampleMethod = {
    "nBound":{
        "default": 5000, 
        "Economist":1000,
        #"Scrap":4000 #可用於限制FixtedTest及WTF的輸入片數。
        "Scrap":256*200//WIDTH #可用於限制FixtedTest及WTF的輸入片數。
        },
    "RandomSample":True,
    "LenLBD":1}
#nBound = {
#        "default": 5000, 
#        "Economist":1000, 
#        }
        
#FixedTestFileBound = 6000
#InforScoreSumLowerBound = -999999999

#DataAugmentationGoal = 200
DataAugmentationGoal = 3
RemoveDumpSamples = True
RemoveDumpArticle_FT = False
#if RemoveDumpArticle_FT == False:
    #RemoveDumpSamples = False


DCkwargs = {
    #"FixedTestFileBound":args.FixedTestFileBound,
    "WIDTH" : WIDTH, #樣本切割長度
    "Mode" : "FullCut", #全文切割模式:"FullCut"
    "tokenizationWrap" : True, #依Token結果切割
    "ConvertToSpec" : ConvertToSpec,
    #"LabelList" : LabelList,
    "sampleMethod" : sampleMethod,
    #"nBound" : nBound,
    #"sampleLenLBD" : sampleLenLBD,#取樣長度下限
    "TreeBinaryTarget" : TreeBinaryTarget,
    "UniqueLabel" : UniqueLabel,
    #"nProcess" : nProcess,
    #"InfoScoreTable":InfoScoreTable,
    "UniqueSortedLabels":UniqueSortedLabels, #讀取Label清單字串時，是否進行Label Unique
    "OnlyLettersDigitsLabels":OnlyLettersDigitsLabels, #讀取Label清單字串時，是否去除非字母或數字字符
    #"tpcTree":tpcTree, #類別樹
    #"RSTRLabelList":RSTRLabelList,
    "RBDict":RBDict, #Rule-Based字典，key為正規表示式，vallue為類別。
    "RBActive":True, #Rule-Based標籤轉換，暫定為active
    "DataCleanerRePatternDict":DataCleanerRePatternDict, #輸入txt後的資料清理字典
    }