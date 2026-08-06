import os
from PackageImport import PackageImporter
PackageImporter.proc()

import datetime
from utils.data.df_utils import dfOutputer
from utils.data.df_utils import dfFromSQLite3
from utils.data.df_utils import CSVtodf
from utils.core.utilities import getMFNFromFN
from utils.core.utilities import removeStrPrefix
from utils.core.utilities import ConvertTimeStrFMT
from ClassTable import ClassTable

CPBatFN = "CPAntCSV.bat"
if os.path.isfile(CPBatFN):
    os.system(CPBatFN)

testResSQL = "test_results_verification.sql3"
testResdf = dfFromSQLite3(testResSQL)
testResDict = dict(zip(testResdf.text,testResdf.pred_Type))
del testResdf
AnnotRawFN = "MERGED-20231024-20240306All.csv"
OUTPUTMAIN = getMFNFromFN(AnnotRawFN)+"_Combined"
InputFMT = "%Y-%m-%d %H:%M:%S"
OutputFMT = "%Y-%m-%d"
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