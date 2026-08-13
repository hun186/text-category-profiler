import os
import sqlite3 as lite
from copy import deepcopy
#from MP_utils  import MPlogger
#import tokenization
from DatasetConverter.reader_utils import filename_extension
from DatasetConverter.reader_utils import intersect_lists
from DatasetConverter.reader_utils import normalize_filename
from DatasetConverter.reader_utils import sanitize_filename
from DatasetConverter.reader_utils import wrap_text
from text_category_profiler.concurrency.MP_utils  import MPlogger
from text_category_profiler.core.log_display import key_values
from text_category_profiler.core.log_display import summarize_sequence
#from text_category_profiler.pipeline.TCF_utils import datasetDirOutputDirPickers
from text_category_profiler.core.model_paths import resolve_local_model_directory
from text_category_profiler.text.TextProcessor_utils import textReader
from text_category_profiler.text.TextProcessor_utils import BasicDataCleaner
from text_category_profiler.text.TextProcessor_utils import DataCleanerWithPattern
from ClassesTree.Label_utils import getLabelsFromFileName
from DatasetConverter.sample_pipeline import build_elasticsearch_provenance
from DatasetConverter.sample_pipeline import select_document_samples
from DatasetConverter.sample_pipeline import transform_sample_segment
from DatasetConverter.sample_sources import apply_regular_cleaning_rules
from DatasetConverter.sample_sources import map_elasticsearch_document
from DatasetConverter.sample_sources import fetch_elasticsearch_response
from DatasetConverter.sample_sources import prepare_document_segments
from DatasetConverter.sample_sources import read_czj_corpus_document
from DatasetConverter.sample_sources import read_czj_sample_rows
from DatasetConverter.sample_sources import read_regular_text_document
from DatasetConverter.sample_sources import SourceDocument
from DatasetConverter.elasticsearch_source import create_elasticsearch_client
from DatasetConverter.opencc_source import convert_text
from DatasetConverter.tokenizer_source import load_auto_tokenizer
from DatasetConverter.tokenizer_source import resolve_tokenizer_model
from DatasetConverter.tokenizer_pipeline import analyze_token_word_mapping
from DatasetConverter.tokenizer_pipeline import split_tokenized_context
#from ClassesTree.Label_utils import LabelsStringReader

#from tokenization import FullTokenizer
import re
import random

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
    modelDir = normalize_filename(modelDir or "xlm-roberta-base")
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
    tokenizer_model = resolve_tokenizer_model(
        modelDir,
        resolve_local_directory=resolve_local_model_directory,
        walk=os.walk,
    )
    if tokenizer_model.used_fallback:
        print(
            "WARNING! The input modelDir "
            f"{tokenizer_model.requested_directory} for "
            "tokenization_wrap does not exist; use "
            f"{tokenizer_model.resolved_directory} instead"
        )
    
    #context = "This is a book.這是一本書。那是一枝筆"
    #nTokensToWrap = 6
    nTokensToWrap -= 3 #預留<s>、</s>及開頭補空白的位置
    #debug = True
    #context = "Все счастливые семьи похожи друг на друга, каждая несчастливая семья несчастлива по-своему. Все смешалось в доме Облонских. Жена узнала, что муж был в связи с бывшею в их доме француженкою-гувернанткой, и объявила мужу, что не мо- жет жить с ним в одном доме. Положение это продолжалось уже третий день и мучительно чувствовалось и самими супругами, и всеми членами семьи, и домочадцами. Все члены семьи и домочадцы чувствовали, что нет смысла в их сожительстве и что на каждом постоялом дворе случайно сошедшиеся люди более связаны между собой, чем они, члены семьи и домочадцы Облонских. "
    tokenizer = load_auto_tokenizer(
        tokenizer_model.resolved_directory,
        trust_remote_code=True,
    )
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
    if debug == True:
        tksPos = list(range(1,len(ecTks)-1))
        indicator = [
            tksPos[i:i + nTokensToWrap]
            for i in range(0, len(tksPos), nTokensToWrap)
        ]
        print("token分組位置清單:",indicator)
    chunks = split_tokenized_context(
        context,
        tokenizer,
        maximum_tokens=nTokensToWrap + 3,
        retokenize=ReTks,
        encoding=encoded,
    )
    ctxCut = list(chunks.chunks)
    ReTks = [list(tokens) for tokens in chunks.retokenized]
    if debug == True:
        print("ctxCut",ctxCut)
        print("針對產出再次tokenized的結果:",ReTks)
        print([len(x) for x in ReTks])
    
    if word_analysis and debug:
        analysis = analyze_token_word_mapping(context, encoded)
        print(
            "word_2_char_mapping:",
            {
                word_index: [start, end]
                for word_index, start, end in analysis.word_character_spans
            },
        )
        print(
            "word_2_token_mapping:",
            {
                word_index: list(token_positions)
                for word_index, token_positions in analysis.word_token_positions
            },
        )
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
        TextList = wrap_text(self.text, self.width)
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
                textList = wrap_text(self.text, self.width)
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
                    if len(re.findall(r'\w{2,} ',text_no_digits))/(len(text_no_digits)+10**-100) > 0.11:
                        textList = wrap_text(self.text, 3*self.width)
                    else:
                        textList = wrap_text(self.text, self.width)
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
                 LabelList = None,
                 width = 1024,
                 Mode = "FullCut",
                 tokenizationWrap=False,
                 modelDir="",
                 ConvertToSpec = None,
                 #nBound = {"default":5000}, 
                 #sampleMethod["LenLBD"]為取樣的長度下限，如果切出的樣本字數少於sampleMethod["LenLBD"]則捨棄
                 sampleMethod = None,
                 LabelConvertDict = None, RBDict=None,
                 #TreeBinaryMode = False,
                 TreeBinaryTarget = None,
                 UniqueLabel = True,
                 #SQLFile = "",
                 CZJCorpusSQLFile = "",
                 esJob = None,
                 esRetMeta = None,
                 ESsubject = None,
                 InfoScoreTable = None,
                 UniqueSortedLabels = True,
                 OnlyLettersDigitsLabels = False,
                 RBActive = True,
                 DataCleanerRePatternDict = None,
                 MPLOGGER = None
                 ):
        self.file = file
        #self.LoadedCZJCorpusText = LoadedCZJCorpusText
        self.Src = self.file
        #self.Target = Target
        self.Selected = Selected
        self.LabelList = list(LabelList) if LabelList is not None else []
        self.width = width
        self.Mode = Mode
        self.tokenizationWrap = tokenizationWrap
        self.modelDir = modelDir
        self.ConvertToSpec = ConvertToSpec
        self.sampleMethod = deepcopy(sampleMethod) if sampleMethod is not None else {
            "nBound": {"default": 5000, "Economist": 1000},
            "RandomSample": True,
            "LenLBD": 128,
        }
        self.LabelConvertDict = dict(LabelConvertDict or {})
        #僅針對預輸入LabelList允許的標籤進行代換。
        self.RBDict = {k:v for k,v in (RBDict or {}).items()
                       if v in self.LabelList}
        #self.TreeBinaryMode = TreeBinaryMode,
        #self.TreeBinaryTarget = TreeBinaryTarget,
        self.UniqueLabel = UniqueLabel
        #self.SQLFile = SQLFile
        self.CZJCorpusSQLFile = CZJCorpusSQLFile
        self.esJob = deepcopy(esJob) if esJob is not None else {}
        self.esRetMeta = dict(esRetMeta or {}) #儲存由ES資料庫取得的日期、目標等資訊
        self.ESsubject = ESsubject
        self.InfoScoreTable = dict(InfoScoreTable or {})
        self.UniqueSortedLabels = UniqueSortedLabels
        self.OnlyLettersDigitsLabels = OnlyLettersDigitsLabels
        self.RBActive = RBActive
        self.DataCleanerRePatternDict = deepcopy(DataCleanerRePatternDict or {})
        if MPLOGGER == None:
            self.MPLOGGER = MPlogger(logFile="sampleHandler.log")
        else:
            self.MPLOGGER = MPLOGGER
        
    def show(self,):
        key_values("Sample reader job", [
            ("file", self.file),
            ("label preview", summarize_sequence(self.LabelList[:5], limit=5)),
            ("label count", len(self.LabelList)),
            ("width", self.width),
            ("Mode", self.Mode),
            ("ConvertToSpec", self.ConvertToSpec),
        ], icon="·")
        
    def textSegsToSamples(self,textList,InLabel):
        result = []
        #空字串不轉換為樣本。
        textList = list(filter(None, textList))
        #如果是從Elasticsearch載入文本，self.file預設值為id，
        #如果Vis_ESFileNameMode模式為"subject_id"
        #且有抓到標題ESsubject，則將標題添加於self.file前面。
        provenance = build_elasticsearch_provenance(
            self.file,
            es_job=self.esJob,
            metadata=self.esRetMeta,
            subject=self.ESsubject,
            sanitize_filename=sanitize_filename,
        )
        self.file = provenance.file_path
        if provenance.invalid_date is not None:
            MES = (
                f"When converting {provenance.invalid_date} from ES to %Y%m%d, "
                "it failed."
            )
            self.MPLOGGER.logW(MES, printOnScreen=False, logFile="ESGrab.log")
        for i, textseg in enumerate(textList):
            segment_result = transform_sample_segment(
                textseg,
                file_path=self.file,
                input_label=InLabel,
                part_number=i,
                rule_based_active=self.RBActive,
                rules=self.RBDict,
                info_scores=self.InfoScoreTable,
                label_conversion=self.LabelConvertDict,
                minimum_length=self.sampleMethod["LenLBD"],
                text_conversion=self.ConvertToSpec,
                convert=convert_text,
            )
            if segment_result.row is not None:
                result.append(segment_result.row)

        #將樣本清單隨機排序，俾如果有設定"單一文本取樣上限"時，可全文分散選取。
        result = select_document_samples(
            result,
            input_label=InLabel,
            bounds=self.sampleMethod["nBound"],
            random_sample=self.sampleMethod["RandomSample"],
            shuffle=random.shuffle,
        )
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
        fileExt = filename_extension(self.file, lower=True)
        #print("handling",self.file)
        if "es_tokens" in self.esJob.keys():# != {}:
            #ConWay = "Estoken"
            es_tokens = self.esJob["es_tokens"]
            def log_fetch_error(attempt, error):
                message = (
                    f"When handling {self.file}, Elasticsearch attempt "
                    f"{attempt + 1} failed:\n{error}\n"
                )
                self.MPLOGGER.logW(message, printOnScreen=False)

            res = fetch_elasticsearch_response(
                attempts=100,
                create_client=lambda: create_elasticsearch_client(es_tokens),
                fetch=lambda client: client.get(
                    index=self.esJob['indexname'], id=self.file
                ),
                content_from_response=lambda response: response['_source'][
                    'rawInfo'
                ].get('content'),
                on_error=log_fetch_error,
            )
            if res is None:
                self.MPLOGGER.logW(
                    f"No Elasticsearch content found for {self.file} after 100 attempts."
                )
                return [],(None,0)
            elasticsearch_document = map_elasticsearch_document(
                res,
                include_subject="subject" in self.esJob.get(
                    "Vis_ESFileNameMode", ""
                ),
            )
            text = elasticsearch_document.document.text
            self.ESsubject = elasticsearch_document.subject
            self.esRetMeta.update(elasticsearch_document.metadata)
            #假定ES資料庫無Label，故直接設定為Scrap。
            InLabelList = list(elasticsearch_document.document.input_labels)
            #self.Src = f"{self.Target}/{self.file}"
        elif self.CZJCorpusSQLFile != "":
            #ConWay = "SQLFI"
            source_document = read_czj_corpus_document(
                self.CZJCorpusSQLFile,
                title=self.file,
                connect=lite.connect,
            )
            text = source_document.text
            InLabelList = list(source_document.input_labels)
            
        elif fileExt in ["ai2","txt"]:
            #ConWay = "ai2,txt"
            #依子目錄名，決定label。
            #InLabel = ""
            source_document = read_regular_text_document(
                self.file,
                unique_sorted_labels=self.UniqueSortedLabels,
                only_letters_digits_labels=self.OnlyLettersDigitsLabels,
                labels_from_path=getLabelsFromFileName,
                read_text=lambda **kwargs: textReader(**kwargs).run(),
            )
            if source_document is None:
                return nullReturn
            InLabelList = list(source_document.input_labels)
            MES = f"InLabelList:{InLabelList}"
            self.MPLOGGER.logW(MES,printOnScreen=False)
            '''
            for term in self.LabelList:
                if term in getLabelsFromFileName(self.file):
                    InLabelList.append(term)
            '''
            #if "COVID-19" in InLabelList:
                #print("for file {}, LabelList is {}".format(self.file,InLabelList))
            source_document = apply_regular_cleaning_rules(
                source_document,
                rules=self.DataCleanerRePatternDict,
                labels_in_exemptions=intersect_lists,
                clean_text=lambda value, rules: DataCleanerWithPattern(
                    value, rules
                ).proc(),
            )
            text = source_document.text

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
            result = list(read_czj_sample_rows(
                self.file,
                connect=lite.connect,
            ))
            MultiLabelCount = (None, 0)
            return result, MultiLabelCount
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
        
        
        prepared_document = prepare_document_segments(
            SourceDocument(text=text, input_labels=tuple(InLabelList)),
            normalize_text=lambda value: BasicDataCleaner(
                strQ2B=True, DummySpace=True
            ).proc(value),
            divide_text=lambda value: TextDivider(
                file=self.file,
                text=value,
                Mode=self.Mode,
                tokenizationWrap=self.tokenizationWrap,
                modelDir=self.modelDir,
                ReTks=False,
                width=self.width,
            ).proc(),
        )
        text = prepared_document.text
        InLabelList = list(prepared_document.input_labels)
        textList = list(prepared_document.segments)
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
                if self.LabelConvertDict and InLabel not in self.LabelConvertDict:
                    MES = (
                        f"Input label {InLabel!r} is not present in the label conversion "
                        "map; this sample was dropped. Rename its #T#[...] directory to "
                        "a label defined by the configured TopicTree files."
                    )
                else:
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
