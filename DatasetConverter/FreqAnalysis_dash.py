from PackageImport import PackageImporter
PackageImporter.proc()

import time
import pandas as pd
import json
import ast

from MP_utils import MPlogger
#from MP_utils import multicoreJob

from utils.utilities import wrap
from utils.utilities import ShowElapsedTime
from utils.utilities import OffsetWrap
from utils.utilities import UniqueList

from df_utils import dfOutputer
from df_utils import StrDfFromJson

import plotly.graph_objects as go
#from plotly.offline import plot
#import plotly.express as px

import dash
import dash_table
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State
import reusable_components as rc  # see reusable_components.py
#from dash_utils import make_dash_table

def init_ParamsDF():
    VisParamsDict = {
        "Start POS": Start,
        "Min/Max-Ratio Bound": str(MinMaxRatio),
        "Number of Unique Value": nUniqueVal,
        "Number of Chunks Once": nFigs
        }
    VisParamsDF = pd.DataFrame(
        VisParamsDict.items(), columns=['parameter', 'value'])
    VisParamsDF = VisParamsDF.set_index('parameter')
    VisParamsDF_json = VisParamsDF.to_json(date_format='iso', orient='split')
    
    ChunkParamsDict = {
        #"CutStart": CutRange[0],
        #"CutEnd": sentCutEnd,
        "CutRange": CutRange,
        "Chunk Unit": ChunkUnit,
        "Stride": Stride,
        }
    ChunkParamsDF = pd.DataFrame(
        ChunkParamsDict.items(), columns=['parameter', 'value'])
    ChunkParamsDF = ChunkParamsDF.set_index('parameter')
    ChunkParamsDF_json = ChunkParamsDF.to_json(date_format='iso', orient='split')
    return VisParamsDF, VisParamsDF_json, ChunkParamsDF, ChunkParamsDF_json

def UniqueConstraint(RowConstraint):
    for key in RowConstraint.keys():
        RowConstraint[key] = UniqueList(RowConstraint[key])
    return RowConstraint

def DataArrayToDict(dataArray):
    '''
    RowConstraintArray [
    {'POS':0, "Constraint":"['o', 'w']",},
    {'POS':1, "Constraint":"['y', 'c', 'b']",}
    ]
    RowConstraint {
    'POS 0': ['o', 'w'], 'POS 1': ['y', 'c', 'b']
    }
    '''
    result = {}
    for x in dataArray:
        #print("INDAT x", x)
        #print("POS {}".format(x['POS']))
        #print(ast.literal_eval(x['Constraint']))
        try:
            result["POS {}".format(x['POS'])] = ast.literal_eval(x['Constraint'])
        except Exception as ex:
            print(ex)
    return result

def DictToDataArray(dictionary):
    '''
    RowConstraint {
    'POS 0': ['o', 'w'], 'POS 1': ['y', 'c', 'b']
    }
    RowConstraintArray [
    {'POS':0: "['o', 'w']",},
    {'POS':1: "['y', 'c', 'b']",}
    ]
    '''
    result = []
    for x in dictionary.keys():
        result.append(
            {'POS':x.split(" ")[1],"Constraint":str(dictionary[x])})
    return result
                                                              

OFNM = "test_funnel"
#sentCutStart = None
#sentCutEnd = None
CutRange = [None, None]
#sentCutStart = 0
#sentCutEnd = 30
Start = 0
MinMaxRatio = [0, 1]
#MaxnUniqueVal = 16
nUniqueVal = [1,32]
ChunkUnit = 1
Stride = ChunkUnit
nFigs = 16
#nFigs_json = json.dumps(str(nFigs))
ConsPosNum = 0
nProcess= 1
page_current = 0
PAGE_SIZE = 10

[VisParamsDF, VisParamsDF_json, ChunkParamsDF, ChunkParamsDF_json
 ] = init_ParamsDF()

RowConstraint = dict()
RowConstraint_json = json.dumps(RowConstraint, indent = 4)
RowConstraintDF = pd.DataFrame(columns = ["POS", "Constraint"], data = RowConstraint)

start_time = time.time()
InputFile = "RandText_short.txt"
InputFile = "RandText.txt"
#InputFile = "test_results_verification.tsv"
#InputFile = "test_results_verification_Positive.tsv"
#InputFile = "MP_log.txt"

def ColumnValuesCount(df):
    return df.apply(pd.Series.value_counts)

        
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


def build_ChunkDF(
        ChunkUnit, Stride, 
        CutRange = []):
        #sentCutStart = None, sentCutEnd =None):
    print("Start to load data from InputFile {}".format(InputFile))
    print("and build Chunk Dataframe.")
    #FreqCountList = []
    ShowElapsedTime(start_time)
    rowlist = []
    with open(InputFile,'rt',encoding = 'utf-8') as f:
        for line in f:
            sent = line.strip()
            if CutRange[0]!=None and CutRange[1] !=None:
                sent = sent[CutRange[0]:CutRange[1]]
            #sentWrap = wrap(sent, ChunkUnit)
            sentWrap = OffsetWrap(sent, Stride, ChunkUnit)
            rowlist.append(sentWrap)
    print("Finished building the rowlist.")
    ShowElapsedTime(start_time)
    print("Start to transform rowlist to Dataframe")
    df = pd.DataFrame(rowlist)
    df = df.where(df.isnull(), df.astype(str))
    print("Finished build Chunk DataFrame.")
    ShowElapsedTime(start_time)   
    ChunkParamsDF.loc["CutRange","value"] = str(CutRange)
    ChunkParamsDF.loc["Chunk Unit","value"] = ChunkUnit
    ChunkParamsDF.loc["Stride","value"] = Stride
    return df, ChunkParamsDF

def BuildChunkParamsCardBody(ChunkParamsDF):
    ChunkParamsDF = ChunkParamsDF.reset_index()
    #VisParamsDF.columns = ['parameter', 'value']
    #ChunkParamsDFData = []
    #ChunkParamsDFData = [{'parameter':x[0],
                     #'value':x[1]} for x in dict(ChunkParamsDF.values).items()]
    return dash_table.DataTable(
        id='Chunk Params',
        data=ChunkParamsDF.to_dict('records'),
        #data=ChunkParamsDFData,
        columns=[{'id': c, 'name': c} for c in ['parameter', 'value']],
        style_cell={'textAlign': 'center'},
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': 'rgb(248, 248, 248)'
            }
        ],
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold'
            },
        #editable=True
        )
                        
def build_visualizations(
        df, Start,nFigs,MinMaxRatio,nUniqueVal, VisParamsDF,
        RowConstraint = None):
    figList = []
    titleList = []
    nChosenFig = 0
    ChunkPos = Start
    nCol = df.shape[1]
    while(nChosenFig < nFigs and ChunkPos < nCol):
        MES = "{} \n {}".format(ChunkPos, dict(df[ChunkPos].value_counts()))
        MPlogger.logW(MES)
        DictCK = dict(df[ChunkPos].value_counts())
        DictCK = sorted(
            DictCK.items(), key = lambda kv:(kv[1], kv[0]), reverse = True)
        terms, numbers = zip(*DictCK)
        terms = [str(x) for x in terms]
        try:
            MinVal = min(numbers)
        except:
            MinVal = 0
        try:
            MaxVal = max(numbers)
        except:
            MaxVal = 0
        if MaxVal != 0:
            Ratio = MinVal/MaxVal
        else:
            Ratio = 0
        if  all([MinMaxRatio[0] <= Ratio <= MinMaxRatio[1],
                 nUniqueVal[0]<= len(numbers) <= nUniqueVal[1]]):
            figList.append(go.Figure(go.Funnel(y = terms,x =numbers)))
            titleList.append("POS {}".format(ChunkPos))
            nChosenFig +=1
        ChunkPos += 1
    if len(figList) < nFigs:
        figList.extend([go.Figure()]*(nFigs - len(figList)))
        titleList.extend([None]*(nFigs - len(titleList)))
        
    VisParamsDF.loc["Start POS","value"] = Start
    VisParamsDF.loc["Number of Chunks Once","value"] = nFigs
    VisParamsDF.loc["Min/Max-Ratio Bound","value"] = str(MinMaxRatio)
    VisParamsDF.loc["Number of Unique Value","value"] = str(nUniqueVal)
    return figList, titleList, VisParamsDF



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


def RowsFilter(df, ChunkUnit, Stride, RowConstraint = None):
    ShowingRows = []
    FilteredDF = df
    if RowConstraint != None:
        for key in RowConstraint.keys():
            if key == None or key == '':
                continue
            keyPos = int(key.split(" ")[1])
            ConstList = RowConstraint[key]
            FilteredDF = FilteredDF.loc[
                FilteredDF[keyPos].isin(ConstList)]
        for i in range(FilteredDF.shape[0]):
            sent = ''.join(str(x) for x in list(
                    (FilteredDF.iloc[i]).dropna())[
                    ::max(ChunkUnit-Stride,0)+1])
            #sent = ''.join((FilteredDF.iloc[i]).dropna())
            ShowingRows.append(sent)
    #先用List:ShowingRows蒐集串接後的還原text，再轉成ShowingDF。
    ShowingDF = pd.DataFrame(ShowingRows, columns = ["text"])
    if ShowingDF.shape[0] > 0:
        ShowingDF['index'] = range(1, len(ShowingDF) + 1)
    if ShowingDF.shape[0] < 10000:
        dfOutputer(ShowingDF[["text"]], "test").run()
    return FilteredDF, ShowingDF

df, ChunkParamsDF = build_ChunkDF(ChunkUnit, Stride, CutRange)
df_json = df.to_json(date_format='iso', orient='split')
FilteredDF_json = df_json
FilteredDF, ShowingDF = RowsFilter(df, ChunkUnit, Stride)
nSamples = len(FilteredDF)
figList, titleList, VisParamsDF = build_visualizations(
    FilteredDF, Start,nFigs,MinMaxRatio,nUniqueVal, VisParamsDF)


page_size = PAGE_SIZE
ShowingData = ShowingDF.iloc[
        page_current*page_size:(page_current+ 1)*page_size
    ].to_dict('records')


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

controls1 = [
    rc.CustomSlider(
        id="Start Bar", min=0, 
        max=df.shape[1]-nFigs, label="Start Point",
        value = 0),
    rc.CustomRangeSlider(
        id="MinMaxRatio Bar", min=0, 
        max=1, label="Min-Max Ratio Bound", step=0.01,
        value = MinMaxRatio),
    rc.CustomRangeSlider(
        id="nUniqueVal Bar", min=1, 
        max=max(df.nunique()), label="number of Unique Value", step=1,
        value = nUniqueVal),
]
controls2 = [
    rc.CustomRangeSlider(
        id="CutRange Bar", min=0, 
        max=df.shape[1], label="CutRange", step=1,
        value = [0,df.shape[1]]),
    rc.CustomSlider(
        id="ChunkUnit Bar", min=0, 
        max=16, label="ChunkUnit",
        value = ChunkUnit),
    rc.CustomSlider(
        id="Stride Bar", min=0, 
        max=16, label="Stride",
        value = Stride),
    rc.CustomSlider(
        id="nFigs Bar", min=0, 
        max=256, label="Number of Figs",
        value = 16),
]

app.layout = html.Div([
    rc.Row([
        rc.Col(
            dbc.Card(
                [
                    dbc.CardHeader(html.H2("Constraint List:")),
                    dbc.CardBody(
                        [
                        dash_table.DataTable(
                            id='Constraint Dict',
                            data = [],
                            columns=[
                                #{"name": i, "id": i} for i in sorted(df.columns)
                                {"name": i, "id": i} for i in ["POS","Constraint"]
                            ],
                            page_current=0,
                            page_size=PAGE_SIZE,
                            page_action='custom',
                            #data=RowConstraint,
                            #html.H2(id = "Constraint Dict", children = RowConstraint),
                            style_cell={
                                'backgroundColor': 'rgb(50, 50, 50)',
                                'color': 'white',
                                #'textAlign': 'left',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                            },
                            row_deletable=True,
                            editable=True,
                            ),
                        html.Button(
                            'Add Row', 
                            id='editing-Constraint-Dict-button', n_clicks=0),
                        ]
                    ),
                    #dbc.CardFooter("This is the footer"),
                ],
                color="info",
                style={"width": "30rem"},
            ),
            width=3),
        rc.Col(
            dbc.Card(
                [
                    dbc.CardHeader(html.H2("Visualization Parameters")),
                    dbc.CardBody(
                        [
                        dash_table.DataTable(
                            id='Vis Params',
                            #data=VisParamsDF.to_dict('records'),
                            columns=[{'id': c, 'name': c} for c in ['parameter', 'value']],
                            style_cell={'textAlign': 'center'},
                            style_data_conditional=[
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': 'rgb(248, 248, 248)'
                                }
                            ],
                            style_header={
                                'backgroundColor': 'rgb(230, 230, 230)',
                                'fontWeight': 'bold'
                            }
                        ),
                        ]),
                ],
                color="warning",
                style={"width": "30rem"},
            ),
            width=3),
        rc.Col(
            dbc.Card(
                [
                    dbc.CardHeader(html.H2("Chunk Parameters")),
                    dbc.CardBody(id='Chunk Params CardBody'),
                ],
                color="success",
                style={"width": "30rem"},
            ),
            width=3),
    ]),
    rc.Row([
        html.H2("Constraint: "),
        rc.Col(dcc.Dropdown(
            id='dropdown Constraint Pos',
            options=[{'label': i, 'value': i} 
                     for i in list(filter(None, titleList))],
        ),width = 3),
        rc.Col(dcc.Dropdown(
            id='dropdown Constraint Value',
            options=[{'label': i, 'value': i} for i in df[ConsPosNum].unique()],
        ),width = 6),
        ]),
    

    dbc.Card(
        [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(html.H2("Samples under Constraint:"),width=3),
                rc.Col(rc.Row([html.H2("total Number:"),
                               html.H2(id = "nSamples", children=f'{nSamples}')]),width=3),
                rc.Col(rc.CustomSlider(
                    id="Page Size Bar", min=0, 
                    max=1000, label="Page Size",
                    value = 10),width=6),
                    ])
                ),
            dbc.CardBody(
                [
                dash_table.DataTable(
                    id='datatable-paging',
                    columns=[
                        #{"name": i, "id": i} for i in sorted(df.columns)
                        {"name": i, "id": i} for i in sorted(ShowingDF.columns)
                    ],
                    page_current=0,
                    page_size=PAGE_SIZE,
                    #page_action='custom',
                    page_action='native',
                    #data=df.to_dict('records'),
                    filter_action='native',
                    #style_header={'backgroundColor': 'rgb(30, 30, 30)'},
                    style_header={'backgroundColor': 'orange'},
                    style_cell={
                        #'backgroundColor': 'rgb(50, 50, 50)',
                        'backgroundColor': 'rgb(252, 240, 204)',
                        #'color': 'white',
                        'color': 'rgb(12, 37, 201)',
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
                    sort_action='native',
                    sort_mode='multi',
                    sort_by=[]
                )
                ]
            ),
            #dbc.CardFooter("This is the footer"),
        ],
        style={"width": "12"},
    ),
    

# =============================================================================
#     dbc.Row(
#         
#             dbc.Col(
#                 create_card(card_id = 'ShowingRowsTable',
#                             #title = 'POS {}'.format(i+Start),
#                             #title = '',
#                             title = "Sample Rows",
#                             description = 'description{}'.format("text"),
#                             fig = ShowingRowsFig
#                             )
#                 ,width = 12)
#         
#     ),
# =============================================================================
    rc.Row(
        rc.Col(
            rc.Card(rc.CardContent(rc.Row([rc.Col(c, width=3) for c in controls1]))),
            width=12,
        )
    ),
    rc.Row(
        rc.Col(
            rc.Card(rc.CardContent(rc.Row([rc.Col(c, width=3) for c in controls2]))),
            width=12,
        )
    ),
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

    dcc.Store(id='intermediate-value-df',  data = df_json),
    dcc.Store(id='intermediate-value-FilteredDF',  data = FilteredDF_json),
    dcc.Store(id='intermediate-value-VisParamsDF',  data = VisParamsDF_json),
    dcc.Store(id='intermediate-value-ChunkParamsDF',  data = ChunkParamsDF_json),
    dcc.Store(id='intermediate-value-RowConstraint',  data = RowConstraint_json),
    dcc.Store(id='intermediate-value-RowConstraint_Previous',  data = RowConstraint_json),
    dcc.Store(id='intermediate-value-nFigs',  data = nFigs),

    

])


args = []
args.extend([Output('intermediate-value-nFigs', 'data')])
args.extend([Input("nFigs Bar", "value")])
@app.callback(*args)
def nFigs_update(nFigs_Bar):
    global nFigs 
    nFigs = nFigs_Bar
    return nFigs_Bar


#===============================================================

args = []
#args.extend([Output("ChunkUnit", "children")])
#args.extend([Output("POS Offset", "children")])
args.extend([Output('intermediate-value-df', 'data')])
#args.extend([Output('Chunk Params', 'data')])
args.extend([Output('Chunk Params CardBody', 'children')])
args.extend([Output('Start Bar', 'max')])
args.extend([Output('Start Bar', 'marks')])
args.extend([Output('nUniqueVal Bar', 'max')])
args.extend([Output('nUniqueVal Bar', 'marks')])
#args.extend([Output('nUniqueVal Bar', 'value')])
args.extend([Input("CutRange Bar", "value")])
args.extend([Input("ChunkUnit Bar", "value")])
args.extend([Input("Stride Bar", "value")])
@app.callback(*args)
def ChunkDF_update(
        CutRange, ChunkUnit, Stride):
    df, ChunkParamsDF = build_ChunkDF(ChunkUnit, Stride, CutRange)
    df_json = df.to_json(date_format='iso', orient='split')
    
    Start_min = 0
    Start_max = df.shape[1]-nFigs
    Start_mid = int((Start_min + Start_max) / 2)
    Start_marks = {i: str(i) for i in [
        Start_min, Start_mid, Start_max]}

    nUniqueVal_min = 1
    nUniqueVal_max = max(df.nunique())
    nUniqueVal_mid = int((nUniqueVal_min + nUniqueVal_max) / 2)
    nUniqueVal_marks = {i: str(i) for i in [
        nUniqueVal_min, nUniqueVal_mid, nUniqueVal_max]}

    
    return [df_json] +[
        BuildChunkParamsCardBody(ChunkParamsDF)
            ]+[Start_max,Start_marks
            ]+[nUniqueVal_max,nUniqueVal_marks]

            #]#,FilteredDF_json]



#===============================================================

args = []
#args.extend([Output("Start Pos", "children")])
#args.extend([Output("Min-Max Ratio", "children")])
#args.extend([Output("MaxnUniqueVal", "children")])
args.extend([Output(f"pos {Start+i}-graph", "figure") for i in range(nFigs)])
args.extend([Output(f"pos {Start+i}-title", "children") for i in range(nFigs)])
args.extend([Output("dropdown Constraint Pos", "options")])
args.extend([Output('Vis Params', 'data')])
args.extend([Input("Start Bar", "value")])
args.extend([Input("MinMaxRatio Bar", "value")])
args.extend([Input("nUniqueVal Bar", "value")])
args.extend([Input('intermediate-value-nFigs', 'data')])
args.extend([Input('intermediate-value-FilteredDF', 'data')])
args.extend([State('intermediate-value-VisParamsDF', 'data')])


@app.callback(*args)
def vis_update(
        Start,MinMaxRatio,nUniqueVal, nFigs, 
        FilteredDF_json, VisParamsDF_json):
    #print("MinMaxRatio", MinMaxRatio)
    FilteredDF = StrDfFromJson(FilteredDF_json, orient='split')
    VisParamsDF = pd.read_json(VisParamsDF_json, orient='split')
    figList, titleList, VisParamsDF = build_visualizations(
        FilteredDF, Start,nFigs,MinMaxRatio,nUniqueVal, VisParamsDF)

    
    dropdownConsPosList = [
        {'label': i, 'value': i} for i in list(filter(None, titleList))]
    VisParamsDF = VisParamsDF.reset_index()
    #VisParamsDF.columns = ['parameter', 'value']
    VisParamsDFData = []
    VisParamsDFData = [{'parameter':x[0],
                     'value':x[1]} for x in dict(VisParamsDF.values).items()]
    return figList+ titleList+[dropdownConsPosList]+[VisParamsDFData]
#===============================================================
args = []
args.extend([Output("dropdown Constraint Value", "options")])
args.extend([Input("dropdown Constraint Pos", "value")])
args.extend([State('intermediate-value-FilteredDF', 'data')])

@app.callback(*args)

def update_dropdown_Constraint_value(
        ConsPos,
        FilteredDF_json):
    if "POS" in str(ConsPos):
        ConsPosNum = int(ConsPos.split(" ")[1])
    else:
        ConsPosNum = 0
    FilteredDF = StrDfFromJson(FilteredDF_json, orient='split')
    vcnt = dict(FilteredDF[ConsPosNum].value_counts())
    value_sorted = sorted(
        vcnt.keys(), key = lambda i: vcnt[i], reverse = True)
    dropdownConsValueList = [{'label': i, 'value': i} 
        for i in value_sorted]
    return dropdownConsValueList


#=================================
args = []
args.extend([Output('datatable-paging', "page_size")])
args.extend([Output('datatable-paging', 'data')])
args.extend([Output('intermediate-value-FilteredDF', 'data')])
args.extend([Output('nSamples', 'children')])
args.extend([Input('datatable-paging', "page_current")])
args.extend([Input("Page Size Bar", "value")])
args.extend([Input('intermediate-value-df', 'data')])
args.extend([Input('Constraint Dict', 'data')])
args.extend([Input("ChunkUnit Bar", "value")])
args.extend([Input("Stride Bar", "value")])
@app.callback(*args)
def table_update(
        page_current,
        page_size,
        df_json,
        RowConstraintArray,
        ChunkUnit,
        Stride,
        #*args
        ):
    '''
    當篩濾條件RowConstraint變動時，
    更新符合條件的樣本之表格(Samples under Constraint)及更新下拉Constrain選項
    並更新FilteredDF變數
    '''
    df =  StrDfFromJson(df_json, orient='split')
    RowConstraint = DataArrayToDict(RowConstraintArray)
    FilteredDF, ShowingDF = RowsFilter(df, ChunkUnit, Stride, RowConstraint)
    FilteredDF_json = FilteredDF.to_json(date_format='iso', orient='split')
    #ShowingData = ShowingDF.iloc[
            #page_current*page_size:(page_current+ 1)*page_size
        #].to_dict('records')
    ShowingData = ShowingDF.to_dict('records')
    
    return [page_size]+[
        ShowingData]+[FilteredDF_json]+[len(FilteredDF)]

#=============================================================

args = []
#args.extend([Output('Constraint Dict', 'data')])
args.extend([Output('intermediate-value-RowConstraint', 'data')])
args.extend([Output("MinMaxRatio Bar", "value")])
args.extend([Output("nUniqueVal Bar", "value")])
args.extend([Input('Constraint Dict', 'data')])
args.extend([State('intermediate-value-RowConstraint', 'data')])
args.extend([State("MinMaxRatio Bar", "value")])
args.extend([State("nUniqueVal Bar", "value")])
@app.callback(*args)
def update_intermediate_value_RowConstraint(
        #RowConstraint_json,
        RowConstraintArray,
        RowConstraint_json,
        MinMaxRatio,
        nUniqueVal,
        ):
    '''
    更新篩濾條件字典json變數 intermediate-value-RowConstraint
    Constraint Dict有變動，則FilteredDF也會連帶變動，
    此情況下重設MinMaxRatio,nUniqueVal值
    '''
    RowConstraint = DataArrayToDict(RowConstraintArray)
    RowConstraint_json_new = json.dumps(RowConstraint, indent = 4)
    RowConstraint_Previous = json.loads(RowConstraint_json)
    if RowConstraint != RowConstraint_Previous:
        MinMaxRatio = [0, 1]
        nUniqueVal = [1,max(df.nunique())]
    return [RowConstraint_json_new]+[MinMaxRatio]+[nUniqueVal]

#=================================

args = []
args.extend([Output(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([Output("dropdown Constraint Pos", "value")])
args.extend([Input("Start Bar", "value")])
args.extend([Input('dropdown Constraint Value', 'value')])
args.extend([State('dropdown Constraint Pos', 'value')])
args.extend([State(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([State(f"pos {Start+i}-title", "children") for i in range(nFigs)])
@app.callback(*args)
def Add_Selection_Or_Clean(
            Start,
            SingleConsValue,
            ConsPos,
            *args
            ):
    def Add_Selection_Constraint_From_Dropdown(
            SingleConsValue,
            ConsPos,
            selectionList,
            titleList,
            ):

        if all(["POS" in ConsPos,SingleConsValue != None]):
            print("updating selectionList")
            #return selectionList
            Sel = selectionList[titleList.index(ConsPos)]
            if Sel == None:
                Sel = {}
            if 'points' not in Sel.keys():
                Sel['points'] = []
            Sel['points']+= [{'y':SingleConsValue}]
            selectionList[titleList.index(ConsPos)] = Sel
        else:
            print("ConsPos == None or SingleConsValue== None, Nothing change")
        return selectionList
    
    def selectionList_clean():
        selectionList = [None]*nFigs
        return selectionList
    
    selectionList = list(args)[0:nFigs]
    titleList = list(args)[nFigs:2*nFigs]
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    print("In up in va Row, button_id", button_id)
    if button_id in ["dropdown Constraint Value"]:
        selectionList = Add_Selection_Constraint_From_Dropdown(
            SingleConsValue, ConsPos, selectionList, titleList)
    elif button_id in [
            "Start Bar"]:
        selectionList = selectionList_clean()
    print("In Add_Selection_Or_Clean selectionList", selectionList)
    return selectionList+[""]
    

#=================================  
'''
@app.callback(
    Output('Constraint Dict', 'data'),
    Input('editing-Constraint-Dict-button', 'n_clicks'),
    State('Constraint Dict', 'data'),
    State('Constraint Dict', 'columns'))
def add_row(n_clicks, rows, columns):
    if n_clicks > 0:
        rows.append({c['id']: '' for c in columns})
    return rows
'''
#=================================  
args = []
args.extend([Output('Constraint Dict', 'data')])
#args.extend([Output(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([Input('editing-Constraint-Dict-button', 'n_clicks')])
args.extend([Input("CutRange Bar", "value")])
args.extend([Input("ChunkUnit Bar", "value")])
args.extend([Input("Stride Bar", "value")])
args.extend([Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([State(f"pos {Start+i}-title", "children") for i in range(nFigs)])
args.extend([State('Constraint Dict', 'data')])
args.extend([State('Constraint Dict', 'columns')])
@app.callback(*args)
def update_intermediate_value_RowConstraint_from_selection(
        #RowConstraintArray,
        n_clicks,
        CutRange,
        ChunkUnit,
        Stride,
        *args
        ):
    '''
    1.更新ChunkPramas時，重設RowsConstraint
    或
    2.將selectionList更新至Constraint Dict。
    '''
    selectionList = list(args)[0:nFigs]
    titleList = list(args)[nFigs:2*nFigs]
    RowConstraintArray =  list(args)[2*nFigs]
    columns =  list(args)[2*nFigs+1]
        
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    print("In up in va Row, button_id", button_id)
    if button_id in [
            "CutRange Bar","ChunkUnit Bar","Stride Bar"]:
        RowConstraint = {}
    elif button_id in [
            "editing-Constraint-Dict-button"]:
        if n_clicks > 0:
            RowConstraintArray.append({c['id']: '' for c in columns})
        return RowConstraintArray
    #elif button_id in [Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)]:
    else:
        #RowConstraint = {}
        RowConstraint = DataArrayToDict(RowConstraintArray)
        print("IN URV, updaint RowConstraint", RowConstraint)
        for j,selected_data in enumerate(selectionList):
            LabelsList = []
            print("In table j {},selected_data is {}".format(j,selected_data))
            if selected_data:# and selected_data['points']:
                print("selected_data", selected_data)
                for point in selected_data['points']:
                    print("j,label", j, point['y'])
                    LabelsList.append(point['y'])
                print("LabelsList", LabelsList)
                RowConstraint[titleList[j]] = LabelsList
                if LabelsList == []:
                    RowConstraint.pop("POS {}".format(j+Start))
                print("="*50)
        RowConstraint = UniqueConstraint(RowConstraint)
    RowConstraintArray = DictToDataArray(RowConstraint)
    #RowConstraint_json_new = json.dumps(RowConstraint, indent = 4)
    return RowConstraintArray#+[[None]*nFigs]



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

    app.run_server(debug=True, use_reloader=False, port = 8051)
    
