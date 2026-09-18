#SDSMS
#python TCFMain.py --WeiTechworkIDPath D:\shared\rawData\AIPool_SDSMS\ProcLink\AutoBertClassify --WeiTechWorkPoolPATH D:\shared\rawData\AIPool_SDSMS\WorkPool -p 8099999 -TRVHost False -task SDSMS_Prediction
#python TCFMain.py --WeiTechworkIDPath /mntCZJ/rawData/AIPool_SDSMS/ProcLink/AutoBertClassify --WeiTechWorkPoolPATH /mntCZJ/rawData/AIPool_SDSMS/WorkPool -p 8099999 -TRVHost False -task SDSMS_Prediction
#WeiTech
#python TCFMain.py --WeiTechworkIDPath D:\shared\rawData\ABT\ProcLink\AutoBertClassify --WeiTechWorkPoolPATH D:\shared\TopicClassification\WTWorkPool -p 8099999 -TRVHost False


from TCF_Params.TCFParameters import setArguments
from TCF_Params.TCFParameters import WorkPoolROOT
from TCF_Params.TCFParameters import BertClassfierPath
from TCF_Params.TCFParameters import FinalOfferedOutputFNrePatList

import setproctitle
import os
import platform
#import csv
import time
import json
import subprocess

from text_category_profiler.execution.process import (
    LegacyShellProcessRunner,
    RootFailFastPolicy,
)

#import plotly.io as pio; pio.renderers.default='notebook'
#from zhconv import convert


def run_stage_command(CMD, stage_name, runner=None):
    if runner is None:
        runner = LegacyShellProcessRunner(run_process=subprocess.run)
    completed = runner.execute(CMD)
    return RootFailFastPolicy(failure_reporter=stage_failed).check(
        completed, stage_name, CMD
    )

#import GPUtil

from text_category_profiler.core.utilities import OSWALK
from text_category_profiler.core.utilities import MKDIR
from text_category_profiler.core.conformer import HybridConformer
#from utilities import ShowElapsedTime
from text_category_profiler.pipeline.TCF_utils import BackupAIPredictResultAndDelTempFile
#from text_category_profiler.pipeline.TCF_utils import ExportDFAllResult
from text_category_profiler.pipeline.TCF_utils import convert_to_args_str
from text_category_profiler.pipeline.TCF_utils import datasetDirOutputDirPickers
from text_category_profiler.pipeline.commands import (
    classifier_command,
    combine_command,
    dataset_command,
    visualization_command,
)
from text_category_profiler.pipeline.configuration import PipelineContext
from text_category_profiler.pipeline.orchestrator import PipelineOrchestrator
from text_category_profiler.pipeline.workpool import (
    DeliveryManager,
    WorkPoolManager,
    WorkPoolPlan,
)
from text_category_profiler.filesystem import LegacyFileSystem

from text_category_profiler.pipeline.DataConverter_utils import CheckDatasetFiles
from text_category_profiler.pipeline.DataConverter_utils import RawAndPredictionMerger
#from utilities import hash

from text_category_profiler.concurrency.MP_utils import MPlogger
#from text_category_profiler.visualization.Dash_utils import LevelDVisProcessor
#from utilities_RAND import LoadTree
#from utilities_RAND import RANDLoader

from text_category_profiler.core.utilities import ShowElapsedTime
from text_category_profiler.core.utilities import exit_program
from text_category_profiler.core.utilities import chownPath
from text_category_profiler.core.log_display import info
from text_category_profiler.core.log_display import print_args_summary
from text_category_profiler.core.log_display import print_command
from text_category_profiler.core.log_display import stage_banner
from text_category_profiler.core.log_display import stage_done
from text_category_profiler.core.log_display import stage_failed
from text_category_profiler.core.log_display import warning

#from text_category_profiler.Tika_pdf_to_txt import ExtractTxt

#將環境變數執行python所需之"."替換成r".\"，
#否則import tulip時，在__init__.py的Line 31之os.add_dll_directory(".")會報錯中斷。
os.environ['PATH']=os.environ['PATH'].replace(";.;",r";\.;")


def DataConvert(args,exeTimeDict=dict()):
    stage_start_time = time.time()
    stage_banner("DataConverter", detail="整理輸入資料並產生 train/dev/test handoff 檔案")
    print_args_summary(args)
    #如果有設定WeiTechworkIDPath和WeiTechWorkPoolPATH，則抓取workID，
    #並續於DataConverter將該workID相關dataset_total_with_filename_FixedTest.sql3和test3.sql3拷貝到WorkPool
    #print("start to find WeiTechworkIDPath")
    if args.WeiTechworkIDPath != "" and args.WeiTechWorkPoolPATH !="":
        context = PipelineContext(
            args=args, root_paths=(),
            final_output_patterns=tuple(FinalOfferedOutputFNrePatList),
            run_mode="legacy",
        )
        manager = WorkPoolManager(
            WorkPoolPlan.from_context(context, workpool_root=WorkPoolROOT),
            _legacy_filesystem(),
            warning=warning,
            info=lambda message: info(message, icon="📌"),
        )
        args.WeiTechworkID = manager.acquire()
    
    CMD = dataset_command(args, args_renderer=convert_to_args_str).render_shell()
    ShowElapsedTime(exeTimeDict["start"])
    print_command(CMD, label="DataConverter command")
    run_stage_command(CMD, "DataConverter")
    
    BertDatasetSubDir,outputDir = datasetDirOutputDirPickers(
        args=args,rdy_for_stage="RunClassfier").proc()
    #檢查train.tsv、test.tsv、dev.tsv狀態，如果都沒有的話，有可能代表無資料成功轉換，中止程式。
    #print("In DCStage, BertDatasetSubDir",BertDatasetSubDir)
    if any(CheckDatasetFiles(BertDatasetSubDir).values()) == False:
        MES = f"There is no train.tsv,dev.tsv,test.tsv found in {BertDatasetSubDir}. It might be something wrong."
        warning(MES)
        raise Exception
    exeTimeDict["DataConverter"] = f"{time.time()-stage_start_time:.2f}"
    stage_done("DataConverter", time.time()-stage_start_time)

def RunClassfier(args,exeTimeDict=dict()):
    stage_start_time = time.time()
    stage_banner("RunClassfier", detail="執行模型訓練或推論")
    print_args_summary(args)
    CMD = classifier_command(
        args, BertClassfierPath, args_renderer=convert_to_args_str
    ).render_shell()
    #stage_start_time = time.time()
    ShowElapsedTime(exeTimeDict["start"])
    print_command(CMD, label="RunClassfier command")
    run_stage_command(CMD, "RunClassfier")
    if args.train == True:
        info("Start to train model in the background.", icon="🚀")
        exit_program()
    exeTimeDict["RunClassfier"] = f"{time.time()-stage_start_time:.2f}"
    stage_done("RunClassfier", time.time()-stage_start_time)

def CombineTestResult(args,exeTimeDict=dict()):
    stage_start_time = time.time()
    #if args.test == True:
    stage_banner("CombineTestResult", detail="合併預測結果與原始文本索引")
    #print("Start to run count_test_accuracy.py")
    print_args_summary(args)
    CMD = combine_command(
        args, BertClassfierPath, args_renderer=convert_to_args_str
    ).render_shell()
    ShowElapsedTime(exeTimeDict["start"])
    print_command(CMD, label="CombineTestResult command")
    run_stage_command(CMD, "CombineTestResult")

    exeTimeDict["Combine AI Result and TextPieces"] = f"{time.time()-stage_start_time:.2f}"
    stage_done("CombineTestResult", time.time()-stage_start_time)

def TestResultVis(args,exeTimeDict=dict()):
    command = visualization_command(
        args, BertClassfierPath, args_renderer=convert_to_args_str
    )
    CMD = command.render_shell()
    stage_start_time = time.time()
    stage_banner("Test_result_Vis", detail="產生結果分析與視覺化網頁資料")
    print_args_summary(args)
    ShowElapsedTime(exeTimeDict["start"])
    print_command(CMD, label="TestResultVis command")
    run_stage_command(CMD, "Test_result_Vis")
    if args.TRVWebHost == False:
        BertDatasetSubDir,outputDir = datasetDirOutputDirPickers(
            args=args,rdy_for_stage="Spike").proc()
        try:
            nDict = json.load(open(os.path.join(
                BertDatasetSubDir,"nDict.json"),encoding='utf-8'))
        except Exception as e:
            MES = f"When load nDict.json, the following error occurs:{e}"
            warning(MES)
            nDict = None
        exeTimeDict["Compute Article Summary"] = f"{time.time()-stage_start_time:.2f}"
        MES = f"Each stage time cost for {BertDatasetSubDir} with pieces count {nDict} is \n {exeTimeDict}"
        MPlogger(logSubDir=f"{BertDatasetSubDir}/logs").logW(MES,logFile="stage_time_cost.log")

def BackupAndClean(args):
    #if args.ExportDFAll == True:
        #print("Start to export good article terms in DFPreambleCols_df_ALL.sql3 to combined SQLite databases.")
        #ExportDFAllResult()
    BertDatasetSubDir,outputDir = datasetDirOutputDirPickers(
        args=args,rdy_for_stage="Spike").proc()
    if args.RemoveBertDataDir == True:
        stage_banner("BackupAndClean", detail="備份預測結果並清理暫存資料")
        info("args.RemoveBertDataDir is True, Running BackupAIPredictResultAndDelTempFile", icon="🧹")
        info(f"BertDatasetSubDir: {BertDatasetSubDir}", icon="📁")
    context = PipelineContext(
        args=args, root_paths=(),
        final_output_patterns=tuple(FinalOfferedOutputFNrePatList),
        run_mode="legacy",
    )
    DeliveryManager(
        WorkPoolPlan.from_context(context, workpool_root=WorkPoolROOT),
        _legacy_filesystem(),
        output_logger=lambda message: MPlogger(logSubDir="logs").logW(
            message, logFile="WeiTechOutputDF.log"
        ),
    ).backup_and_complete(BertDatasetSubDir)


def _legacy_filesystem():
    return LegacyFileSystem(
        make_directory=lambda path: MKDIR(path),
        walk=lambda path: OSWALK(path),
        chown=lambda path: chownPath(path),
        backup=lambda **kwargs: BackupAIPredictResultAndDelTempFile(**kwargs),
        platform_name=lambda: platform.system(),
    )

def ArticleAnalysis(args,exeTimeDict=dict()):
    #綜合輸入資料及推論結果，製作資料庫，以供檢索
    CombineTestResult(args,exeTimeDict=exeTimeDict)
    #建置可視化研閱界面
    TestResultVis(args,exeTimeDict=exeTimeDict)
    #合併資料與推論結果
    if args.task in ["SDSMS","SDSMS_Prediction"]:
        RawAndPredictionMerger(args=args).proc()
    #備份AI分析結果，並清除過程檔案
    BackupAndClean(args)

def main(argv=None):
#WT測試指令:python TCFMain.py -WTworkIDPath rawData/ABT/ProcLink/AutoBertClassify -WTWorkPoolPath WTWorkPool -TRVHost False
    exeTimeDict = dict()
    exeTimeDict["start"] = time.time()
#%%初始化，智慧化參數設定
    args = setArguments() if argv is None else setArguments(argv)
    setproctitle.setproctitle(f'TCFMain{args.ExecutionTime[4:]}')
    HybridConformer(cpuUsageThreshold=90).proc()

    context = PipelineContext(
        args=args,
        root_paths=(),
        final_output_patterns=tuple(FinalOfferedOutputFNrePatList),
        run_mode="legacy",
    )
    orchestrator = PipelineOrchestrator(
        context,
        convert=lambda: DataConvert(args, exeTimeDict=exeTimeDict),
        classify=lambda: RunClassfier(args, exeTimeDict=exeTimeDict),
        combine=lambda: CombineTestResult(args, exeTimeDict=exeTimeDict),
        visualize=lambda: TestResultVis(args, exeTimeDict=exeTimeDict),
        merge=lambda: RawAndPredictionMerger(args=args).proc(),
        deliver=lambda: BackupAndClean(args),
    )
    orchestrator.run()

    info(f"各階段耗時摘要: {exeTimeDict}", icon="⏱️")


if __name__ == '__main__':
    main()
