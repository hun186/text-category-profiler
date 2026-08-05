from PackageImport import PackageImporter
PackageImporter.proc()

import os
import time
import platform

from utils.utilities import timeNow
from utils.utilities import MKDIR
from utils.utilities import colored_print
from utils.MP_utils import multicoreJob
from utils.TCF_utils import ClassfierOptionParser

WorkPoolROOT = "WorkPool"
WorkPoolROOT_ArticleComposition = "WorkPoolROOT_ArticleComposition"
#TopicTextCrawlerROOT = "TopicTextCrawler"
TopicTextCrawlerROOT = "../../AIData/text-category-profiler-data/"
DatasetConverterROOT = "DatasetConverter"


def setArguments():
    args = ClassfierOptionParser()
    '''
    for x in ["WorkPoolROOT","BertDataDir","datasetDBDir",
              "mdlDir","ExpDBPATH","DFAllExpPath","FTPath",
              "WTFInpPath","WTFOptPath","WTworkIDPath",
              "WeiTechworkIDPath"
              ]:
        args(x) = getatribute(args,x).replace("\\","/")
    '''
    args.WeiTechworkIDPath = args.WeiTechworkIDPath.replace("\\","/")
    if args.ESDataConfigFile != "":
        #esJob = json.load(open(args.ESDataConfigFile))
        from DatasetConverter.ESDataConfigFile import esJob
    else:
        esJob = dict()

    if args.public == True:
        publicOpt = "-pub True"
    else:
        publicOpt = ""
        
    #開始進行模型訓練或推論。
    if args.train == False and args.test == False:
        print("Dataset Conversion are finished and Both of args.train and args.test are False. Return.")
        os.system("pause")
        #system.quit()
        
    execTime = timeNow()
    if args.ExecutionTime == "":
        args.ExecutionTime = execTime
    '''
    exeTimeDict = {
        "start":time.time(),
        }
    '''
    #exeTimeDict["start"] = time.time()
    #start_time = time.time()
    #stage_time_cost = []

    if args.WeiTechFormatInputPATH != "":
        #WeiTechFormatInputPATH = args.WeiTechFormatInputPATH
        NewWeiTechFormatInputPATH = "{}_{}_is_running_AI".format(
            args.WeiTechFormatInputPATH,args.ExecutionTime)
        os.rename(args.WeiTechFormatInputPATH,NewWeiTechFormatInputPATH)
        MKDIR(args.WeiTechFormatInputPATH)
        args.WeiTechFormatInputPATH = NewWeiTechFormatInputPATH
    if args.task in ["SDSMS","SDSMS_Prediction"]:
        FinalOfferedOutputFNrePatList.extend(["SDSMS.*"])
        args.ExtractionConverterTask = args.task

    args.nProcess = multicoreJob().ComputeNProcess()
    args.nProcessSPC = multicoreJob().ComputeSPCNProcess()
    #遷移式學習功能，考慮遺忘現象之不良影響，已移除。
    #ContinueTrainAfterConvert = False
    #TestAfterConvert = getattr(args,"test")
    
    return args

args = ClassfierOptionParser()

        
if args.debugMode == True:
    ROOTPATHList = [
        "TopicTextCrawler/TrainSamples",
        ]
    #print(f"Run in debug Mode ROOTPATHList is forced set as {ROOTPATHList}")
    run_mode = "debug"
#if 'linux' in platform.system().lower() or tf.test.gpu_device_name():# and False:
elif args.TrainDRNDataOnly == True:
    ROOTPATHList = [
        "===DRNData",
        ]
    run_mode = "TrainDRNDataOnly"
elif 'linux' in platform.system().lower():# or len(GPUDevices)>0:# and False:
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
    run_mode = "linux"
    if args.trainWithMaliciousDomainDataset == True:
        #ROOTPATHList.append("惡意網址分析/SelfDownload")
        ROOTPATHList.append("惡意網址分析")
        run_mode += "+trainWithMaliciousDomainDataset"       
else:
    ROOTPATHList = [
    "TrainSamples",
    ]
    run_mode = "debug"

colored_print(f"Run in {run_mode} Mode, ROOTPATHList is set as {ROOTPATHList}")

FinalOfferedOutputFNrePatList = [
    "^DFPreambleCols_df_ALL.*",
    "dataset_total_with_filename_FixedTest.sql3",
    "test.sql3",
    "test.tsv",
    ]
'''
if args.task == "SDSMS":
    FinalOfferedOutputFNrePatList.extend(["SDSMS.*"])
    args.ExtractionConverterTask = "SDSMS_Prediction"
'''
#設定Bert分類器訓練程式路徑，以進行資料集相關檔案輸出至該路徑，如果不存在，則暫時設為dataset子目錄存放。
BertClassfierPath = 'BertScript'

#單篇文章用來進行摘要的片數上限
nPiecesToSummaryUPD = 26