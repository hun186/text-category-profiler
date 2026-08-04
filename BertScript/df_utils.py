import numpy as np
import multiprocessing as mp
import pandas as pd
import csv
import sqlite3 as lite
import xlsxwriter
import time
from collections import Counter
#import pyodbc
#import pymysql
#import charts
from MP_utils import MPlogger
from MP_utils import multicoreJob
from utilities import hash
from utilities import ShowElapsedTime


'''
def parallelize_dataframe(df, func, n_cores=4):
    df_split = np.array_split(df, n_cores)
    pool = mp.Pool(n_cores)
    df = pd.concat(pool.map(func, df_split))
    pool.close()
    pool.join()
    return df
'''

def dfToXLS(df, OutputFN, excelindex=True, encoding = 'utf-8'):
    #df.to_excel(OutputFN, engine = 'openpyxl', index = excelindex, encoding = 'utf-8')
    df.to_excel(OutputFN, engine = 'xlsxwriter', index = excelindex, encoding = 'utf-8')
    
def dfToTSV(df, OutputFN):
    #df.dropna(how="all", inplace=True, axis=1)
    #df.dropna(how="any", inplace=True, axis=1)
    df.to_csv(
        OutputFN, sep = '\t', index = False,
        quoting=csv.QUOTE_NONE, quotechar="", escapechar="\\",
        header = False, encoding="utf-8")

def dfToSQL(SQLname, df, SavingDfColumns = []):
    #SavingDfColumns = ['Column Name A','Column Name B','Column Name C']
    if len(SavingDfColumns) == 0:
        SavingDfColumns = df.columns.values
    #連結sqlite資料庫
    cnx = lite.connect(SQLname)
    
    #選取dataframe 要寫入的欄位名稱
    #欄位名稱需與資料庫的欄位名稱一樣 才有辦法對照寫入
    sql_df=df.loc[:,SavingDfColumns]
    
    #if_exists 選擇 replace，若是Daily_Record 這個 table 已存在資料庫
    #將Daily_Record 表刪除並重新創建 寫入 sql_df 的資料
    sql_df.to_sql(name='sampleSrc', con=cnx, if_exists='replace')
    #創造index，以提升讀取速度。
    createIndex = 'CREATE INDEX "text_Index" ON "sampleSrc"("text");'
    cnx.execute(createIndex)

class dfOutputer:
    def __init__(self, df, OMFN):
        self.df = df
        self.OMFN = OMFN
    def show(self):
        print("OMFN is {}".format(self.OMFN))
    
    def run(self):
        try:
            dfToTSV(self.df, self.OMFN+'.tsv')
        except Exception as ex:
            print(ex)
            MPlogger.logW(ex)
        #dfToTSV(self.df, self.OMFN+'.tsv')
        #將轉換成完成之資料集df存入SQL資料庫，以加速存取。
        dfToSQL(self.OMFN+".sql3",
                self.df,
                self.df.columns.values)
        #Excel檔案最大列數限制 1048576
        if self.df.shape[0] <= 1048576:
            dfToXLS(self.df, self.OMFN+'.xlsx')


def TSVtodf(InputCSV, sep = ','):
    # Import CSV
    df = pd.read_csv(
        InputCSV, sep = sep,
        quoting=csv.QUOTE_NONE, quotechar="", escapechar="\\",
        encoding="utf-8", header = None)
    return df

def dftoMySQL(df, db_settings=None, TableName = 'Samples'):
    db_settings = {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "abc123",
        "db": "test",
        "charset": "utf8mb4"
    }
    Cols = ['InLabel', 'OutLabel', 'texts','fileSrc', 'DataSrcType', 'DataSrc']
    df.columns = Cols
    for col in Cols:
        df[col] = getattr(df,col).astype(str)
    for col in df.columns:
        df[col] = df[col].apply(
            lambda x:
                x.replace('\"',"\'") if isinstance(x, str) else x)
    
    #如果text結尾為 \，補上空白，以免\與字分隔符"結合，
    #造成SQL將 \"誤判為"，而視為text字串的一部份，
    #因而導致SQL語法錯誤。
    df['texts'] = df['texts'].apply(
        lambda x: x+x.endswith('\\')*' ')
    df['SampleID'] = df['texts'].apply(
        lambda x: hash(x.encode('utf-8'), 'sha1'))
    Cols = ['SampleID', 'InLabel', 'OutLabel',
            'texts','fileSrc', 'DataSrcType', 'DataSrc']
    df = df[Cols]
    ColumnsString = ",".join(Cols)
    print("ColumnsString",ColumnsString)
    ColumnsTypeString ='''
        SampleID CHAR(40) NOT NULL,
        InLabel VARCHAR(50) NOT NULL,
        OutLabel VARCHAR(50) NOT NULL,
        texts VARCHAR(2048) NOT NULL,
        fileSrc VARCHAR(400) NOT NULL,
        DataSrcType VARCHAR(200) NOT NULL,
        DataSrc VARCHAR(200) NOT NULL,
        PRIMARY KEY (SampleID)
        '''
    # 建立Connection物件
    conn = pymysql.connect(**db_settings)
    cursor = conn.cursor()
    try:
        # Create Table
        create_table = "CREATE TABLE IF NOT EXISTS {} ({})".format(
            TableName, ColumnsTypeString)
        cursor.execute(create_table)
        createIndex = 'CREATE INDEX {} ON {}({});'.format(
            "SampleID_Index",TableName,"SampleID")
        cursor.execute(createIndex)
        createIndex = 'CREATE INDEX {} ON {}({});'.format(
            "texts_Index",TableName,"texts")
        cursor.execute(createIndex)
        
    except Exception as ex:
        print(ex)
    
    #def dfInserter(df):
    i = 0
    for row in df.itertuples():
        if i % 1000 == 0:
            MES = "{} samples have been imported.".format(i)
            print(MES)
            MPlogger.logW(MES)
            conn.commit()
        Attrs = list(row[1:]) #捨去index number
        ValuesString = ",".join(
            ["{}{}{}".format('"',x,'"') for x in Attrs])
        insert_dict = 'INSERT INTO {} ({}) VALUES ({})'.format(
                TableName, ColumnsString, ValuesString)
        try:
            cursor.execute(insert_dict)
        except Exception as ex:
            MPlogger.logW("="*50)
            MPlogger.logW(row)
            MPlogger.logW(ex)
            MPlogger.logW(insert_dict)
            pass
        i += 1
    MES = "{} samples have been imported.".format(i)
    print(MES)
    MPlogger.logW(MES)
    conn.commit()
    return pd.DataFrame()

    
def dfFromSQLite3(sql3File,tableList = None, columnList = None):
    # Read sqlite query results into a pandas DataFrame
    conn = lite.connect(sql3File)
    if type(tableList) == str:
        tableList = [tableList]
    if tableList == None:
        tableList = list(conn.execute("SELECT name FROM sqlite_master WHERE type='table';"))
        tableList = [x[0] for x in tableList]
    if columnList == None:
        ColumnStrings = "*"
    else:
        ColumnStrings = ','.join(columnList)
    print("tableList",tableList)
    df = pd.DataFrame()
    print("Start to load the sql3 file {}.".format(sql3File))
    for name in tableList:
        print("Loading the table {}".format(name))
        #df = pd.read_sql_query("SELECT * FROM {}".format(table), conn)
        
        query = "SELECT {} FROM {}".format(ColumnStrings, name)
        df = pd.concat(
            [df,pd.read_sql_query(query, conn)])
    
    # Verify that result of SQL query is stored in the dataframe
    #print(df.head())
    conn.close()
    return df


