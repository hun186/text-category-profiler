import os
from PackageImport import PackageImporter
PackageImporter.proc()

import time
import shutil
import platform
import setproctitle

from TCF_Params.TCFParameters import BertClassfierPath
from utils.utilities import getFNFromFullPath
from utils.TCF_utils import datasetDirOutputDirPickers
from utils.TCF_utils import get_testResFile_Name
from utils.TCF_utils import freeModelDirConformer
from utils.TCF_utils import ClearOldTestResFile
from utils.TCF_utils import ClassfierOptionParser
from utils.utilities import MKDIR
from utils.utilities import MKDIRandCopy
from utils.utilities import getFNFromFullPath
from utils.utilities import OSWALK
from utils.conformer import freeGPUConformer
from utils.conformer import HybridConformer
from utils.utilities import WaitUntilFileIsStable
from utils.MP_utils import MPlogger
from utils.DB_utils import sqlite3Query
from utils.log_display import info
from utils.log_display import key_values
from utils.log_display import print_command
from utils.log_display import section
from utils.log_display import stage_banner
from utils.log_display import stage_done
from utils.log_display import summarize_sequence
from utils.log_display import warning


def _display_model_command(command, log_path, background=False):
    section("RunClassfier model command", icon="🚀")
    key_values("Command output", [
        ("log file", log_path),
        ("stderr", "redirected to log"),
        ("background", background),
    ])
    print_command(command, label="Model command")


#def CopyModelRelatedFiles(BertDatasetSubDir, outputDir):
def WriteOccurringLabelList(BertDatasetSubDir):
    # 讀取有出現在 train.sql3 中的 Label，並寫到 Bert 參照的 LabelList File 內。
    # 訓練新模型時，label space 應以 train split 實際可學到的類別為準；
    # 否則完整 taxonomy 中沒有訓練樣本的 label 會進入 classifier head。
    sql3File = os.path.join(BertDatasetSubDir,"train.sql3")
    query = f'SELECT DISTINCT OutLabel FROM sampleSrc;'
    OccuringLabelList = sqlite3Query(
        sql3File, query = query,ListForm = True)
    labelListFile = os.path.join(BertDatasetSubDir,
            "TopicAnalysis_LabelList.txt")
    with open(labelListFile, 'wt',encoding='utf-8') as f:
        for y in sorted(set(OccuringLabelList)):
            f.write(y+"\n")
    return OccuringLabelList


def CopyModelRelatedFiles(
        srcDir, desDir,datasetDBDir="datasetDB",onlyLabelFile=False
        ):
        #可能會有training時WorkPool下的dataset目錄copy到BertScript下的output模型目錄
        #或test時，反向copy等兩種可能，為了避免錯誤覆蓋，如果檔案存在則不copy
        #TopicAnalysis_LabelList for CombineTestResult
        for file in [
                "TopicAnalysis_LabelList.txt",
                #"TopicAnalysis_LabelList_Including_NonOccuring.txt",
                ]:
            src = os.path.join(srcDir,file)
            des = os.path.join(desDir,file)
            if os.path.isfile(des):
                continue
            MKDIRandCopy(src, des)
        if onlyLabelFile == True:
            return
        #模型訓練集統計與標註檔案留存，供分析人員參考
        FNMatchList = list(map(getFNFromFullPath,OSWALK(srcDir,
            FNrePat="(TopicTree.*)|(InfoScoreTable.*)")))
        for file in [
                "dataset.txt",
                "TopicAnalysis_LabelList_Including_NonOccuring.txt",
                ]+FNMatchList:
            src = os.path.join(srcDir,"OnlyForRecord",file)
            des = os.path.join(desDir,"OnlyForRecord",file)
            if os.path.isfile(des):
                continue
            MKDIRandCopy(src, des)


        FNMatchList = list(map(getFNFromFullPath,OSWALK(srcDir,
            FNrePat="dataset_total_.*")))
        for file in [
                ]+FNMatchList:
            src = os.path.join(srcDir,datasetDBDir,file)
            des = os.path.join(desDir,datasetDBDir,file)
            if os.path.isfile(des):
                continue
            MKDIRandCopy(src, des)

if __name__ == '__main__':
    setproctitle.setproctitle(f'CZJRunClassfier')
    #print("start to run RunCF, wait for 100 secs")
    #time.sleep(100)
    #print(os.getcwd().split(os.path.sep)[-1])
    if os.getcwd().split(os.path.sep)[-1] in [
            "DatasetConverter","BertScript"]:
        os.chdir("../")
        info(f"Change working directory to {os.getcwd()}", icon="📁")
    args = ClassfierOptionParser()
    BertDatasetSubDir,outputDir = datasetDirOutputDirPickers(
        args=args,rdy_for_stage="RunClassfier").proc()
    if BertDatasetSubDir == None:
        MES = f"In {args.WorkPoolROOT}, There is no BertDatasetSubDir ready for RunClassfier! ABORT!"
        MPlogger().logW(MES)
        raise Exception
    NewBertDatasetSubDir = BertDatasetSubDir.replace(
        "_rdy_for_RunClassfier","_is_running_RunClassfier")
    #NewBertDatasetSubDir += BertDatasetSubDir + "_is_running_DataConverter"
    os.rename(BertDatasetSubDir,NewBertDatasetSubDir)
    stage_banner("RunClassfier")
    key_values("RunClassfier workspace", [("WorkDir", NewBertDatasetSubDir)], icon="·")
    MES = f"RunClassfier started. WorkDir is {NewBertDatasetSubDir}."
    BertDatasetSubDir = NewBertDatasetSubDir
    #MPLOGGER = MPlogger(logSubDir=f"{BertDatasetSubDir}/logs")
    MPLOGGER_TCFMain = MPlogger(logSubDir=f"{NewBertDatasetSubDir}/logs",logFile="TCFMain.log")
    MPLOGGER_TCFMain.logW(MES, printOnScreen=False)
    #用來儲存dataset_total_.*檔案位於BertDatasetSubDir下的子目錄。
    datasetDBDir = args.datasetDataBaseSubDir

#%%檢查AI運算資源
    #如果有GPU的話，確認是否有足夠的free GPU memory，如果沒有的話，
    #進入監看狀態，等有足夠free VRAM，再進行AI推論。
    #freeGPUConformer(ObjectName = args.BertDatasetSubDir).proc()
    #freeGPUConformer(ObjectName = BertDatasetSubDir).proc()
    HybridConformer(ObjectName = BertDatasetSubDir).proc()
#-------------------------------------------------------------------------
#%%AI模型訓練或推論
    '''
    if args.BertDatasetSubDir != "":
        BertDatasetSubDir = os.path.join(
            WorkPoolROOT, args.BertDatasetSubDir)
    else:
        #BertDatasetSubDir = os.path.join(
            #BertClassfierPath,f"dataset_{execTime}_{args.ModelType}_pt{args.TRVPort}")
        BertDatasetSubDir = datasetSubDir

    if args.BertDatasetSubDirExt != "":
        BertDatasetSubDir += "_"+args.BertDatasetSubDirExt

    #如果MKDIR，下面又快速直接搬移目錄，跑run_classifier時會報錯（Windows fatal exception: access violation）
    #替代方案為不要MKDIR，直接搬目錄；或者MKDIR，移動每個單檔，但會留下一個空目錄。
    #MKDIR(BertDatasetSubDir)
    MES = "Move {} as {}".format(datasetSubDir, BertDatasetSubDir)
    MPLOGGER_TCFMain.logW(MES)
    #for file in OSWALK(datasetSubDir):
        #des = os.path.join(BertDatasetSubDir,getFNFromFullPath(file))
        #shutil.move(file, des)
    shutil.move(datasetSubDir, BertDatasetSubDir)
    '''

    #print("rdy to query nDict, wait for 100 secs")
    #time.sleep(100)
    stage_start_time = time.time()
    #讀取各測試集資料庫，計算測試本總數，
    #以估算RunClassfier階段預估執行時間，做為TF15推論最大終止時間。
    nDict = {}
    for setsrc, sql3file in [
            ("test","test.sql3"),
            ("fixed_test","dataset_total_with_filename_FixedTest.sql3"),
            ("Elasticsearch","dataset_total_with_filename_ES.sql3")]:
        if setsrc in ["test"]:
            sql3file = os.path.join(BertDatasetSubDir,sql3file)
        elif setsrc in ["fixed_test","Elasticsearch"]:
            sql3file = os.path.join(BertDatasetSubDir,"OnlyForRecord",sql3file)
        query = f'SELECT COUNT() FROM sampleSrc;'
        try:
            if os.path.isfile(sql3file) == True:
                #time.sleep(1)
                nDict[setsrc] = sqlite3Query(
                    sql3file, query = query,ListForm = True)[0]
            else:
                warning(f"Dataset count source missing for {setsrc}; set count to 0. ({sql3file})")
                nDict[setsrc] = 0
        except Exception as e:
            warning(f"Dataset count query failed for {setsrc}; set count to 0. ({sql3file}: {e})")
            nDict[setsrc] = 0
    nDict["test"] -= nDict["fixed_test"]
    nTotalTest = nDict["test"]+nDict["fixed_test"]+nDict["Elasticsearch"]
    #print("finish query nDict, wait for 100 secs")
    #time.sleep(100)
    #nTotalTest = 16


    #os.chdir(BertClassfierPath)
    if args.train == True:
        OccuringLabelList = WriteOccurringLabelList(BertDatasetSubDir)
        if len(OccuringLabelList) <= 1:
            MES = f"{'-'*50}\n These is only one occuring label {OccuringLabelList} for the training set! This will result RuntimeError: Found dtype Long but expected Float! ABORT! Check your training set."
            MPLOGGER_TCFMain.logW(MES)
            raise Exception


        outputDir = f"{BertClassfierPath}/output_{args.ExecutionTime}_{args.ModelType}"
        MKDIR(outputDir)
        #BatCMD += ("--init_checkpoint=./chinese_rbtl3_L-3_H-1024_A-16/bert_model.ckpt"+LineBreaker)

        #將模型相關標籤檔由BertDatasetSubDir複製到outputDir
        CopyModelRelatedFiles(
            #BertDatasetSubDir=BertDatasetSubDir,outputDir=outputDir)
            srcDir=BertDatasetSubDir,desDir=outputDir)


    testResFile = get_testResFile_Name(
        args.ModelType,BertDatasetSubDir=BertDatasetSubDir,outputDir=outputDir)
    key_values("Prediction output files", [("testResFile", summarize_sequence(testResFile, limit=3))], icon="·")
    #如果訓練模式關閉，且測試模式開啓，使用輸入目錄或進行智慧式選定模型目錄。
    if args.test == True:
        if args.modelDir != "":
            outputDir = args.modelDir
            MES = f"Since args.modelDir is {args.modelDir}, the model dir is reset as this value."
            MPLOGGER_TCFMain.logW(MES,logFile="TCFMain.log")
        else:
            outputDir = freeModelDirConformer(
                args = args,
                outputDirsROOT = BertClassfierPath,
                datasetDirsROOT = args.WorkPoolROOT,
                #modelType = args.ModelType,
                testResFile=testResFile).proc()



        #print("outputDir",outputDir)
        #print("BertDatasetSubDir",BertDatasetSubDir)
        #將選中的output模型目錄更名，新增後綴標記 "_Using"，以免被其他程序誤用。
        original_outputDir = outputDir
        if args.ModelType in ["TF15Bert"]:
            using_outputDir = outputDir + f"_Using_{args.ExecutionTime}"
            #shutil.move(outputDir,using_outputDir)
            os.rename(outputDir,using_outputDir)
            outputDir = using_outputDir

        testResFile = get_testResFile_Name(
            args.ModelType,BertDatasetSubDir=BertDatasetSubDir,outputDir=outputDir)
        key_values("Prediction output files after retry", [("testResFile", summarize_sequence(testResFile, limit=3))], icon="·")
        #將模型相關標籤檔由outputDir複製到BertDatasetSubDir，續供CombineTestResult使用。
        #print("rdy to CopyModelRelatedFiles from outputDir to BertDatasetSubDir, wait for 100 secs")
        #time.sleep(100)
        CopyModelRelatedFiles(
            srcDir=outputDir,desDir=BertDatasetSubDir,onlyLabelFile=True)
        #print("finished CopyModelRelatedFiles from outputDir to BertDatasetSubDir, wait for 100 secs")
        #time.sleep(100)


    #使用TF1.5 Bert模型(roberta)
    if args.ModelType == "TF15Bert":
        WindowsAnacondaPath = 'd:/ProgramData/Anaconda3'
        WindowsAnacondaPromptCMD = os.path.join(
            WindowsAnacondaPath,'Scripts/activate.bat')

        if "windows" in platform.system().lower():
            LineBreaker = " ^\n"
        else:
            LineBreaker = " \\\n"

        BatFile = os.path.join(
            BertClassfierPath, "run_classifier_script_automatic_dynamic.bat")
        BatFileTemplateFile = os.path.join(
            BertClassfierPath, "run_classifier_script_automatic_dynamic_template.txt")
        #BatCMD = open(BatFile,'rt',encoding='utf-8').read()
        BatCMD = open(BatFileTemplateFile,'rt',encoding='utf-8').read()
        if "windows" in platform.system().lower():
            BatCMD = "call activate TF1.5\n\n" + BatCMD
        else:
            BatCMD = BatCMD.replace("^\n","\\\n")

        if args.train == True:
            BatCMD += ("--do_train=True"+LineBreaker)
            #BatCMD += "--output_dir={} {}".format(
                #f"./output_{execTime}/", LineBreaker)

        else:
            #BatCMD = BatCMD.replace("--do_train=True", "--do_train=False")
            BatCMD += ("--do_train=False"+LineBreaker)

            MES = f"Using the {args.ModelType} model in {outputDir} to predict."
            MPLOGGER_TCFMain.logW(MES,logFile="TCFMain.log")
        BatCMD += "--output_dir={} {}".format(f"{outputDir}/", LineBreaker)
        BatCMD += (f"--do_predict={args.test}"+LineBreaker)
        BatCMD += (f"--keep_checkpoint_max={args.keep_checkpoint_max}"+LineBreaker)
        BatCMD += "--data_dir={} {}".format(
            f"{BertDatasetSubDir}/", LineBreaker)

        #if "windows" in platform.system().lower():
            #BatCMD +=  "> RunClassfier.log 2>&1 & \n\n"
        #else:
            #BatCMD +=  "2>&1 | tee RunClassfier.log \n\n"
        #如果是訓練模式，因枆時甚長，無需計算各階段時間，則採背景作業。
        run_log = os.path.join(BertDatasetSubDir, "logs", "RunClassfier.log")
        BatCMD += f'> "{run_log}" 2>&1'
        if args.train == True:
            BatCMD += " &"
        BatCMD += " \n\n"
        open(BatFile,'wt',encoding='utf-8').write(BatCMD)
        MES = f"RunClassfier command is written to {run_log}"
        MPLOGGER_TCFMain.logW(MES, logFile="TCFMain.log", printOnScreen=False)
        _display_model_command(BatCMD, run_log, background=args.train == True)
        ClearOldTestResFile(BertDatasetSubDir=BertDatasetSubDir,outputDir=outputDir,testResFile=testResFile)


        #開始執行AI運算。
        if "windows" in platform.system().lower():
            os.system(WindowsAnacondaPromptCMD)
        else:
            os.system(f"chmod 700 {BatFile}")
            BatFile = "."+os.path.sep+BatFile
        os.system(BatFile)
        #假設每秒至少推論60個樣本，且至少設為20秒給推論。
        #runclassifier.py的write example速度則假設每秒至少600個
        WatchedTimeBound = max(nTotalTest//60,20)+(nTotalTest)//500


    elif args.ModelType in ["PytorchXLM","PytorchRBTL3"]:
        #BatCMD = f"python {BertClassfierPath}/TextClassification_XLM.py"
        BatCMD = f"python {BertClassfierPath}/TextClassification_transformers.py"
        if args.train == True:
            BatCMD += " -tr True"
        if args.test == True:
            BatCMD += " -ts True"
        BatCMD += f" -mdlDir {outputDir} -BertDataDir {BertDatasetSubDir} -mdlType {args.ModelType} -ZeroShot {args.ActiveHTCZeroshot} "
        #BatCMD += "> RunClassfier.log 2>&1 & \n\n" #背景作業
        run_log = os.path.join(BertDatasetSubDir, "logs", "RunClassfier.log")
        BatCMD += f'> "{run_log}" 2>&1'
        #如果是訓練模式，因枆時甚長，無需計算各階段時間，則採背景作業。
        if args.train == True:
            BatCMD += " &"
        BatCMD += " \n\n"
        MES = f"RunClassfier command is written to {run_log}"
        MPLOGGER_TCFMain.logW(MES, logFile="TCFMain.log", printOnScreen=False)
        _display_model_command(BatCMD, run_log, background=args.train == True)
        ClearOldTestResFile(BertDatasetSubDir=BertDatasetSubDir,outputDir=outputDir,testResFile=testResFile)
        try:
            os.system(BatCMD)
        except Exception as e:
            warning(f"RunClassfier command failed: {e}")
        #raise Exception
        #if TestAfterConvert == True:
            #os.system(f"python TextClassification_XLM_Pred.py -mdlDir {outputDir}")
        WatchedTimeBound = 6000

    key_values("Prediction result files", [("testResFile", summarize_sequence(testResFile, limit=3))])

    #WatchedTimeBound = 6000
    #如果是TF15Bert，將預測完的輸出結果移至資料集目錄。
    if args.test == True:
        for filename in testResFile:
            #if args.ModelType == "TF15Bert":
                #WatchedFN = os.path.join(outputDir, filename)
            WatchedFN = filename
            WaitUntilFileIsStable(
                WatchedFN,WatchedTimeBound=WatchedTimeBound)
        #stage_time_cost.append((f"AI Model Prediction",f"{time.time()-stage_start_time:.2f}"))
        #stage_start_time = time.time()
        if args.ModelType in ["TF15Bert"]:
            for filename in testResFile:
                #src = filename
                des = os.path.join(
                    BertDatasetSubDir, getFNFromFullPath(filename))
                shutil.move(filename,des)


        #還原使用的output模型目錄名稱，以釋放此目錄使用權。
        if args.ModelType in ["TF15Bert"]:
            #shutil.move(using_outputDir,original_outputDir)
            os.rename(using_outputDir,original_outputDir)
    if args.train == True:
        MES = "Start to train model in the background."
        NewBertDatasetSubDir = BertDatasetSubDir
        #exit_program()
        #NewBertDatasetSubDir = BertDatasetSubDir.replace(
        #    "_is_running_RunClassfier","_rdy_for_Predict")
        #1
    elif args.test == True:
        #將目錄更名，以供下階段功能程式抓取。
        NewBertDatasetSubDir = BertDatasetSubDir.replace(
            "_is_running_RunClassfier","_rdy_for_CombineTestResult")
        nTryRename = 0
        while(nTryRename < 5 and not os.path.isdir(NewBertDatasetSubDir)):
            os.rename(BertDatasetSubDir,NewBertDatasetSubDir)
            nTryRename += 1
            time.sleep(2)
        stage_done("RunClassfier")
        MES = f"RunClassfier is finished. Rename {BertDatasetSubDir} as {NewBertDatasetSubDir}"
        key_values("RunClassfier handoff", [("from", BertDatasetSubDir), ("to", NewBertDatasetSubDir)])
    MPLOGGER_TCFMain = MPlogger(logSubDir=f"{NewBertDatasetSubDir}/logs",logFile="TCFMain.log")
    MPLOGGER_TCFMain.logW(MES, printOnScreen=False)
    #print("finish runngi RunCF, wait for 100 secs")
    #time.sleep(100)
