import math
from DatasetConverter.EXTConverter.Combiner import EmbassyPagesCombiner

ExtractionRuleDict = {
    "Malicious URLs dataset":{
        #檔案所在目錄
        "DirName":"TopicClassification/惡意網址分析/Malicious URLs dataset",
        #CSV的檔名
        "fileNames":["malicious_phish.csv"],
        #輸出sql3之主檔名
        #"OUTPUTMAIN":"",
        #如果輸出檔案已存在，是否重做並覆蓋
        "OverWriteOutput":True,
        #如果TestSetFormatOutput為True，則除了CZJ格式，亦輸出TestSet格式
        "TestSetFormatOutput":False,
        #SQL3內的file欄位是否要填入
        "FileNameInSQL3":False,
        #CSV首列是否為欄位名header列
        "header":True,
        #欄位分隔符號
        "Sep":",",
        #欄位數量
        "nCSVCol":2,
        #文本所在欄位，由0開始編號。
        "TextCol":[0],
        #標籤欄資訊
        "LabelInfo":{
            #標籤欄所在欄位，由0開始編號。
            "nCol":1,
            #標籤轉換映射
            "Mapping":{
                "benign":"Benign Web Link",
                "phishing":"Phishing Web Link",
                #"defacement":"Defacement Web Link",
                "malware":"Malware Web Link"
                },
            #標籤轉換後再加上前置字串，如無任何手動設定，抽取程式預設值為不加任何字串。
            "Prefix":"",
            #如果讀入標籤不在轉換映射的key裡時，該筆資料是否保留，False為不保留。
            #如無任何手動設定，抽取程式預設值為True，以讀入標籤保留該筆資料。
            "KeepUnseenInMapKey":False,
            },
        #單一類別之轉換抽取上限筆數，如無任何手動設定，抽取程式預設值為無限。
        "SingleTypeUPD": math.inf
        #"SingleTypeUPD": 100000
        },
    "DGA Detection":{
        "DirName":"TopicClassification/惡意網址分析/DGA Detection",
        "fileNames":["dga-domain.txt"],
        "header":False,
        "Sep":"\t",
        "nCSVCol":4,
        "TextCol":[1],
        "LabelInfo":{
            "nCol":0,
            "Mapping":{
                },
            "Prefix":"DGA Web Link-"
            },
        "SingleTypeUPD": 10
        },
    "Phishing Site URLs":{
        #檔案所在目錄
        "DirName":"TopicClassification/惡意網址分析/Phishing Site URLs",
        #CSV的檔名
        "fileNames":["phishing_site_urls.csv"],
        #CSV首列是否為欄位名header列
        "header":True,
        #欄位分隔符號
        "Sep":",",
        #欄位數量
        "nCSVCol":2,
        #文本所在欄位，由0開始編號。
        "TextCol":[0],
        #標籤欄資訊
        "LabelInfo":{
            #標籤欄所在欄位，由0開始編號。
            "nCol":1,
            #標籤轉換映射
            "Mapping":{
                "good":"Benign Web Link",
                "bad":{#如果標籤對應為一個字典，則進一步用正規表示式去看text是否有滿足任何條件。
                    #使用此法，需設定"default"之對應值
                    "default":"Phishing Web Link",
                     ".*\.exe":"Malware Web Link"},
                },
            #正規表示式標籤轉換映射
            #"ReMapping":{".*":"Benign Web Link",
                #},
            #標籤轉換後再加上前置字串，如無任何手動設定，抽取程式預設值為不加任何字串。
            "Prefix":"",
            #如果讀入標籤不在轉換映射的key裡時，該筆資料是否保留，False為不保留。
            #如無任何手動設定，抽取程式預設值為True，以讀入標籤保留該筆資料。
            "KeepUnseenInMapKey":False,
            },
        #單一類別之轉換抽取上限筆數，如無任何手動設定，抽取程式預設值為無限。
        "SingleTypeUPD": math.inf
        },
    "SelfDownload/C2":{
        "DirName":"TopicClassification/惡意網址分析/SelfDownload/C2",
        "fileNames":["output.csv"],
        "header":False,
        "Sep":",",
        "nCSVCol":2,
        "TextCol":[0],
        "LabelInfo":{
            "nCol":1,
            "Mapping":{
                },
            },
        "SingleTypeUPD": math.inf
        },
    "SelfDownload/Alexa Top 1M":{
        "DirName":"TopicClassification/惡意網址分析/SelfDownload/Alexa Top 1M",
        "fileNames":["top-1m.csv"],
        "header":False,
        "Sep":",",
        "nCSVCol":2,
        "TextCol":[1],
        "LabelInfo":{
            "nCol":0,
            "InputLabelReMapping":{
                ".*":"Benign Web Link",
                },
            "Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    "SelfDownload/OpenPhish":{
        "DirName":"TopicClassification/惡意網址分析/SelfDownload/OpenPhish/OpenPhishFeed",
        "fileNames":[
            #"openphish.com_feed.txt",
            #"openphish.com_feed_MainDomain.txt",
            "openphish.com_feed.*\.txt",
            ],
        "header":False,
        "Sep":",",
        #"nCSVCol":2,
        "nCSVCol":1,
        "TextCol":[0],
        "LabelInfo":{
            "nCol": math.inf,
            "Mapping":{
                },
            "InputLabelReMapping":{
                ".*":"Phishing Web Link",
                },
            "Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    "SelfDownload/URLhaus":{
        "DirName":"TopicClassification/惡意網址分析/SelfDownload/URLhaus",
        "fileNames":["URLhaus.txt"],
        "header":True,
        "Sep":",",
        "nCSVCol":9,
        "TextCol":[2],
        "LabelInfo":{
            "nCol":0,
            "InputLabelReMapping":{
                ".*":"Malware Web Link",
                },
            "Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    "SelfDownload/PhishTank":{
        "DirName":"TopicClassification/惡意網址分析/SelfDownload/PhishTank",
        "fileNames":["Combined.csv"],
        "header":True,
        "Sep":",",
        "nCSVCol":2,
        "TextCol":[1],
        "LabelInfo":{
            "nCol":0,
            "InputLabelReMapping":{
                ".*":"Phishing Web Link",
                },
            "Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    "===DRNData/VirusTotal_Converting/Benign Web Link":{
        "DirName":"TopicClassification/===DRNData/VirusTotal_Converting/Benign Web Link",
        "fileNames":[
            #"openphish.com_feed.txt",
            #"openphish.com_feed_MainDomain.txt",
            ".*VirusTotal Benign Web Link.*\.txt",
            ],
        "header":False,
        "Sep":",",
        #"nCSVCol":2,
        "nCSVCol":1,
        "TextCol":[0],
        "LabelInfo":{
            "nCol": math.inf,
            "Mapping":{
                },
            "InputLabelReMapping":{
                ".*":"Benign Web Link-VirusTotal Benign Web Link",
                },
            "Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    "===DRNData/VirusTotal_Converting/Malicious Web Link":{
        "DirName":"TopicClassification/===DRNData/VirusTotal_Converting/Malicious Web Link",
        "fileNames":[
            #"openphish.com_feed.txt",
            #"openphish.com_feed_MainDomain.txt",
            ".*VirusTotal Malicious Web Link.*\.txt",
            ],
        "header":False,
        "Sep":",",
        #"nCSVCol":2,
        "nCSVCol":1,
        "TextCol":[0],
        "LabelInfo":{
            "nCol": math.inf,
            "Mapping":{
                },
            "InputLabelReMapping":{
                ".*":"Malicious Web Link-VirusTotal Malicious Web Link",
                },
            "Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    "RealTestData/rdy to convert":{
        "DirName":"TopicClassification/惡意網址分析/RealTestData/rdy to convert",
        "fileNames":[
            #"0927.csv",
            #"1206.txt",
            "20[2-7]\d{5}.*\.(csv|txt)"
            ],
        "header":False,
        "Sep":",",
        #"nCSVCol":2,
        "nCSVCol":1,
        "TextCol":[0],
        "LabelInfo":{
            "nCol": math.inf,
            "Mapping":{
                },
            "InputLabelReMapping":{
                ".*":"Benign Web Link",
                },
            "Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    #each line as an example for a specified class
    "LetterGreetings":{
        "DirName":"D:\shared\TopicClassification\DatasetConverter\Dataset Generator\ComponentGenerator",
        "fileNames":[
            "LetterGreetingsForClosing.tsv",
            #"phishing_templates_gpt1.csv"
            ],
        "header":False,
        "Sep":"\t",
        #"nCSVCol":2,
        "nCSVCol":1,
        "TextCol":[0],
        "LabelInfo":{
            "nCol": math.inf,
            #"Mapping":{
                #},
            "InputLabelReMapping":{
                ".*":"Letter Greetings For Closing",
                #".*":"Phishing Attack Email Content",
                },
            #"Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    #產製CZJ_SamplesFile供訓練用，樣本無輸入Label時，則不採用。
    "SDSMS_Train":{
        #"DirName":"TopicClassification/===DRNData/SDSMS/SMS/Deactive_DCRB/rdy to convert",
        "DirName":r"D:\shared\rawData\AIPool_SDSMS\WorkPool",
        "fileNames":[
            #"0927.csv",
            #"1206.txt",
            "SDSMS_20[2-7]\d{5}.*\.(csv|txt)$"
            ],
        "header":True,
        "Sep":",",
        #"nCSVCol":2,
        "nCSVCol":[6,7],
        "TextCol":[5],
        "LabelInfo":{
            "nCol": 6,
            #"Mapping":{
                #},
            "InputLabelReMapping":{
                #"Navigational Warning-.*":"UseInLabelAsOutLabel",
                "(.|\s)*\S(.|\s)*":"UseInLabelAsOutLabel",
                },
            #"Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    #推論用，樣本無輸入Label時，則使用Scrap做為Label。
    "SDSMS_Prediction":{
        #"DirName":r"TopicClassification\rawData\SDSMS\WorkPool",
        "DirName":r"D:\shared\rawData\AIPool_SDSMS\WorkPool",
        "fileNames":[
            #"0927.csv",
            #"1206.txt",
            "SDSMS_20[2-7]\d{5}.*\.(csv|txt)$"
            ],
        #"OUTPUTMAIN":"dataset_total_with_filename_FixedTest",
        "OverWriteOutput":False,
        "CZJ_SamplesFileFormatOutput":False,
        #"TestSetFormatOutput":True,
        "CZJ_CorpusFileFormatOutput":True,
        "FileNameInSQL3":True,
        "header":True,
        "Sep":",",
        #"nCSVCol":2,
        "nCSVCol":[6,7],
        "TextCol":[5],
        "LabelInfo":{
            "nCol": 6,
            "Mapping":{
                "":"Scrap",
                },
            "InputLabelReMapping":{
                "(.|\s)*\S(.|\s)*":"UseInLabelAsOutLabel",
                #"^$":"Scrap",
                },
            #"Prefix":"",
            "KeepUnseenInMapKey":True,
            },
        "SingleTypeUPD": math.inf
        },
    }

CombinationRuleDict = {
    "EmbassyPages-Located Country":{"processor":EmbassyPagesCombiner,
        }
    }