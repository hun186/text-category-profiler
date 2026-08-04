from pymongo import MongoClient
import pprint
import datetime as dte
import pytz
import pandas as pd
import sqlite3

def _connect_mongo(host, port, username, password, db):
    """ A util for making a connection to mongo """

    if username and password:
        mongo_uri = 'mongodb://%s:%s@%s:%s/%s' % (username, password, host, port, db)
        conn = MongoClient(mongo_uri)
    else:
        conn = MongoClient(host, port)

    return conn[db]

def Read_Mongo(db='LPNK',
               collection='2013Test', 
               query = None, 
               project = None,
               host = 'localhost', port = 27017, 
               username = None, password = None, 
               no_id = True,):
    """ Read from Mongo and Store into DataFrame """

    # Connect to MongoDB
    db = _connect_mongo(
        host=host, port=port, 
        username=username, password=password, db=db)

    # Make a query to the specific DB and Collection
    cursor = db[collection].find(query, project)

    # Expand the cursor and construct the DataFrame
    df =  pd.DataFrame(list(cursor))

    # Delete the _id
    if no_id and '_id' in df.columns.tolist():
        del df['_id']

    return df

#以字串形式比對時間，印出時段內資料。
def PrintData(collection, TP):
    TimeLen = len(str(TP[0]))
    for x in collection.find():
        if TP[0] <= int(x['Time'][0:TimeLen]) < TP[1]:
            if 'Receiver' not in x.keys():
                x['Receiver'] = ""
            pprint.pprint(','.join([x[key] for key in 
                           ['Sender', 'Receiver', 'Time', 'Length']]))


def AddDatetimeField(collection):
    pacific = pytz.timezone('US/Pacific')
    for x in collection.find():
        if "Datetime" not in x:
            #print(x["Time"])
            #aware_datetime = pacific.localize(
                #dte.datetime.strptime(x["Time"], "%Y%m%d%H%M%S"))
            aware_datetime = dte.datetime.strptime(x["Time"], "%Y%m%d%H%M%S")
            #print("aware_datetime", aware_datetime)
            collection.update_one({
              '_id': x['_id']
            },{
              '$set': {
                'Datetime': aware_datetime
              }
            }, upsert=False)

def ShowDataAttr(collection, attribute):
    for x in collection.find()[:5]:
        print(x[attribute])

def MongoTest():
    #如果無法連線本機server，確認本機server服務有執行，或啓動之：
    #執行 MongoDB path/bin/mongod --dbpath DBPATH
    #client = MongoClient('localhost', 27017)
    client = MongoClient('mongodb://localhost:27017/')
    db = client['LPNK']
    #collection = db['Y2013']
    #將字串型式時間轉為DateTime物件
    AddDatetimeField(db['Y2013'])
    
    #Before Mongo 4.0
    #client.admin.command('copydb',fromdb='LPNK',todb='LPNK2')
    #db['2013'].copyTo("2013_Copy")

    #client.copy_database(from_name='LPNK',to_name='LPNK2')
    
    #mongo shell:
    #db.Y2013.find().forEach(function(d){ db.getSiblingDB('CopyDB')['copyCol'].insert(d); });
    
    query = {'Time':'20130922132400'}
    TP = [201310230000,201310231400]
    
    ShowDataAttr(db['Y2013'], 'Datetime')
    print("="*50)
    #mongo shell query
    #{Datetime:{
    #    $gte: ISODate("2013-09-22T13:00:00.000Z"),
    #    $lt: ISODate("2013-09-22T17:00:00.000Z")}}

    FMT = "%Y-%m-%dT%H:%M:%SZ"
    from_dt = dte.datetime.strptime(
        "2013-10-23T00:00:00Z", FMT)
    to_dt = dte.datetime.strptime(
        "2013-10-23T14:00:00Z", FMT)
    query = {
        "$or":[
        {"Sender": {
            "$in": ["736158"],
            }},
        {"Receiver": {
            "$in": ["736158"],
            }},
        ],
        #"Datetime":{
            #"$gte": from_dt,
            #"$lt": to_dt
            #}
        }
    project = {
        "_id":0,
        "Sender":1, 
        "Receiver":1, 
        "Datetime": 1, 
        "Length":1
        }
    print("query", query)
    df = Read_Mongo(
                query=query,
                #project=project,
                db='LPNK',
                collection='Y2013',)
    print("The result of Read_Mongo is", df)
    print("="*50)
    for x in df.head(3).itertuples():
        print(x)
        
def sqlite3Query(SQLname, cols=None, clause=None, table=None,
                 query = None):
    rowslist = []
    conn = sqlite3.connect(SQLname)
    c = conn.cursor()
    
    #TableName = Dict['mission'].split("_")[-1].replace(" ","_")
    #create_table = "CREATE TABLE IF NOT EXISTS {} ({})".format(
        #TableName, ColumnsString)
    if query == None:
        query = "SELECT "+','.join(cols)
        if table != None:
            query += " FROM "+table
        if clause !=None:
            query += " WHERE "+clause
    #print("query",query)
    return c.execute(query)
    #conn.commit()
       
def sqlite3QueryTest():
    SQLname = "D:/Emo/test_results_verification_Large.sql3"
    cols = ['PartNO', 'pred_Type', 'text']
    #clause = f"'Src'={file}"
    clause = "abc"
    table = "sampleSrc"
    
    #SELECT PartNO,pred_Type,text from sampleSrc where SRC = "..\FixedTest\#T#[PRC-Think]\科睿唯安\#T#[5G]\5G技術全景報告.txt";
    query = "SELECT DISTINCT Src FROM sampleSrc;"
    FileList = [x[0] for x in list(sqlite3Query(SQLname, query = query))]
    print(f"There are totally {len(FileList)} different files.")
    for file in FileList:
        if file is None:
            continue
        print("file", file)
        query = f'SELECT PartNO,pred_Type,text FROM sampleSrc WHERE SRC = "{file}";'
        rowslist = sqlite3Query(SQLname,  query = query)
        
if __name__ == '__main__':
    #MongoTest()
    sqlite3QueryTest()

