import platform

WorkPoolROOT = "WorkPool"
#TopicTextCrawlerROOT = "TopicTextCrawler"
TopicTextCrawlerROOT = "../../AIData/text-category-profiler-data/"
DatasetConverterROOT = "DatasetConverter"

CombinerROOTPATHList = [
    #"BigDataWarehouse/論文/汉斯期刊網",
    "BigDataWarehouse/論文/ScientificResearch", #只有英文摘要
    ]
#if 'linux' in platform.system().lower() or tf.test.gpu_device_name():# and False:
if 'linux' in platform.system().lower():# or len(GPUDevices)>0:# and False:
#if False:
    ROOTPATHList = [
        "News/THUCNews",
        "News/AFPBB",
        "News/HuffPost",
        "Kaggle",
        "BigDataWarehouse",
        "===DRNData",
        "TopicTextCrawler/Books",
        "TopicTextCrawler/C_GoogleSearch",
        #"C_wikisourceSearch",
        "TopicTextCrawler/C_wikisourcePortal",
        ]
else:
    ROOTPATHList = [
        #"TopicTextCrawler/TrainSamples",
        #"TopicTextCrawler/C_HansJournal",
        "TopicTextCrawler/C_ScientificResearch", #只有英文摘要
        #"BigDataWarehouse/汉斯期刊網", #
        #"THUCNews",
        #"AFPBB",
        #"===DRNData",
        #"TopicTextCrawler/Books",
        #"TopicTextCrawler/C_GoogleSearch",
        #"TopicTextCrawler/C_wikisourceSearch",
        #"TopicTextCrawler/C_wikisourcePortal",
        ]


SummarizationExcelROOTPATHList = [
    r"D:\shared\TopicClassification\GenerativeLanguageModel\摘要標註", #人工標註
    r"J:\AI\TopicClassification\GenerativeLanguageModel\摘要標註", #人工標註
    ]

#設定Bert分類器訓練程式路徑，以進行資料集相關檔案輸出至該路徑，如果不存在，則暫時設為dataset子目錄存放。
BertClassfierPath = 'BertScript'
