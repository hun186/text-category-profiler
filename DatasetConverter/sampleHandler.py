from PackageImport import PackageImporter
PackageImporter.proc()
import os
if os.getcwd().split(os.path.sep)[-1] in [
        "DatasetConverter","BertScript","GenerativeLanguageModel","ArticleClustering"]:
    os.chdir("../")
    print(f"Change working directory to {os.getcwd()}")
import sqlite3 as lite
from collections import Counter
from utils.utilities import RemoveIlleagalCharForFileName
#from MP_utils  import MPlogger
#import tokenization
from opencc import OpenCC
from utils.utilities import ListCap
from utils.utilities import wrap
from utils.utilities import GetRatioOfDigits
from utils.utilities import getFNExtFromFullPath
from utils.utilities import fileNameNormalizer
from utils.df_utils import dfFromSQLite3
from utils.MP_utils  import MPlogger
#from utils.TCF_utils import datasetDirOutputDirPickers
from utils.TCF_utils import ClassfierOptionParser
from utils.TextProcessor_utils import textReader
from utils.TextProcessor_utils import BasicDataCleaner
from utils.TextProcessor_utils import DataCleanerWithPattern
from ClassesTree.Label_utils import getLabelsFromFileName
#from ClassesTree.Label_utils import LabelsStringReader

#from tokenization import FullTokenizer
import re
import datetime as dte
import random

from elasticsearch import Elasticsearch

from transformers import AutoTokenizer

#def wrap(s, w):
    #return [s[i:i + w] for i in range(0, len(s), w)]

'''
def tokenization_wrap(s, w):
    tokenizer = tokenization.FullTokenizer(
        vocab_file='vocab.txt', do_lower_case=False)
    tokens = tokenizer.tokenize(s)
    print("tokens:", tokens)
    raise Exception
'''

def tokenization_wrap(
        context, modelDir="", nTokensToWrap=256,
        word_analysis = False,ReTks = False,
        EarlyReturnForShortMessage = True,
        debug = False):
    #print("in tokenization_wrap, nTokensToWrap is",nTokensToWrap)
    #print("input modelDir for tokenization_wrap b4",modelDir)
    modelDir = fileNameNormalizer.proc(modelDir or "xlm-roberta-base")
    #print("input modelDir for tokenization_wrap af",modelDir)
    
    if debug == True:
        ReTks = True
    #EarlyReturnForShortMessage = False
    #print(context,len(context),nTokensToWrap)
    #如果開啓短文EarlyReturn，碰到太短的文本就直接回傳整串為一個單串。
    if all([EarlyReturnForShortMessage == True,
            len(context)+2<= nTokensToWrap,
            ]):
        if debug == True:
            print("len of context is not larger than nTokensToWrap, direct return [context] as the result of wrapping.")
        res = {
            "ctxCut":[context],
            "ReTks":[],
            }
        return res
    if not os.path.isdir(modelDir):
        print("WARNING! The input modelDir {modelDir} for tokenization_wrap does not exist, use xlm-roberta-base instead")
        modelDir = "xlm-roberta-base"
    
    #context = "This is a book.這是一本書。那是一枝筆"
    #nTokensToWrap = 6
    nTokensToWrap -= 3 #預留<s>、</s>及開頭補空白的位置
    #debug = True
    #context = "Все счастливые семьи похожи друг на друга, каждая несчастливая семья несчастлива по-своему. Все смешалось в доме Облонских. Жена узнала, что муж был в связи с бывшею в их доме француженкою-гувернанткой, и объявила мужу, что не мо- жет жить с ним в одном доме. Положение это продолжалось уже третий день и мучительно чувствовалось и самими супругами, и всеми членами семьи, и домочадцами. Все члены семьи и домочадцы чувствовали, что нет смысла в их сожительстве и что на каждом постоялом дворе случайно сошедшиеся люди более связаны между собой, чем они, члены семьи и домочадцы Облонских. "
    for subdir in [x[0] for x in os.walk(modelDir)]:
        if "config.json" in os.listdir(subdir):
            #model_checkpoint = subdir
            modelDir = subdir
            break
    #print("modelDir for tokenization",modelDir)
    tokenizer = AutoTokenizer.from_pretrained(
        modelDir,trust_remote_code=True)
    encoded = tokenizer(context)
    ecTks = encoded.tokens()
    if debug == True:
        print(context)
        print("encoded['input_ids']:",encoded['input_ids'])
        print(len(encoded['input_ids']))
        print("encoded.tokens():",ecTks)
        print(len(ecTks))
        print("encoded.word_ids():",encoded.word_ids())
        print(len(encoded.word_ids()))
    WrapPosList = []
    tksPos = list(range(1,len(ecTks)-1))
    indicator = [tksPos[i:i + nTokensToWrap] for i in range(0, len(tksPos), nTokensToWrap)]
    if debug == True:
        print("token分組位置清單:",indicator)
    WrapPosList = [[encoded.token_to_chars(csIntv[0]).start,
                    encoded.token_to_chars(csIntv[-1]).end] for csIntv in indicator]
    for i in range(len(WrapPosList)-1):
        if WrapPosList[i][1] == WrapPosList[i+1][0]:
            WrapPosList[i][1] -= 1
    if debug == True:
        print("WrapPosList af",WrapPosList)
    
    ctxCut = [context[st:ed+1] for st,ed in WrapPosList]
    if ReTks == True:
        ReTks = [tokenizer(x).tokens() for x in ctxCut]
    else:
        ReTks = []
    if debug == True:
        print("ctxCut",ctxCut)
        print("針對產出再次tokenized的結果:",ReTks)
        print([len(x) for x in ReTks])
    
    if word_analysis == True:
        corpora_records = context.split(' ')
        word_2_char_mapping = dict()
        char_cursor = 0
        for ind in range(len(corpora_records)):
            if(len(corpora_records[ind])>0): #the last space will not be considered
                start = char_cursor
                end = char_cursor+len(corpora_records[ind])
                word_2_char_mapping[ind] = [start,end]
                char_cursor = char_cursor+len(corpora_records[ind])+1 #consider the white
        if debug == True:
            print("word_2_char_mapping:",word_2_char_mapping)
        
        word_2_token_mapping = dict()
        for token_index in range(len(encoded.tokens())):
            this_token = encoded.word_ids()[token_index]
            if (not this_token==None):
                char_span=encoded.token_to_chars(token_index)
                if debug == True:
                    print("token_index,char_span",token_index,char_span)
                for each_word in word_2_char_mapping:
                    start = word_2_char_mapping[each_word][0]
                    end = word_2_char_mapping[each_word][1]
                    if (char_span.start)>=start and char_span.end<=end:
                        #print(batch_encoding.tokens()[token_index]) #check the
                        #print('--->')
                        #print(corpora_records[each_word])
                        if (each_word in word_2_token_mapping):
                            word_2_token_mapping[each_word].append(token_index)
                        else:
                            word_2_token_mapping[each_word]=[token_index]
        if debug == True:
            print("word_2_token_mapping:",word_2_token_mapping)
    res = dict()
    res["ctxCut"] = ctxCut
    res["ReTks"] = ReTks
    return res


class RedundantBlankSpaceRemover():
    '''
    處理" 示 範 字 串"這種單字接空白的中文字串，移除空格
    '''
    def __init__(self,
                 text = "", #文本內容
                 width = 256, #切片長度
                 ):
        self.text = text
        self.width = width
    def proc(self,):
        #每一個片段各自處理，以因應多語種混合文本
        TextList = wrap(self.text, self.width)
        TextList = [seg.replace(" ","").replace("　","")
                    if len(set(seg))>80 and (seg.count(" ")+seg.count("　"))/len(seg)>0.4 else seg
                    for seg in TextList]
        self.text = ''.join(TextList)
        return self.text
    
class TextDivider():
    '''
    依設定決定，要將整份文檔長文是否全部依token量或者字元長等長切割後，全部回傳。
    或者僅回傳第一個區塊。
    '''
    def __init__(self,
                 file = "", #文檔檔名
                 text = "", #文本內容
                 Mode = "FullCut",
                 tokenizationWrap = True,
                 modelDir = "", #tokenizer的所在模型目錄
                 ReTks = False, #將依token切割完成之各文本切片重新tokenized，驗證結果。
                 width = 256, #切片長度，單位可為token數或字元數。
                 ):
        self.file = file
        self.text = text
        self.Mode = Mode
        self.tokenizationWrap = tokenizationWrap
        self.modelDir = modelDir
        self.ReTks = ReTks
        self.width = width
    def proc(self, file = ""): 
        self.text = RedundantBlankSpaceRemover(text=self.text).proc()#處理" 示 範 字 串"這種單字接空白的中文字串，移除空格，以免造成相似度被高估，
        #導致錯誤豁免。
        if self.Mode == "FullCut":
            #全文切割為多個樣本。
            ExpandWidthForFixedTest = True
            #如果ExpandWidthForFixedTest為False，
            #則針對FixedTest的文本直接以self.width當切割長度，
            #如果非FixedTest的文本，則進行語種判斷，視語種決定是否加大切割長度。
            #如果空白比例高，應該是英文，tokenize後會有不少wordpiece，
            #token數量僅約字元數的1/3左右，故可將width加大，以提高token量至max length。
            if all(["FixedTest" in os.path.dirname(self.file),
                    not ExpandWidthForFixedTest]
                   ):
                textList = wrap(self.text, self.width)
            else:
                if self.tokenizationWrap == True:
                    #print("Using tokenizationWrap in sampleHandler")
                    textList = tokenization_wrap(
                        context=self.text, modelDir=self.modelDir, 
                        nTokensToWrap=self.width,
                        ReTks=self.ReTks,
                        #debug=True,
                        )
                    #print(textList)
                    textList = textList["ctxCut"]
                    #print("textList",textList)
                    #print("textList len",[len(x) for x in textList])
                    #time.sleep(10)
                else:
                    text_no_digits = ''.join([i for i in self.text if not i.isdigit()])
                    #text_no_digits = ''.join(filter(lambda x: x.isalpha(), text))
                    #去除連續空白
                    '''
                    for x in ["\n"," ","\n "," \n"]:
                        text_no_digits = re.sub(
                            "({}){{2,}}".format(x), x, text_no_digits)
                    '''
                    text_no_digits = BasicDataCleaner(
                        strQ2B = False,DummySpace = True).proc(text_no_digits)
                    #if text.count(" ")/(len(text)+10**-100) > 0.13:
                    #if text_no_digits.count(" ")/(len(text_no_digits)+10**-100) > 0.13:
                    #被空格隔開的字符要大於1個，才計數，以避免" 示 範 字 串"這種單字接空白的中文字串被誤判為英文。
                    if len(re.findall('\w{2,} ',text_no_digits))/(len(text_no_digits)+10**-100) > 0.11:
                        textList = wrap(self.text, 3*self.width)
                    else:
                        textList = wrap(self.text, self.width)
        else:
            #每一份txt只取前width個字元，生成一個樣本。
            textList = [self.text[:self.width]]

        return textList
    
class SampleReader():
    '''
    針對輸入檔名，讀取文本，輸入標籤及樣本。
    '''
    def __init__(self, file = "", 
                 #LoadedCZJCorpusText = "",
                 #Target = "",
                 Selected = "",
                 LabelList = [], 
                 width = 1024,
                 Mode = "FullCut",
                 tokenizationWrap=False,
                 modelDir="",
                 ConvertToSpec = None,
                 #nBound = {"default":5000}, 
                 #sampleMethod["LenLBD"]為取樣的長度下限，如果切出的樣本字數少於sampleMethod["LenLBD"]則捨棄
                 sampleMethod = {
                     "nBound":{
                        "default": 5000, 
                        "Economist":1000, 
                        },
                     "RandomSample":True,
                     "LenLBD":128},
                 LabelConvertDict = {}, RBDict={},
                 #TreeBinaryMode = False,
                 TreeBinaryTarget = None,
                 UniqueLabel = True,
                 #SQLFile = "",
                 CZJCorpusSQLFile = "",
                 esJob = dict(),
                 esRetMeta = dict(),
                 ESsubject = None,
                 InfoScoreTable = {},
                 UniqueSortedLabels = True,
                 OnlyLettersDigitsLabels = False,
                 RBActive = True,
                 DataCleanerRePatternDict = dict(),
                 MPLOGGER = None
                 ):
        self.file = file
        #self.LoadedCZJCorpusText = LoadedCZJCorpusText
        self.Src = self.file
        #self.Target = Target
        self.Selected = Selected
        self.LabelList = LabelList
        self.width = width
        self.Mode = Mode
        self.tokenizationWrap = tokenizationWrap
        self.modelDir = modelDir
        self.ConvertToSpec = ConvertToSpec
        self.sampleMethod = sampleMethod
        self.LabelConvertDict = LabelConvertDict
        #僅針對預輸入LabelList允許的標籤進行代換。
        self.RBDict = {k:v for k,v in RBDict.items() 
                       if v in self.LabelList}
        #self.TreeBinaryMode = TreeBinaryMode,
        #self.TreeBinaryTarget = TreeBinaryTarget,
        self.UniqueLabel = UniqueLabel
        #self.SQLFile = SQLFile
        self.CZJCorpusSQLFile = CZJCorpusSQLFile
        self.esJob = esJob
        self.esRetMeta = esRetMeta #儲存由ES資料庫取得的日期、目標等資訊
        self.ESsubject = ESsubject
        self.InfoScoreTable = InfoScoreTable
        self.UniqueSortedLabels = UniqueSortedLabels
        self.OnlyLettersDigitsLabels = OnlyLettersDigitsLabels
        self.RBActive = RBActive
        self.DataCleanerRePatternDict = DataCleanerRePatternDict
        if MPLOGGER == None:
            self.MPLOGGER = MPlogger(logFile="sampleHandler.log")
        else:
            self.MPLOGGER = MPLOGGER
        
    def show(self,):
        print("="*50)
        print("FileName:", self.file)
        print("預輸入LabelList[:20]:", self.LabelList[:20])
        print("width:", self.width)
        print("Mode:", self.Mode)
        print("ConvertToSpec:", self.ConvertToSpec)
        
    def textSegsToSamples(self,textList,InLabel):
        result = []
        #空字串不轉換為樣本。
        textList = list(filter(None, textList))
        #如果是從Elasticsearch載入文本，self.file預設值為id，
        #如果Vis_ESFileNameMode模式為"subject_id"
        #且有抓到標題ESsubject，則將標題添加於self.file前面。
        if self.esJob.get("Vis_ESFileNameMode","") == "subject_id":
            if self.ESsubject != None:
                if type(self.ESsubject) is not str:
                    self.ESsubject = str(self.ESsubject)
                self.file = RemoveIlleagalCharForFileName(
                    self.ESsubject)[:100]+"_"+self.file
        if "es_tokens" in self.esJob.keys():
            if self.esRetMeta.get("Target",None) == "T":
                self.file = f"Target/{self.file}"
            else:
                self.file = f"NonTarget/{self.file}"
        if len(self.esRetMeta.get("itcDT","")) > 0:
            for fmtcand in ["%Y-%m-%dT%H:%M:%S",
                            "%Y-%m-%dT%H:%M:%S.%fZ",
                            "%Y-%m-%dT%H:%M:%SZ"
                            ]:
                try:
                    itcDT = dte.datetime.strftime(dte.datetime.strptime(
                        self.esRetMeta['itcDT'],fmtcand),"%Y%m%d")
                    break
                except Exception as e:
                    print(f"When converting the date for {self.file}, the following error occurs:\n{e}")
                    itcDT = None
                    pass
            if itcDT is None:
                MES = f"When converting {self.esRetMeta['itcDT']} from ES to %Y%m%d, it failed."
                self.MPLOGGER.logW(MES,printOnScreen=False,logFile="ESGrab.log")
            #itcDT = self.esRetMeta['itcDT']
            self.file = f"{itcDT}/{self.file}"
        for i,textseg in enumerate(textList):
            #print("i,textseg",i,textseg)
            segInLabel = InLabel
            LenSeg = len(textseg)
            #print("textseg at beg",textseg)
            if textseg.count("\n")/LenSeg > 0.1:
                #如果斷行過多，可能代表非預期之單字斷行現象發生，
                #為優化文字排版，故用空白取代斷行。
                textseg = textseg.replace("\n", " ")

            if LenSeg >50 and self.RBActive == True:
                SPCOutLabelCand = ''
                #如果含有大量數字，候選類別為未知數字串。
                if GetRatioOfDigits(textseg,SpaceExcluded=True) > 0.9:
                    #Uncertainty-Unidentified Digits，
                    #然後continue。
                    SPCOutLabelCand = 'Uncertainty-Unidentified Digits'
                #如果含有大量"."，候選類別為目錄。
                elif textseg.count(".")/LenSeg > 0.9:
                    SPCOutLabelCand = 'BD-Table Of Contents'
                #如果含有最多的字元含量大於90%，候選類別為毀損資料流。
                elif Counter(textseg).most_common()[0][1]/LenSeg > 0.9:
                    SPCOutLabelCand = 'False Decoding-Broken Data Stream'
                #SPCOutLabelCand = 'False Decoding'
                #如果數字比例大且去除特殊符號、數字、字母A-F後，
                #剩下的中文或其他語文字元過少，
                #則直接判定OutLabel為SPCOutLabelCand
                if len(re.sub('[ -F,\[-f,\{-~]','',textseg)) < 40 and SPCOutLabelCand != "":
                    sample = {
                        "file":self.file,
                        "InLabel": segInLabel,
                        "OutLabel": SPCOutLabelCand,
                        "text": textseg,
                        #"file": self.file,
                        "PartNO":i
                        }
                    result.append(sample)
                    continue
            if self.RBActive == True:
                #針對特殊條件進行Rule-Based InLabel設定。
                #取出符合觸發條件的標籤
                sampleLenLBD = self.sampleMethod["LenLBD"]
                ReMatchedLabel = sorted(
                    #[self.RBDict[pat] for pat in self.RBDict.keys() 
                     #if len(re.findall(pat,textseg.lower()))>max(self.width/40,6)], 
                    [self.RBDict[(pat,intv)] for (pat,intv) in self.RBDict.keys() 
                     if intv[0]<=len(re.findall(pat,textseg.lower()))<=intv[1]], 
                    key = lambda x:self.InfoScoreTable[x]
                    )
                #print("ReMatchedLabel",ReMatchedLabel)
                if len(ReMatchedLabel)>0:
                    segInLabel = ReMatchedLabel[-1] #選符合條件中最高分的當InLabel
            #如果有簡繁轉碼設定，則使用OpenCC模組進行轉換。
            if self.ConvertToSpec != None:
                cc = OpenCC(self.ConvertToSpec)
                textseg = cc.convert(textseg)
            #樣本文字數量大於self.sampleLenLBD，才輸出。
            sampleLenLBD = self.sampleMethod["LenLBD"]
            if len(textseg) > sampleLenLBD-1:
                if len(self.LabelConvertDict) > 0:
                    #print("In read, label is {} and LabelConvertDict is {}"
                          #.format(label,self.LabelConvertDict))
                    OutLabel = self.LabelConvertDict[segInLabel]
                else:
                    OutLabel = segInLabel
                #print("label af is {}".format(label))
                sample = {
                    "file":self.file,
                    "InLabel": segInLabel,
                    "OutLabel": OutLabel,
                    "text": textseg,
                    #"file": self.file,
                    "PartNO":i
                    }
                result.append(sample)

        #將樣本清單隨機排序，俾如果有設定"單一文本取樣上限"時，可全文分散選取。
        if self.sampleMethod["RandomSample"] == True:
            random.shuffle(result)
        #如果該類別有設定"單一文本取樣上限"，縮減輸出樣本量。
        #result = result[0:self.nBound.get(InLabel, self.nBound["default"])]
        nBound = self.sampleMethod["nBound"]
        result = result[0:nBound.get(InLabel, nBound["default"])]
        #回傳取出樣本。[{'label': 'xxxx', 'text': 'xxxxxx', 'file':'xxxxxx'},{...},{...},...]
        return result
            
        
    def run(self,):
        MES = "Dealing file {}.\n".format(self.file)
        #print("self.tokenizationWrap",self.tokenizationWrap)
        #time.sleep(10)
        self.MPLOGGER.logW(MES,printOnScreen=False)
        nullReturn = [], (None, 0)
        #print("self.esJob",self.esJob)
        #print("LoadedCZJCorpusText",LoadedCZJCorpusText)
        #if LoadedCZJCorpusText != "":
            #text = LoadedCZJCorpusText
        #print("self.CZJCorpusSQLFile",self.CZJCorpusSQLFile)
        #print("os.path.isfile",os.path.isfile(self.CZJCorpusSQLFile))
        #如果有es_tokens，則表示其為ES伺服器任務。
        fileExt = getFNExtFromFullPath(self.file).lower()
        #print("handling",self.file)
        if "es_tokens" in self.esJob.keys():# != {}:
            #ConWay = "Estoken"
            es_tokens = self.esJob["es_tokens"]
            retry = 0
            text = None
            while(retry == 0 or (retry<100 and text is None)):
                try:
                    es = Elasticsearch(
                        es_tokens['host'],
                        http_auth=(es_tokens['user'], es_tokens['password']),
                        verify_certs=False
                        )
                    res = es.get(index=self.esJob['indexname'],id=self.file)
                    text = res['_source']['rawInfo'].get('content')
                except Exception as e:
                    MES = f"When handdling {self.file} with retrial for {retry} times, the following error occrus:\n{e}\n"
                    self.MPlogger.logW(MES,printOnScreen=False)
                finally:
                    retry += 1
            if text == None:
                print(MES)
                return [],(None,0)
            if "subject" in self.esJob.get("Vis_ESFileNameMode",""):
                self.ESsubject = res['_source']['communication'].get('subject', "")
            userNames = res['_source'].get('userNames',[])
            if len(userNames) > 0:
                #self.Target = "T"
                self.esRetMeta["Target"] = "T"
            self.esRetMeta["itcDT"] = res['_source'].get('itcDT',"")            
            #tex =es.search(index=indexname,body=jqbody,scroll="2m")
            es.close()
            #假定ES資料庫無Label，故直接設定為Scrap。
            InLabelList = ["Scrap"]
            #self.Src = f"{self.Target}/{self.file}"
        elif self.CZJCorpusSQLFile != "":
            #ConWay = "SQLFI"
            conn = lite.connect(self.CZJCorpusSQLFile)
            label_query = 'SELECT InLabel,text FROM Corpus WHERE title=?'
            InLabel, text = conn.execute(label_query, [self.file]).fetchone()
            conn.close()
            if InLabel is None:
                InLabel = "Scrap"
            InLabelList = [InLabel]
            
        elif fileExt in ["ai2","txt"]:
            #ConWay = "ai2,txt"
            #依子目錄名，決定label。
            #InLabel = ""
            InLabelList = []
            #如果完整檔名路徑含有特定Label，則該檔切出樣本使用該Label。
            InLabelList = getLabelsFromFileName(
                self.file,
                UniqueSorted = self.UniqueSortedLabels,
                OnlyLettersDigits = self.OnlyLettersDigitsLabels)
            MES = f"InLabelList:{InLabelList}"
            self.MPLOGGER.logW(MES,printOnScreen=False)
            '''
            for term in self.LabelList:
                if term in getLabelsFromFileName(self.file):
                    InLabelList.append(term)
            '''
            #if "COVID-19" in InLabelList:
                #print("for file {}, LabelList is {}".format(self.file,InLabelList))
            #如果完整檔名路徑不含有任何Label，
            #但副檔名為AI2，則強制添加Scrap為Label，
            #否則回傳空列表，表示無取出樣本。
            if InLabelList == []:
                if getFNExtFromFullPath(self.file).lower() in [
                    x.lower() for x in ["AI2"]]:
                    InLabelList = ["Scrap"]
                else:
                    return nullReturn
            #讀取文本。
            text = textReader(
                file=self.file,encoding="utf-8").run()
            
            if 'text' not in locals():
                print('*'*50)
                MES = f"SamepleHandler Line 305 WARNing! When handling {self.file} with ai2 or txt, text is not defined"
                self.MPLOGGER.logW(MES)
                return nullReturn
            
            #如果正規表示式資料清理字典非空，則進行相對應處理。
            RePatternDict = self.DataCleanerRePatternDict
            if len(RePatternDict.keys()) > 0:
                InputRePatternDict = {}
                for key in RePatternDict:
                    #如果輸入文本標籤清單不略在排除清單內，才進行相關資料清理。
                    if ListCap(InLabelList,RePatternDict[key].get(
                            "ExemptInLabelList",[])) == []:
                        InputRePatternDict[key] = RePatternDict[key]
                        text = DataCleanerWithPattern(
                            text,InputRePatternDict).proc()

        #處理CZJ切片樣本集合sql3檔
        #每一列欄位樣態：{'file': 'FixedTest/FixedTest_8050/Using/20220301/#T#[CN-IND Boundary]/老一辈革命家处理中印边界问题的对策方法.txt',
        #'InLabel': 'CN-IND Boundary',
        #'OutLabel': 'CN-IND Boundary',
        #'text': '文献研究室研究员，北京100017〕',
        #'PartNO': 65}
        #elif "CZJ_SamplesFile.sql3" in self.file:
        elif re.search(".*CZJ_SamplesFile.*sql3",self.file) is not None:
            #ConWay = "CZJ_SamplesFile in sql3"
            print("*"*50)
            print(f"Loading SamplesFile Database in CZJ Format {self.file}")
            df = dfFromSQLite3(self.file).reset_index(drop=True).drop(columns=["index"])
            result = df.to_dict('records')
            MultiLabelCount = (None, 0)
            return result, MultiLabelCount
        elif re.search(".*CZJ_CorpusFile.*sql3",self.file) is not None:
            #ConWay = "CZJ_SamplesFile in sql3"
            print("*"*50)
            print(f"Loading Corpus Database in CZJ Format {self.file}")
            df = dfFromSQLite3(self.file).reset_index(drop=True).drop(columns=["index"])
            df["InLabel"].fillna("Scrap",inplace=True)
            print("df", df)
            #result = df.to_dict('records')
            result = []
            for idx,dfrow in df.iterrows():
                title = dfrow["title"]
                CZJtext = dfrow["text"]
                print("title",title)
                #print("type(CZJtext)",type(CZJtext))
                #SelfRun = self.run(self,LoadedCZJCorpusText=CZJtext)
                result = SampleReader(
                    file=title,CZJCorpusSQLFile=self.file,tokenizationWrap=True).run()
                print("result",result)
                #print(SelfRun)
                #dfrow["text"]
                #print("dfrow",dfrow)
                #print("dfrow[0]",dfrow[0])
                #print("dfrow[1]",dfrow["text"])
            MultiLabelCount = (None, 0)
            print("result",result)
            #return result, MultiLabelCount

            
        #elif self.SQLFile != "":
            ##ConWay = "SQLFI"
            #conn = lite.connect(self.SQLFile)
            #label_query = 'SELECT topics,Context FROM Corpus WHERE FilePath=?'
            #topics, text = conn.execute(label_query, [self.file]).fetchone()
            #InLabelList = LabelsStringReader.proc(topics)
        else:
            MES = f"When handling {self.file}, there is no fullfilled condition to pick sample handler, return Null!"
            self.MPLOGGER.logW(MES)
            return nullReturn
        
        
        text = BasicDataCleaner(
            strQ2B = True,DummySpace = True).proc(text)
        '''
        #去除斷行。
        #text = text.replace("\n", " ")
        #將全形字母、數字換成半型，以利tokenize。
        text = strQ2BConverter().proc(text)
        #若遇連續空白，只留下一個空白。
        text = re.sub(" \n", "\n", text)
        for x in ["\n"," ","\n "," \n"]:
            text = re.sub(f"({x})+", x, text)
        text = re.sub(" \n", "\n", text)
        '''
        #print("self.modelDir",self.modelDir)
        textList = TextDivider(
                 file = self.file,text = text,Mode = self.Mode,
                 tokenizationWrap = self.tokenizationWrap,
                 modelDir = self.modelDir,ReTks = False,
                 width = self.width,
                 ).proc()
        #print("textList in sampleHandler",textList)
        result = []
        #if "COVID-19" in InLabelList:
            #print("="*50)
            #print("len(result)", len(result))
        #如果不縮減InLabelList，將輸出所有Label的同樣樣本，
        #如:PRC_OffDoc/path/COVID-19，
        #會輸出PRC_OffDoc及COVID-19兩個相同內容之樣本
        #反之，如果UniqueLabel設定為True，
        #將會依Label重要分數評估表縮減InLabelList為某個分數最高的Label，
        #將其輸出為該Label單一樣本
        #sampleHandler_InfoScoreTable
        InfoScoreTable = self.InfoScoreTable
        SPCScoreTable = {"PRC Document":15,
                         "PRC-OffDoc":17,
                         "PRC-WReport":17,
                         "PRC-Law":17,
                         "PRC-Think":17}
        InfoScoreTable.update(SPCScoreTable)
        if len(InLabelList) > 1 and self.UniqueLabel == True:
            #print("="*50)
            #print("InLabelList:", InLabelList)
            labelAvailability = [(x,x in InfoScoreTable.keys()) for x in InLabelList]
            if not all([availability for x,availability in labelAvailability]):
                #print("InLabelList:", InLabelList)
                #print("InfoScoreTable.keys()", InfoScoreTable.keys())
                MES = f"When run sampleReader for {self.file}, the following labels"
                MES += f" {[x for x,availability in labelAvailability if availability is False]}"
                MES += " of InLabelList are not in InfoScoreTable.keys().\n"
                #MES += (str(ex)+"\n")
                self.MPLOGGER.logW(MES,logFile="SampleReader.log")
            #取絕對值為最大的分數
            MaxScore = max([InfoScoreTable[x] for x in InLabelList], key= lambda x:abs(x))

            for x in InLabelList:
                if InfoScoreTable[x] == MaxScore:
                    InLabelList = [x]
                    break
        
        for InLabel in InLabelList:
            MES = ""
            if InLabel == "Positive":
                SampleDupeTime = 1
                #MES = "Positive samples dump"
                #MPlogger.logW(MES)
            else:
                SampleDupeTime = 1
                #MES = "Not Positive samples No dump"
                #MPlogger.logW(MES)
            try:
                Samples = self.textSegsToSamples(
                    textList,InLabel)*SampleDupeTime
                result.extend(Samples)
            except KeyError as e:
                MES = f"KeyError occurred: {e}"
    
            except Exception as e:
                MES = e
                
            if MES != "":
                MES = f"When transffering {self.file} to samples, the following error occurs:\n{MES}\n"
                self.MPLOGGER.logW(MES,logFile="SampleReader.log")
            #result.extend(Samples)
        #print("return",result)
        MultiLabelCount = (None, 0)
        if len(InLabelList) > 1:
            MultiLabelCount = (set(InLabelList), len(result)/len(InLabelList))
        #if "COVID-19" in InLabelList:
            #print("for file {}, 輸出樣本為{}".format(self.file,result))
        return result, MultiLabelCount

def tokenization_wrap_Test(TestString,args=dict()):
    global tokenizer
    #model_checkpoint = "./xlm-roberta-base"
    if args.ModelType == "PytorchXLM":
        model_checkpoint = "xlm-roberta-base"
    elif args.ModelType == "PytorchRBTL3":
        model_checkpoint = "chinese_rbtl3_L-3_H-1024_A-16_Pytorch"
        
    for model_ckptDir in ["./","./BertScript/"]:
        #for model_checkpoint in ["./xlm-roberta-base","./BertScript/xlm-roberta-base"]:
        model_ckptPath = model_ckptDir+model_checkpoint
        print("="*50)
        print("model_ckptPath",model_ckptPath)
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_ckptPath)
            #如果成功載入tokenizer的話，回存取獲的完整模型正確路徑到model_checkpoint。
            model_checkpoint = model_ckptPath
            print("final model_checkpoint",model_checkpoint)
            break
        except:
            pass

    tokensWrap = tokenization_wrap(TestString, model_checkpoint,ReTks=True)
    print("tokensWrap",tokensWrap)
    print("len(tokensWrap[ctxCut]",[len(x) for x in tokensWrap["ctxCut"]])
    print("len(tokensWrap[ReTks]",[len(x) for x in tokensWrap["ReTks"]])

if __name__=='__main__':
    #setproctitle.setproctitle(f'TxCL_Transformer')
    args = ClassfierOptionParser()
    
    TestString = """\
东方证券-农业行业禽养殖专题之二：白鸡拐点已至，黄鸡景气持续

农业行业
行业研究 | 深度报告

白羽肉鸡：淡季价格坚挺，引种依然受限。3 月下旬开始，鸡肉价格稳步上涨，6 月末屠宰加工企业白羽肉鸡产品综合价格回到 11.11元/公斤，同比上涨 8.7%，7月第 3 周价格为 11.13 元/公斤。本轮价格上涨略超预期，一方面，价格上涨于二季度传统淡季；另一方面，2022 年上半年的鸡苗供应量由 3 个季度之前父母代鸡苗销量决定，彼时父母代鸡苗同比增加 4.5%，当前供应水平不应紧缺，但是上半年商品代鸡苗销量同比大幅减少 12%。我们认为，偏高的产能与偏低的供应水平或与种鸡质量降低、持续低迷行情打击补栏情绪有关。由于毛鸡供应偏紧，但补栏意愿疲弱，行业利润向养殖环节集中，近 4个月单羽盈利在 2元以上。往后来看，1）父母代鸡苗的销售量自 2021 年 10 月开始拐点向下，对应今年下半年的商品代鸡苗出现实质性的下降，供应或将进一步收紧；2）祖代引种断档已经持续 2 个月，上半年祖代雏鸡累计更新数量仅 47 万套，同比减少 21.5%，其中 5、6 月更新数量分别为 0、4 万套，引种量均为 0套，祖代更新不足对行业下游供应的冲击或将重演。

黄羽肉鸡：产能低位运行，猪鸡景气共振。黄羽肉鸡的价格自 2021年年中便开启上涨，受季节性消费波动影响，2022年 3月之后价格有所承压，于 4月末再度开启上涨，7月第 4周周末，中速鸡、慢速鸡价格已分别涨至 17.44、18.90元/公斤，同比涨幅分别为 40.6%、38.8%。往后来看，1）根据黄羽肉鸡生长周期规律， 2022 年 Q3的商品代鸡苗供应量由 2021年 Q4父母代鸡苗供应量决定，2021Q4监测企业的父母代鸡苗销量环比减少 7.7%，因此预计 Q3 市场依然处于鸡苗偏紧缺状态，叠加黄鸡育肥平均周期约 3 个月，从而价格景气至少有望持续至年末，且存在进一步上涨的可能。2）虽然价格恢复较早，但是由于原料价格上涨，行业的盈利始终没有得到充分的恢复，进而掣肘行业补栏。2022 年上半年，全国父母代黄羽肉种鸡平均存栏量 3946.8万套，同比减少 5.62%，仍处于近 3年低位，产能边际增量偏低，中期对高价的压制程度或较弱。3）黄鸡消费场景与猪肉消费极为类似，从而在价格趋势上与猪价具有较明显的同步特征，随着猪价拐点向上趋势明确，黄羽肉鸡的价格走势有望与猪价同步上行。

白羽肉鸡：白羽肉鸡经历相对漫长的低迷后，下半年有望迎来相对确定性的供应拐点，叠加行业偏弱的养殖效率、餐饮消费的逐步复苏以及北美引种持续断档催化，行业至暗时刻已经过去，关注具备自主种源和养殖、食品两端的白鸡养殖龙头以及业绩具备苗价和鸡价弹性的相关标的。

黄羽肉鸡：黄羽肉鸡产能去化相对明显，我们认为价格景气至少持续至年底，关注后续价格超预期机会，关注温氏股份、立华股份、湘佳股份。

风险提示：原材料价格波动、发生鸡类疫病、消费需求下滑超预期

目 录
白羽：淡季价格坚挺，引种依然受限 .............................................................. 4
养殖环节利润恢复，鸡苗供应量增质减 .............................................................................. 4
北美供种制约持续，祖代更新下降明显 .............................................................................. 5
黄羽：产能低位运行，猪鸡景气共振 .............................................................. 8
毛鸡成本涨幅明显，养殖效益恢复偏慢 .............................................................................. 8
存栏仍在低位，下半年景气持续 ......................................................................................... 9
投资建议 ...................................................................................................... 11
风险提示 ...................................................................................................... 11
"""
    tokenization_wrap_Test(TestString,args=args)

    #CorpusSQL = "CZJ_CorpusFile_SDSMS_Prediction_FixedTest.sql3"
    #SampleReader(file=CorpusSQL).run()