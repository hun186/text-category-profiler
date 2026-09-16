
import sys

from text_category_profiler.pipeline.configuration import BASE_FINAL_OUTPUT_PATTERNS
from text_category_profiler.pipeline.configuration import activate_pipeline_runtime
from text_category_profiler.pipeline.configuration import build_pipeline_plan

WorkPoolROOT = "WorkPool"
WorkPoolROOT_ArticleComposition = "WorkPoolROOT_ArticleComposition"
#TopicTextCrawlerROOT = "TopicTextCrawler"
TopicTextCrawlerROOT = "../../AIData/text-category-profiler-data/"
DatasetConverterROOT = "DatasetConverter"


ROOTPATHList = []
FinalOfferedOutputFNrePatList = list(BASE_FINAL_OUTPUT_PATTERNS)
_loaded_parser = getattr(
    sys.modules.get("text_category_profiler.pipeline.TCF_utils"),
    "ClassfierOptionParser",
    None,
)
_loaded_clock = getattr(
    sys.modules.get("text_category_profiler.core.utilities"), "timeNow", None
)
_loaded_process_source = getattr(
    sys.modules.get("text_category_profiler.concurrency.MP_utils"),
    "multicoreJob",
    None,
)


def ClassfierOptionParser(argv=None):
    if _loaded_parser is not None:
        return _loaded_parser(argv) if argv is not None else _loaded_parser()
    from text_category_profiler.pipeline.TCF_utils import ClassfierOptionParser as parser
    return parser(argv)


def timeNow():
    if _loaded_clock is not None:
        return _loaded_clock()
    from text_category_profiler.core.utilities import timeNow as current_time
    return current_time()


def multicoreJob():
    if _loaded_process_source is not None:
        return _loaded_process_source()
    from text_category_profiler.concurrency.MP_utils import multicoreJob as source
    return source()


def setArguments(argv=None):
    """Compatibility entrypoint that plans and immediately activates a run."""
    parsed = None

    def parse_legacy_arguments(values):
        nonlocal parsed
        parsed = ClassfierOptionParser(values)
        return parsed

    plan = build_pipeline_plan(
        argv=argv,
        parser=parse_legacy_arguments,
        clock=timeNow,
    )
    context = activate_pipeline_runtime(plan, process_source=multicoreJob)
    ROOTPATHList[:] = context.root_paths
    FinalOfferedOutputFNrePatList[:] = context.final_output_patterns
    from text_category_profiler.core.log_display import print_once
    print_once(
        f"Run in {context.run_mode} Mode, ROOTPATHList is set as {ROOTPATHList}"
    )
    vars(parsed).update(vars(context.args))
    return parsed
'''
if args.task == "SDSMS":
    FinalOfferedOutputFNrePatList.extend(["SDSMS.*"])
    args.ExtractionConverterTask = "SDSMS_Prediction"
'''
#設定Bert分類器訓練程式路徑，以進行資料集相關檔案輸出至該路徑，如果不存在，則暫時設為dataset子目錄存放。
BertClassfierPath = 'BertScript'

#單篇文章用來進行摘要的片數上限
nPiecesToSummaryUPD = 26
