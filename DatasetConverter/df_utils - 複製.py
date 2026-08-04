import numpy as np
import multiprocessing as mp
import pandas as pd
import csv
import sqlite3 as lite
import xlsxwriter
import pyodbc
import pymysql
#import charts
from MP_utils import MPlogger

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
        dfToTSV(self.df, self.OMFN+'.tsv')
        #將轉換成完成之資料集df存入SQL資料庫，以加速存取。
        dfToSQL(self.OMFN+".sql3",
                self.df,
                self.df.columns.values)
        dfToXLS(self.df, self.OMFN+'.xlsx')


def TSV_to_MySQL(InputCSV, db_settings, CSVsep = ',', TableName = 'testTable'):
    # Import CSV
    df = pd.read_csv (InputCSV, sep = CSVsep, encoding="utf-8", header = None)
    df_to_MySQL(df, db_settings = db_settings, TableName = TableName)

def df_to_MySQL(df, db_settings, TableName = 'testTable'):
    Cols = ['InLabel', 'OutLabel', 'texts','fileSrc', 'DataSrcType', 'DataSrc']
    df.columns = Cols
    try:
        ColumnsString = ",".join(Cols)
        print("ColumnsString",ColumnsString)
        ColumnsTypeString ='''
            InLabel VARCHAR(50) NOT NULL,
            OutLabel VARCHAR(50) NOT NULL,
            texts VARCHAR(512) NOT NULL,
            fileSrc VARCHAR(400) NOT NULL,
            DataSrcType VARCHAR(200) NOT NULL,
            DataSrc VARCHAR(200) NOT NULL,
            PRIMARY KEY (texts)
            '''
        # 建立Connection物件
        conn = pymysql.connect(**db_settings)
        cursor = conn.cursor()
        # Create Table
        create_table = "CREATE TABLE IF NOT EXISTS {} ({})".format(
            TableName, ColumnsTypeString)
        query = '''
        CREATE TABLE Samples2 (
            InLabel VARCHAR(50) NOT NULL,
            OutLabel VARCHAR(50) NOT NULL,
            texts VARCHAR(512) NOT NULL,
            fileSrc VARCHAR(400) NOT NULL,
            DataSrcType VARCHAR(200) NOT NULL,
            DataSrc VARCHAR(200) NOT NULL,
            PRIMARY KEY (texts)
            );
        '''
        #cursor.execute(query)
        cursor.execute(create_table)
        createIndex = 'CREATE INDEX {} ON {}({});'.format(
            "texts_Index",TableName,"texts")
        cursor.execute(createIndex)
        
    except Exception as ex:
        print(ex)

    i = 0
    for row in df.itertuples():
        Attrs = []
        for x in row[1:]:#捨去index number
            Attrs.append(x.replace('\"',"\'"))
        ValuesString = ",".join(
            ["{}{}{}".format('"',x,'"') for x in Attrs])
        insert_dict = 'INSERT INTO {} ({}) VALUES ({})'.format(
                TableName, ColumnsString, ValuesString)
        #print("="*50)
        #print("query",insert_dict)
        try:
            cursor.execute(insert_dict)
        except Exception as ex:
            #print(ex)
            MPlogger.logW(ex)
            pass
        #print(i)
        if i % 1000 == 0:
            print("{} samples have been imported.".format(i))
            conn.commit()
        i += 1


# 資料庫設定
db_settings = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "abc123",
    "db": "test",
    "charset": "utf8"
}
    
if __name__ == '__main__':
    print("START to import tsv To MySQL.")
    InputTSV = "dataset_total_with_filename.tsv"
    TSV_to_MySQL(InputTSV,db_settings = db_settings,CSVsep = '\t',TableName = 'Samples')
    print("Finished importing tsv To MySQL.")
