import os
from PackageImport import PackageImporter
PackageImporter.proc()
import pandas as pd
import setproctitle
#載入摘要標註目錄參數設定
from DatasetConverter.ConverterParameters_Combiner import SummarizationExcelROOTPATHList
from text_category_profiler.core.utilities import OSWALK
from text_category_profiler.core.utilities import getFNFromFullPath
#DataFrame處理小函式
from text_category_profiler.data.df_utils import dfOutputer
from text_category_profiler.data.df_utils import XLSTodf
#平行化運行小函式
from text_category_profiler.concurrency.MP_utils import multicoreJob
from text_category_profiler.concurrency.MP_utils import MPlogger

if __name__ == '__main__':
    setproctitle.setproctitle(f'SummarizationExcels')
    df = pd.DataFrame()
    for path in SummarizationExcelROOTPATHList:
        for file in OSWALK(path):
            if any([getFNFromFullPath(file).startswith(x) for x in (".~lock","~$")
                    ]
                   ):
                continue
            try:
                print("dealing file",file)
                Partdf = XLSTodf(InputXLS=file, usecols="B:C",
                                 #skiprows=skiprows
                                 )
                Partdf.columns = ["text","OutLabel"]
                df = pd.concat([df, Partdf], ignore_index=True)
            except Exception as e:
                MES = f"{'-'*50}\n When applying SummarizationExcels to {file}, the following error occurs:\n{e}\n"
                MPlogger().logW(MES)
                
    print("df.shape",df.shape)
    df.dropna(inplace=True)
    df.reset_index(inplace=True,drop=True)
    OUTPUTMAIN = os.path.join(os.getcwd(),"SummarizationTrain")
    dfOutputer(df, OUTPUTMAIN, IndexCols=[],
               OutputFormat=["sql"]).run()
    print(f"The combined data has been export to {OUTPUTMAIN}.sql3.")
    os.system("pause")