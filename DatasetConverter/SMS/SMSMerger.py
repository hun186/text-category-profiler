import os
import sys
from pathlib import Path

if __name__ == "__main__":
    REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))

import datetime
from text_category_profiler.data.df_utils import dfOutputer
from text_category_profiler.data.df_utils import dfFromSQLite3
from text_category_profiler.data.df_utils import CSVtodf
from text_category_profiler.core.utilities import getMFNFromFN
from text_category_profiler.core.utilities import removeStrPrefix
from text_category_profiler.core.utilities import ConvertTimeStrFMT
from BertScript.ClassTable import ClassTable

CPBatFN = "CPAntCSV.bat"
testResSQL = "test_results_verification.sql3"
AnnotRawFN = "MERGED-20231024-20240306All.csv"
InputFMT = "%Y-%m-%d %H:%M:%S"
OutputFMT = "%Y-%m-%d"


def main():
    if os.path.isfile(CPBatFN):
        os.system(CPBatFN)

    testResdf = dfFromSQLite3(testResSQL)
    testResDict = dict(zip(testResdf.text,testResdf.pred_Type))
    del testResdf
    OUTPUTMAIN = getMFNFromFN(AnnotRawFN)+"_Combined"
    df = CSVtodf(InputCSV = AnnotRawFN,sep=",",header=True,error_bad_lines=True)
    df["推論類別"] = df.apply(lambda x:testResDict.get(x.SmsContent,""),axis=1)
    df["日期"] = df.apply(lambda x:ConvertTimeStrFMT(
        x.ItcDate,srcFMTCands=[InputFMT],desFMT=OutputFMT),axis=1)
    for col in ["SmsContentNo","標註類別"]:
        df[col] = df[col].fillna(value="")

    for col in ["標註類別","推論類別"]:
        df[col] = df.apply(lambda x:ClassTable.get(
            getattr(x,col),dict()).get("CT",getattr(x,col)),axis=1)
        df[col] = df.apply(lambda x:removeStrPrefix(
            str(getattr(x,col)),"漁業簡訊-"),axis=1)
    df["推論正確"] = df["標註類別"] == df["推論類別"]
    df = df.sort_values(["ItcDate","Address1","Address2"])
    print("df",df)
    dfOutputer(df,OUTPUTMAIN,OutputFormat=["tsv"],TSVTextAdapter=True).run()


if __name__ == "__main__":
    main()
