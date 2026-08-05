from PackageImport import PackageImporter
PackageImporter.proc()
import os
import sqlite3 as lite
import shutil
from utils.df_utils import dfFromSQLite3
from utils.utilities import BackUp
from utils.utilities import OSWALK
from utils.utilities import MKDIR
from utils.utilities import timeNow
from utils.utilities import getFileModTime
from utils.utilities import getMFNFromFN
from utils.utilities import getFileDirFromFN
from utils.utilities import hash
from utils.utilities import textReader
from utils.utilities import TextNormalizer
from utils.utilities import removekey
from utils.MP_utils import MPlogger
from utils.utilities import fileNameNormalizer

from utils.DataConverter_utils import getSrcFromFileName

from ClassesTree.Label_utils import getLabelsFromOSWALK
from ClassesTree.Label_utils import getLabelsFromFileName
from ClassesTree.Label_utils import LabelsStringReader
from ClassesTree.Label_utils import LabelNormalizer
from ClassesTree.Label_utils import LabelsQuerent
from ClassesTree.Label_utils import FilePathLabelsPurifier

def getDBLabels(sql3cursor=None,
                Table = "Corpus", 
                LabelCol = "topics", 
                HashCol = "ArticleHash", 
                HashVal = "",
                FilePathCol = "FilePath",
                FilePath = ""):
    if sql3cursor == None:
        sql3cursor = lite.connect(sql3File)
    return LabelsQuerent.proc(sql3cursor=sql3cursor,
                              Table=Table,
                              LabelCol=LabelCol,
                              HashCol=HashCol,
                              HashVal=HashVal,
                              FilePathCol=FilePathCol,
                              FilePath=FilePath)

CleanLabelsInPath = False
#TopicTextCrawlerROOT = "../TopicTextCrawler/"
TopicTextCrawlerROOT = "../../AIData/text-category-profiler-data/"

ROOTPATHList = [
    "C_GoogleSearch",
    "Books",
    "../===DRNData",
    "C_wikisourceSearch",
    "C_wikisourcePortal",
    #"SQLite_Test_Corpus"
    ]
ROOTPATHList = [TopicTextCrawlerROOT+x for x in ROOTPATHList]
ROOTPATHList = [fileNameNormalizer.proc(x) for x in ROOTPATHList]

LabelList = getLabelsFromOSWALK(ROOTPATHList)
print("LabelList", LabelList)

sql3File = "Books_Metadata.sql3"
sql3File = sql3File.replace(".sql3","_CLIP_{}.sql3".format(CleanLabelsInPath))
tableList = ["Corpus"]
CorpusTableName = "Corpus"
ColumnsTypeString ='''
    ArticleHash CHAR(40) NOT NULL,
    title VARCHAR(400) NOT NULL,
    topics VARCHAR(400),
    authors VARCHAR(400), 
    FilePath VARCHAR(500) NOT NULL,
    url VARCHAR(400),
    DLTime SMALLDATETIME,
    ImportTime SMALLDATETIME,
    keywords VARCHAR(400),
    description VARCHAR(400),
    SrcType VARCHAR(50),
    Src VARCHAR(50),
    FileDir VARCHAR(400) NOT NULL,
    Existing BOOLEAN,
    Length INT,
    Context VARCHAR(5000000),
    PRIMARY KEY (FilePath)
    '''
if os.path.isfile(sql3File):
    BackUp(sql3File)
                
conn = lite.connect(sql3File,timeout=30)
sql3FileTables = list(conn.execute("SELECT name FROM sqlite_master WHERE type='table';"))
for TableName in tableList:
    if TableName not in sql3FileTables:
        create_table = "CREATE TABLE IF NOT EXISTS {} ({});".format(
            TableName, ColumnsTypeString)
        conn.execute(create_table)
        for col in ["FilePath","FileDir", "ArticleHash"]:
            createIndex = 'CREATE INDEX IF NOT EXISTS {} ON {}({});'.format(
                col+"_Index",TableName,col)
            conn.execute(createIndex)        

df = dfFromSQLite3(sql3File,tableList = ["Corpus"])
#偵測FilePath路徑之檔案是否確實存在，如果不存在，將"Existing"欄位標註為"False"
#檢查FilePath路徑之檔案的修改時間是否與記錄相同，如果不同，進行更新
#DataFrame物件查詢值跟修改耗費資料及時間，直接從資料庫查詢取值。
nMOD = 0
file_query = 'SELECT FilePath FROM {}'.format(CorpusTableName)
DBFileList = conn.execute(file_query).fetchall()
DBFileList = [fileNameNormalizer.proc(fileName=x[0]) for x in DBFileList] #x is a tuple of single element
for i,file in enumerate(DBFileList):
#for i,file in enumerate(df["FilePath"]):
    row_Mod = False
    for attrPair in [["Existing", os.path.isfile(file)],
                      ["DLTime", getFileModTime(file)],
                      ["FileDir", getFileDirFromFN(file)],
                      #["ImportTime", timeNow(FMT = "%Y-%m-%d %H:%M:%S")]
                      ]:
        dfCol = attrPair[0]
        attrExactVal = attrPair[1]
        #DBVal = df.loc[df["FilePath"]==file][dfCol].iloc[0]
        query = 'SELECT {} FROM {} WHERE FilePath=?'.format(
            dfCol, CorpusTableName)
        DBVal = conn.execute(query, [file]).fetchone()[0]
        #不是同樣的布林值且轉換為字串後不是同樣字串
        if attrExactVal != DBVal and str(attrExactVal) != str(DBVal):
            #df.loc[df["FilePath"]==file, dfCol] = attrExactVal
            update_dict = 'UPDATE {} SET {}=? AND ImportTime=? WHERE FilePath=?;'.format(
                CorpusTableName,dfCol)
            TN = timeNow(FMT = "%Y-%m-%d %H:%M:%S")
            conn.execute(update_dict, [attrExactVal, TN, file])
            if row_Mod == False:
                nMOD += 1
                row_Mod = True
    if nMOD%1000==999:
        conn.commit()
print("There are totally {} rows modified.".format(nMOD))
conn.commit()

#將所有檔案的標籤一次讀入，存為字典變數topicsDict
topicsDict = {}
tpcs_query = 'SELECT FilePath,topics FROM {}'.format(CorpusTableName)
for FP, tpcs in conn.execute(tpcs_query).fetchall():
    topicsDict[FP] = LabelsStringReader.proc(LabelsString=tpcs)

#偵測是否有不在資料庫內的資料，有的話，將其加入資料庫。
nMOD = 0
for ROOTPATH in ROOTPATHList:
    for i,file in enumerate(OSWALK(ROOTPATH, Extension="txt")):
        file = fileNameNormalizer.proc(fileName=file)
        if file not in DBFileList:
            if nMOD == 1:
                print("Found new data and adding, the first 10 items as the following:")
            if nMOD < 10:
                print("file {} is not in SQLite DB and Adding the data".format(
                    file))
            #print("file",file)
            #如果CleanLabelsInPath == True，
            #將檔案路徑中的標籤去除後，搬移檔案，並以新路徑入庫。
            if CleanLabelsInPath == True:
                desFile = FilePathLabelsPurifier.proc(file)
            else:
                desFile = file
            AttrsDict = {}
            #取得資料庫中的標籤與路徑標籤整合做為入庫標籤。
            #使用getDBLabels呼叫外部LabelsQuerent SQLite標籤查詢器時，會產生資料庫
            #存取鎖定問題，故暫不使用此外部函數呼叫方法。之後如果用MYSQL時，可採用此即時
            #查詢法。目前先將所有檔案的標籤一次讀入，存為字典變數topicsDict，以供運用。
            #DBLabels = LabelNormalizer.proc(getDBLabels(FilePath=desFile))
            if desFile in topicsDict.keys():
                DBLabels = topicsDict[desFile]
            else:
                DBLabels = []
            AttrsDict["topics"] = str(LabelNormalizer.proc(
                DBLabels+getLabelsFromFileName(file)))
            #print(file, AttrsDict["topics"])
            
            if file != desFile:
                MKDIR(desFile.rpartition("/")[0])
                shutil.move(file, desFile)
                MES = "The file {} has been moved to {}.".format(file,desFile)
                file = desFile 
                
            AttrsDict["FilePath"] = file
            AttrsDict["FileDir"] = getFileDirFromFN(file)
            AttrsDict["Context"] = TextNormalizer().proc(textReader(file).run())
            AttrsDict["Length"] = len(AttrsDict["Context"])
            if "Context" in AttrsDict.keys():
                AttrsDict["ArticleHash"] = hash(AttrsDict["Context"], "sha1")
            else:
                AttrsDict["ArticleHash"] = hash(textReader(file).run(), "sha1")
            AttrsDict["title"] = getMFNFromFN(file)
            AttrsDict["SrcType"], AttrsDict["Src"] = getSrcFromFileName(file, LabelList)
            AttrsDict["Existing"] = True
            AttrsDict["DLTime"] = getFileModTime(file)
            AttrsDict["ImportTime"] = timeNow(FMT = "%Y-%m-%d %H:%M:%S")
            #print(type("getFileModTime(file)"),type(getFileModTime(file)))
            for key in AttrsDict.keys():
                if type(AttrsDict[key]) == str:
                    AttrsDict[key] = AttrsDict[key].replace('\"',"\'").replace("\\","/")
                elif  type(AttrsDict[key]) == list:
                    AttrsDict[key] = [x.replace('\"',"\'").replace("\\","/") for x in AttrsDict[key]]
            
            Cols, Values = zip(*AttrsDict.items())
            ColumnsString = ",".join(Cols)
            ValuesString = ",".join(['"{}"'.format(x) for x in Values])
            KeyValues = list(AttrsDict.items())
            
            ValuesString2 = ','.join(['{}=?'.format(x) for x in Cols])
            #update_dict = 'UPDATE {} SET {} WHERE FilePath= {};'.format(
                #TableName, ValuesString, '"'+AttrsDict["FilePath"]+'"')
            #insert_dict = 'INSERT INTO {} ({}) VALUES ({})'.format(
                    #TableName, ColumnsString, ValuesString)
            #insert_dict = 'INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {};'.format(
                    #TableName, ColumnsString, ValuesString, ValuesString2) #For MYSQL
            #insert_dict = 'INSERT OR IGNORE INTO {} ({}) VALUES ({}) UPDATE {} SET {} WHERE FilePath= {};'.format(
                    #TableName, ColumnsString, ValuesString, TableName, ValuesString2, '"'+AttrsDict["FilePath"]+'"')
            insert_dict = 'INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {} WHERE FilePath= {};'.format(
                    TableName, ColumnsString, ValuesString, "FilePath", ValuesString2, '"'+AttrsDict["FilePath"]+'"')
    
            conn.execute(insert_dict, Values)
            try:
                nMOD += 1
                conn.execute(insert_dict, Values)
            except Exception as ex:
                MPlogger.logW("="*50)
                MPlogger.logW(ex)
                MPlogger.logW(insert_dict)
                pass
            if nMOD % 1000 == 999:
                conn.commit()

print("There are totally {} inserted or updated rows.".format(nMOD))
conn.commit()
conn.close()