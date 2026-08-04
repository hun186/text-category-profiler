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
import plotly.graph_objects as go
from plotly.offline import plot
import plotly.express as px

import dash
import dash_table
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State
import reusable_components as rc  # see reusable_components.py


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

def wrap(s, w):
    return [s[i:i + w] for i in range(0, len(s), w)]


OFNM = "test_funnel"
Start = 0
MinMaxRatio = 1
MaxnUniqueVal = 16
ChunkUnit = 2
nFigs = 16
ConsPosNum = 0
nProcess= 1
page_current = 0
PAGE_SIZE = 10

start_time = time.time()
InputFile = "RandText_short.txt"
InputFile = "RandText.txt"
#InputFile = "test_results_verification.tsv"
#InputFile = "test_results_verification_Positive.tsv"

def ColumnValuesCount(df):
    return df.apply(pd.Series.value_counts)

class SampleReader():
    def __init__(self, file, LabelList, width = 1024, 
                 Mode = "FullCut", ConvertToSpec = None,
                 nBound = {"default":5000}, sampleLenLBD = 128,
                 LabelConvertDict = {},
                 #TreeBinaryMode = False,
                 TreeBinaryTarget = None,
                 UniqueLabel = True,
                 ):
        self.file = file
        
class SeriesCounter():
    def __init__(self, seri):
        self.seri = seri
    def show(self,):
        print("="*50)
        print("Series:", self.seri)
    def run(self,):
        MES = "Dealing Series {}.\n".format(self.seri)
        MPlogger.logW(MES)
        return dict(self.seri.value_counts())


def build_ChunkDF(ChunkUnit):
    print("Start to load data from InputFile {}".format(InputFile))
    print("and build Chunk Dataframe.")
    #FreqCountList = []
    ShowElapsedTime(start_time)
    rowlist = []
    with open(InputFile,'rt',encoding = 'utf-8') as f:
        for line in f:
            sent = line.strip()
            sentWrap = wrap(sent, ChunkUnit)
            rowlist.append(sentWrap)
    print("Finished building the rowlist.")
    ShowElapsedTime(start_time)
    print("Start to transform rowlist to Dataframe")
    df = pd.DataFrame(rowlist)
    print("Finished build Chunk DataFrame.")
    ShowElapsedTime(start_time)
    return df

def build_FreqCountList(ChunkUnit):
    print("Start to load data from InputFile {} and count".format(InputFile))
    print("as list of lists of count unit.")
    FreqCountList = []
    ShowElapsedTime(start_time)
    with open(InputFile,'rt',encoding = 'utf-8') as f:
        for line in f:
            sent = line.strip()
            sentWrap = wrap(sent, ChunkUnit)
            for i,x in enumerate(sentWrap):
                if len(FreqCountList) < len(sentWrap):
                    FreqCountList.extend([{}])
                FreqCountList[i][x] = FreqCountList[i].get(x, 0) + 1
    #
    print("Finished loading and counting data from InputFile {}".format(InputFile))
    ShowElapsedTime(start_time)
    return FreqCountList

def build_visualizationsOld(Start,nFigs,MinMaxRatio,MaxnUniqueVal):
    figList = []
    titleList = []
    nChosenFig = 0
    ChunkPos = Start
    while(nChosenFig < nFigs and ChunkPos < len(FreqCountList)):
    #for i in range(nFigs):
        #print(df[i].value_counts())
        FreqCountList[ChunkPos] = dict(sorted(
            FreqCountList[ChunkPos].items(), key=lambda x:x[1],reverse = True))
        MPlogger.logW(str(FreqCountList[ChunkPos]))
        terms = list(FreqCountList[ChunkPos].keys())
        numbers = list(FreqCountList[ChunkPos].values())
        MinVal = min(FreqCountList[ChunkPos].values())
        MaxVal = max(FreqCountList[ChunkPos].values())
        if MinVal/MaxVal <= MinMaxRatio or len(FreqCountList[ChunkPos].values()) < MaxnUniqueVal:
            figList.append(go.Figure(go.Funnel(y = terms,x =numbers)))
            titleList.append("POS {}".format(ChunkPos))
            nChosenFig +=1
        ChunkPos += 1
    if len(figList) < nFigs:
        figList.extend([go.Figure()]*(nFigs - len(figList)))
        titleList.extend([None]*(nFigs - len(titleList)))
    return figList+titleList


def build_visualizations(Start,nFigs,MinMaxRatio,MaxnUniqueVal,RowConstraint = None):
    figList = []
    titleList = []
    nChosenFig = 0
    ChunkPos = Start
    nCol = df.shape[1]
    while(nChosenFig < nFigs and ChunkPos < nCol):
    #for i in range(nFigs):
        #print(df[i].value_counts())
        #print("="*50)
        #print(ChunkPos,'\n', dict(df[ChunkPos].value_counts()))
        MES = "{} \n {}".format(ChunkPos, dict(df[ChunkPos].value_counts()))
        MPlogger.logW(MES)
        DictCK = dict(df[ChunkPos].value_counts())
#        print(dict(df[ChunkPos].value_counts()))
#        raise Exception
        #MPlogger.logW(str(FreqCountList[ChunkPos]))
        terms = list(DictCK.keys())
        numbers = list(DictCK.values())
        MinVal = min(numbers)
        MaxVal = max(numbers)
        if MinVal/MaxVal <= MinMaxRatio or len(numbers) < MaxnUniqueVal:
            figList.append(go.Figure(go.Funnel(y = terms,x =numbers)))
            titleList.append("POS {}".format(ChunkPos))
            nChosenFig +=1
        ChunkPos += 1
    if len(figList) < nFigs:
        figList.extend([go.Figure()]*(nFigs - len(figList)))
        titleList.extend([None]*(nFigs - len(titleList)))
    #print("in build vis, RowConstraint",RowConstraint)
    ShowingRows = []
    if RowConstraint != None:
        for key in RowConstraint.keys():
            if key == None:
                continue
            keyPos = int(key.split(" ")[1])
            ConstList = RowConstraint[key]
            Partdf = df.loc[df[keyPos].isin(ConstList)]
            for i in range(Partdf.shape[0]):
                sent = ''.join((Partdf.iloc[i]).dropna())
                ShowingRows.append(sent+"\n")
        
    else:
        for i in range(1):
            sent = ''.join((df.iloc[i]).dropna())
            ShowingRows.append(sent+"\n")
        
    print("in build ShowingRows[0:2]", ShowingRows[0:2])
    #print(figList, titleList)
    #print(figList, titleList)
    ShowingRowsFig = go.Figure(
        data=[go.Table(
                header=dict(values=['text']),
                 cells=dict(
                     values=[ShowingRows],
                     line_color='darkslategray',
                     fill_color='lightcyan',
                     align='left',
                     font_size=16,
                     height=30)
                 )
              ])
    return figList, titleList, ShowingRowsFig



def create_card(card_id, title, description, fig):
    return dbc.Card(
        dbc.CardBody(
            [
                html.H2(id=f"{card_id}-title", children = title),
                #html.H2("100", id=f"{card_id}-value"),
                #html.P(description, id=f"{card_id}-description"),
                dcc.Graph(
                    id=f"{card_id}-graph",
                    figure=fig),
                
            ]
        )
    )


def RowsFilter(ChunkDF, RowConstraint = None):
    #df['index'] = range(1, len(df) + 1)
    ShowingRows = []
    if RowConstraint != None:
        for key in RowConstraint.keys():
            keyPos = int(key.split(" ")[1])
            ConstList = RowConstraint[key]
            Partdf = df.loc[df[keyPos].isin(ConstList)]
            for i in range(Partdf.shape[0]):
                sent = ''.join((Partdf.iloc[i]).dropna())
                ShowingRows.append(sent+"\n")
        

    if len(ShowingRows) == 0:
        sent = ''.join((df.iloc[0]).dropna())
        ShowingRows.append(sent+"\n")
    ShowingDF = pd.DataFrame(ShowingRows, columns = ["text"])
    if ShowingDF.shape[0] > 0:
        print("ShowingDF.columns", ShowingDF.columns)
        #ShowingDF.columns = ["text"]
        print("ShowingDF.columns", ShowingDF.columns)
        ShowingDF[' index'] = range(1, len(ShowingDF) + 1)
        print("ShowingDF\n", ShowingDF)
    dfOutputer(ShowingDF[["text"]], "test").run()
    return ShowingDF

#FreqCountList = build_FreqCountList(ChunkUnit)
#visList = build_visualizationsOld(Start,nFigs,MinMaxRatio,MaxnUniqueVal)
df = build_ChunkDF(ChunkUnit)
#visList = build_visualizations(Start,nFigs,MinMaxRatio,MaxnUniqueVal)
figList, titleList, ShowingRowsFig = build_visualizations(Start,nFigs,MinMaxRatio,MaxnUniqueVal)
#df[' index'] = range(1, len(df) + 1)
ShowingDF = RowsFilter(df)
print(" in vis ShowingDF",ShowingDF)
page_size = PAGE_SIZE
ShowingData = ShowingDF.iloc[
        page_current*page_size:(page_current+ 1)*page_size
    ].to_dict('records')
print("ShowingData", ShowingData)



external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

#app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
app = dash.Dash(external_stylesheets=[dbc.themes.BOOTSTRAP])

# ############ Build components and layouts ############
navbar = html.Nav(
    html.Div(
        className="nav-wrapper teal",
        children=[
            html.Img(
                src=app.get_asset_url("dash-logo.png"),
                style={"float": "right", "height": "100%", "padding-right": "15px"},
            ),
            html.A(
                "GCH and Cut Plane Visualization in FLORIS",
                className="brand-logo",
                href="https://plotly.com/dash/",
                style={"padding-left": "15px"},
            ),
        ],
    )
)

controls = [
    rc.CustomSlider(
        id="Start Bar", min=0, 
        #max=len(FreqCountList)-nFigs, label="Start Point"),
        max=df.shape[1]-nFigs, label="Start Point",
        value = 0),
    rc.CustomSlider(
        id="MinMaxRatio Bar", min=0, 
        max=1, label="Min-Max Ratio Upper Bound", step=0.01,
        value = 1),
    rc.CustomSlider(
        id="MaxnUniqueVal Bar", min=0, 
        max=32, label="Max number of Unique Value",
        value = 32),
    #rc.CustomSlider(id="nLine", min=0, max=290, label="Number of Lines Once"),
    #rc.CustomSlider(id="ChunkUnit Bar", min=1, max=6, label="Chunk Unit"),
]



#print("Start", Start)
#FirstPos = int(titleList[0].split(" ")[1])

app.layout = html.Div([
    rc.Row([
        html.H2("Constraint: "),
        rc.Col(dcc.Dropdown(
            id='dropdown Constraint Pos',
            options=[{'label': i, 'value': i} for i in titleList],
        ),width = 3),
        rc.Col(dcc.Dropdown(
            id='dropdown Constraint Value',
            options=[{'label': i, 'value': i} for i in df[ConsPosNum].unique()],
        ),width = 6),
        ]),
    
        #html.Ul(id = "ShowingRows", 
                #children = [html.Li('-'+x+'\n') for x in ShowingRows]),
    rc.Row([dash_table.DataTable(
        id='datatable-paging',
        columns=[
            #{"name": i, "id": i} for i in sorted(df.columns)
            {"name": i, "id": i} for i in sorted(ShowingDF.columns)
        ],
        page_current=0,
        page_size=PAGE_SIZE,
        page_action='custom',
        #data=df.to_dict('records'),
        style_header={'backgroundColor': 'rgb(30, 30, 30)'},
        style_cell={
            'backgroundColor': 'rgb(50, 50, 50)',
            'color': 'white',
            'textAlign': 'left',
            'whiteSpace': 'normal',
            'height': 'auto',
        },
        style_cell_conditional=[
            {
                'if': {'column_id': c},
                'textAlign': 'right'
            } for c in [' index']
        ],
    ),]),
    dbc.Row(
        
            dbc.Col(
                create_card(card_id = 'ShowingRowsTable',
                            #title = 'POS {}'.format(i+Start),
                            #title = '',
                            title = "Sample Rows",
                            description = 'description{}'.format("text"),
                            fig = ShowingRowsFig
                            )
                ,width = 12)
        
    ),
    
    html.H1(children='Chunk Column Count'),
    html.H2("="*50),
    rc.Row([
        rc.Col(rc.Row([html.H2("Start ="),
        html.H2(id = "Start Pos", children=f'{Start}')]),width=3),
        rc.Col(rc.Row([html.H2("Min/Max-Ratio Upper Bound ="),
        html.H2(id = "Min-Max Ratio", children=f'{MinMaxRatio}')]),width=3),
        rc.Col(rc.Row([html.H2("Max number of Unique Value ="),
        html.H2(id = "MaxnUniqueVal", children=f'{MaxnUniqueVal}')]),width=3),
        ]),
    rc.Row([
        rc.Col(html.H2(id = "nLines", children=f'Number of Chunks Once = {nFigs}'),width=3),
        rc.Col(html.H2(id = "ChunkUnit", children=f'Chunk Unit = {ChunkUnit}'),width=3),
        ]),
    #html.Div([html.H2("Start ="),
        #html.H2(id = "Start Pos", children=f'{Start}')]),
    html.H2("="*50),
    #html.H2(id = "nLines", children=f'Number of Lines Once = {nFigs}'),
    #html.H2(id = "ChunkUnit", children=f'Chunk Unit = {ChunkUnit}'),

    rc.Row(
        rc.Col(
            rc.Card(rc.CardContent(rc.Row([rc.Col(c, width=3) for c in controls]))),
            width=12,
        )
    ),
    #dbc.Row(dbc.Col(html.Div(controls[0]))),
    #dbc.Row(
        #[
            #dbc.Col(html.Div(
                #dcc.Graph(
                    #id='example-graph{}'.format(i),
                    #figure=figList[i]),
                #), width=6) for i in range(4)
        #]
    #),
    dbc.Row(
        [
            dbc.Col(
                create_card(card_id = 'pos {}'.format(i+Start),
                            #title = 'POS {}'.format(i+Start),
                            #title = '',
                            title = titleList[i],
                            description = 'description{}'.format(i),
                            fig = figList[i]
                            )
                ,width = 6) for i in range(nFigs)
        ]
    ),

    #rc.Row(
        #[c for c in dccGraphs],
            
    #),

    

])



argws = []
argws.extend([Output("Start Pos", "children")])
argws.extend([Output("Min-Max Ratio", "children")])
argws.extend([Output("MaxnUniqueVal", "children")])
argws.extend([Output(f"pos {Start+i}-graph", "figure") for i in range(nFigs)])
argws.extend([Output(f"pos {Start+i}-title", "children") for i in range(nFigs)])
argws.extend([Output("dropdown Constraint Pos", "options")])
argws.extend([Output("dropdown Constraint Value", "options")])
argws.extend([Output("ShowingRowsTable-graph", "figure")])
argws.extend([Output('datatable-paging', 'data')])
argws.extend([Input("Start Bar", "value")])
argws.extend([Input("MinMaxRatio Bar", "value")])
argws.extend([Input("MaxnUniqueVal Bar", "value")])
argws.extend([Input('dropdown Constraint Pos', 'value')])
argws.extend([Input('dropdown Constraint Value', 'value')])
argws.extend([Input('datatable-paging', "page_current")])
argws.extend([Input('datatable-paging', "page_size")])
argws.extend([Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])

#print(*argws)
@app.callback(*argws)
def vis_update(
        Start,MinMaxRatio,MaxnUniqueVal,ConsPos,
        SingleConsValue = None, page_current = 0, page_size=5, *argws):
    print("*argws", *argws)
    selectionList = list(argws)
    print("*selectionList", selectionList)
    figList, titleList, ShowingRows = build_visualizations(
        Start,nFigs,MinMaxRatio,MaxnUniqueVal)
    #print("ShowingRows", ShowingRows)
    #FirstPos = [int(titleList[0].split(" ")[1])]
    #print(":titleList", titleList)
    if ConsPos is not None:
        ConsPosNum = int(ConsPos.split(" ")[1])
    else:
        ConsPosNum = 0

    #print("selection1", selection1)
    LabelsList = []
    #Posj = 0
    #for selected_data in [selection1]:
    global RowConstraint
    RowConstraint = {}
    if SingleConsValue != None:
        RowConstraint[ConsPos] = [SingleConsValue]
    for j,selected_data in enumerate(selectionList):
        #print("selected_data", selected_data)
        if selected_data and selected_data['points']:
            for point in selected_data['points']:
                print("j,label", j, point['y'])
                LabelsList.append(point['y'])
            RowConstraint[titleList[j]] = LabelsList
            print("="*50)
    print("RowConstraint", RowConstraint)


    
    dropdownConsPosList = [[{'label': i, 'value': i} for i in titleList]]
    dropdownConsValueList = [[
        {'label': i, 'value': i} 
        for i in list(dict(df[ConsPosNum].value_counts()).keys())]]
    figList, titleList, ShowingRows = build_visualizations(
        Start,nFigs,MinMaxRatio,MaxnUniqueVal, RowConstraint=RowConstraint)
    ShowingDF = RowsFilter(df, RowConstraint)
    print(" in vis ShowingDF",ShowingDF)
    ShowingData = ShowingDF.iloc[
            page_current*page_size:(page_current+ 1)*page_size
        ].to_dict('records')
    print("ShowingData", ShowingData)
    return [Start,MinMaxRatio,MaxnUniqueVal
            ]+figList+ titleList+dropdownConsPosList+dropdownConsValueList+[ShowingRows]+[ShowingData]

'''
@app.callback(
    Output('datatable-paging', 'data'),
    Input('datatable-paging', "page_current"),
    Input('datatable-paging', "page_size"))
def update_table(page_current,page_size):
    ShowingDF = RowsFilter(df, RowConstraint)
    return ShowingDF.iloc[
        page_current*page_size:(page_current+ 1)*page_size
    ].to_dict('records')
'''

if __name__ == '__main__':
    nProcess= 40
    '''
    print("START to import tsv To MySQL.")
    InputTSV = "dataset_total_with_filename_Large.tsv"
    df = TSVtodf(InputTSV, sep = '\t')
    multicoreJob(MulticoreMode = True, nProcess = nProcess
                 ).parallelize_dataframe(df, dftoMySQL)
    print("Finished importing tsv To MySQL.")
    '''

    app.run_server(debug=True, use_reloader=False)
    