import time
import pandas as pd
import json
import ast

from MP_utils import MPlogger
#from MP_utils import multicoreJob

from utilities import wrap
from utilities import ShowElapsedTime
from utilities import OffsetWrap

from df_utils import dfOutputer

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
        "POS Offset": POSOffset,
        }
    ChunkParamsDF = pd.DataFrame(
        ChunkParamsDict.items(), columns=['parameter', 'value'])
    ChunkParamsDF = ChunkParamsDF.set_index('parameter')
    ChunkParamsDF_json = ChunkParamsDF.to_json(date_format='iso', orient='split')
    return VisParamsDF, VisParamsDF_json, ChunkParamsDF, ChunkParamsDF_json

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
POSOffset = ChunkUnit
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
        ChunkUnit, POSOffset, 
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
            sentWrap = OffsetWrap(sent, POSOffset, ChunkUnit)
            rowlist.append(sentWrap)
    print("Finished building the rowlist.")
    ShowElapsedTime(start_time)
    print("Start to transform rowlist to Dataframe")
    df = pd.DataFrame(rowlist)
    print("Finished build Chunk DataFrame.")
    ShowElapsedTime(start_time)   
    ChunkParamsDF.loc["CutRange","value"] = str(CutRange)
    ChunkParamsDF.loc["Chunk Unit","value"] = ChunkUnit
    ChunkParamsDF.loc["POS Offset","value"] = POSOffset
    print("In build ChunkParamsDF", ChunkParamsDF)
    return df, ChunkParamsDF

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
    print("In build VisParamsDF", VisParamsDF)
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


def RowsFilter(df, RowConstraint = None):
    ShowingRows = []
    FilteredDF = df
    print("In RowF, RowConstraint", RowConstraint)
    if RowConstraint != None:
        for key in RowConstraint.keys():
            if key == None or key == '':
                continue
            keyPos = int(key.split(" ")[1])
            ConstList = RowConstraint[key]
            print("In RowF, keyPos=", keyPos)
            FilteredDF = FilteredDF.loc[FilteredDF[keyPos].isin(ConstList)]
        for i in range(FilteredDF.shape[0]):
            sent = ''.join(str(x) for x in (FilteredDF.iloc[i]).dropna())
            #sent = ''.join((FilteredDF.iloc[i]).dropna())
            ShowingRows.append(sent)
    #先用List:ShowingRows蒐集串接後的還原text，再轉成ShowingDF。
    ShowingDF = pd.DataFrame(ShowingRows, columns = ["text"])
    if ShowingDF.shape[0] > 0:
        ShowingDF['index'] = range(1, len(ShowingDF) + 1)
    if ShowingDF.shape[0] < 10000:
        dfOutputer(ShowingDF[["text"]], "test").run()
    return FilteredDF, ShowingDF

df, ChunkParamsDF = build_ChunkDF(ChunkUnit, POSOffset, CutRange)
df_json = df.to_json(date_format='iso', orient='split')
FilteredDF_json = df_json
FilteredDF, ShowingDF = RowsFilter(df)
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
        #max=len(FreqCountList)-nFigs, label="Start Point"),
        max=df.shape[1]-nFigs, label="Start Point",
        value = 0),
    #rc.CustomSlider(
        #id="MinMaxRatio Bar", min=0, 
        #max=1, label="Min-Max Ratio Upper Bound", step=0.01,
        #value = 1),
    rc.CustomRangeSlider(
        id="MinMaxRatio Bar", min=0, 
        max=1, label="Min-Max Ratio Bound", step=0.01,
        value = MinMaxRatio),
    #rc.CustomSlider(
        #id="MaxnUniqueVal Bar", min=0, 
        #max=max(df.nunique()), label="Max number of Unique Value",
        #value = 64),
    rc.CustomRangeSlider(
        id="nUniqueVal Bar", min=1, 
        max=max(df.nunique()), label="number of Unique Value", step=1,
        value = nUniqueVal),
]
controls2 = [
    rc.CustomRangeSlider(
        id="CutRange Bar", min=0, 
        max=df.shape[1], label="CutRange", step=1,
        value = CutRange),
    rc.CustomSlider(
        id="ChunkUnit Bar", min=0, 
        max=16, label="ChunkUnit",
        value = ChunkUnit),
    rc.CustomSlider(
        id="POSOffset Bar", min=0, 
        max=16, label="POS Offset",
        value = POSOffset),
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
                            ),
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
                    dbc.CardBody(
                        [
                        dash_table.DataTable(
                            id='Chunk Params',
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
    
    #html.H1(children='Chunk Column Count'),
    #html.H2("="*50),
    #rc.Row([
        #rc.Col(rc.Row([html.H2("Start = "),
        #html.H2(id = "Start Pos", children=f'{Start}')]),width=3),
        #rc.Col(rc.Row([html.H2("Min/Max-Ratio Bound = "),
        #html.H2(id = "Min-Max Ratio", 
                #children='"["{},{}"]"'.format(MinMaxRatio[0],MinMaxRatio[1]))]),width=3),
        #rc.Col(rc.Row([html.H2("Max number of Unique Value = "),
        #html.H2(id = "MaxnUniqueVal", children=f'{MaxnUniqueVal}')]),width=3),
        #]),
#    rc.Row([
        #rc.Col(html.H2(id = "nLines", children=f'Number of Chunks Once = {nFigs}'),width=3),
        #rc.Col(rc.Row([html.H2("ChunkUnit = "),
        #html.H2(id = "ChunkUnit", children=f'{ChunkUnit}')]),width=3),
        #]),
    #rc.Row([
        #rc.Col(rc.Row([html.H2("POS Offset = "),
        #html.H2(id = "POS Offset", children=f'{POSOffset}')]),width=3),

        #rc.Col(html.H2(id = "ChunkUnit", children=f'Chunk Unit = {ChunkUnit}'),width=3),
        #]),
    #html.Div([html.H2("Start ="),
        #html.H2(id = "Start Pos", children=f'{Start}')]),
    #html.H2("="*50),
    #html.H2(id = "nLines", children=f'Number of Lines Once = {nFigs}'),
    #html.H2(id = "ChunkUnit", children=f'Chunk Unit = {ChunkUnit}'),

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
args.extend([Output('Chunk Params', 'data')])
args.extend([Input("CutRange Bar", "value")])
args.extend([Input("ChunkUnit Bar", "value")])
args.extend([Input("POSOffset Bar", "value")])
@app.callback(*args)
def ChunkDF_update(
        CutRange, ChunkUnit, POSOffset):
    df, ChunkParamsDF = build_ChunkDF(ChunkUnit, POSOffset, CutRange)
    df_json = df.to_json(date_format='iso', orient='split')

    ChunkParamsDF = ChunkParamsDF.reset_index()
    #VisParamsDF.columns = ['parameter', 'value']
    ChunkParamsDFData = []
    ChunkParamsDFData = [{'parameter':x[0],
                     'value':x[1]} for x in dict(ChunkParamsDF.values).items()]
    
    return [df_json, ChunkParamsDFData]#,FilteredDF_json]



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
    FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    VisParamsDF = pd.read_json(VisParamsDF_json, orient='split')
    figList, titleList, VisParamsDF = build_visualizations(
        FilteredDF, Start,nFigs,MinMaxRatio,nUniqueVal, VisParamsDF)

    
    dropdownConsPosList = [
        {'label': i, 'value': i} for i in list(filter(None, titleList))]
    VisParamsDF = VisParamsDF.reset_index()
    #VisParamsDF.columns = ['parameter', 'value']
    print("In vsi VisParamsDF\n", VisParamsDF)
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
    FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    vcnt = dict(FilteredDF[ConsPosNum].value_counts())
    value_sorted = sorted(
        vcnt.keys(), key = lambda i: vcnt[i], reverse = True)
    dropdownConsValueList = [{'label': i, 'value': i} 
        for i in value_sorted]
    return dropdownConsValueList

#=================================
#當篩濾條件RowConstraint變動時，
#更新符合條件的樣本之表格(Samples under Constraint)及更新下拉Constrain選項
#並更新FilteredDF變數
args = []
args.extend([Output('datatable-paging', "page_size")])
args.extend([Output('datatable-paging', 'data')])
#args.extend([Output("dropdown Constraint Pos", "options")])
#args.extend([Output("dropdown Constraint Value", "options")])
args.extend([Output('intermediate-value-FilteredDF', 'data')])
args.extend([Output('nSamples', 'children')])
args.extend([Input('datatable-paging', "page_current")])
args.extend([Input("Page Size Bar", "value")])
args.extend([Input('intermediate-value-df', 'data')])
args.extend([Input('Constraint Dict', 'data')])
#args.extend([State('intermediate-value-RowConstraint', 'data')])
#args.extend([State('intermediate-value-FilteredDF', 'data')])
#args.extend([State(f"pos {Start+i}-title", "children") for i in range(nFigs)])
#TODO 建立RowConstraintArray轉為RowConstraint字典的功能後，即可略去
#[State('intermediate-value-RowConstraint', 'data')]
@app.callback(*args)
def table_update(
        page_current,
        page_size,
        df_json,
        RowConstraintArray,
        #RowConstraint_json,
        #FilteredDF_json,
        *args
        ):
    #print("*args", *args)
    print("len(*args)", len(args))
    #RowConstraint_json = list(args)[0]
    
    #print("RowConstraint_json", RowConstraint_json)
    #RowConstraint = json.loads(RowConstraint_json)
    #print("RowConstraint 1", RowConstraint)
    df =  pd.read_json(df_json, orient='split')
    RowConstraint = {}
    for x in RowConstraintArray:
        RowConstraint['POS '+x['POS']] = ast.literal_eval(x['Constraint'])
        #print("In RowConstraintArray x", x)
    print("RowConstraint", RowConstraint)
#{'POS': '0', 'Constraint': "['h', 'o', 'w', 'i', 'y', 'c', 'b']"}
    print("IN, TU, df", df)
    FilteredDF, ShowingDF = RowsFilter(df, RowConstraint)
    FilteredDF_json = FilteredDF.to_json(date_format='iso', orient='split')
    ShowingData = ShowingDF.iloc[
            page_current*page_size:(page_current+ 1)*page_size
        ].to_dict('records')
    
    return [page_size]+[
        ShowingData]+[FilteredDF_json]+[len(FilteredDF)]
        
#=================================  
#更新篩濾條件字典變數Constraint Dict
args = []
args.extend([Output('Constraint Dict', 'data')])
args.extend([Output("MinMaxRatio Bar", "value")])
args.extend([Output("nUniqueVal Bar", "value")])
args.extend([Input('intermediate-value-RowConstraint', 'data')])
args.extend([Input('intermediate-value-RowConstraint_Previous', 'data')])
args.extend([State("MinMaxRatio Bar", "value")])
args.extend([State("nUniqueVal Bar", "value")])
@app.callback(*args)
def update_Constraint_Dict(
        RowConstraint_json,
        RowConstraint_Previous_json,
        MinMaxRatio,
        nUniqueVal,
        ):
    RowConstraint = json.loads(RowConstraint_json)
    RowConstraintArray = []
    for key in RowConstraint.keys():
        if key == None or key == 'null':
            continue
        RowConstraintArray.append(
            {"POS": key.split(" ")[1], "Constraint":str(RowConstraint[key])})
    print("In update_Constraint_Dict, RowConstraintData: \n", RowConstraintArray)
    #return [RowConstraintArray]
    #RowConstraintArray = [{'POS': '0', 'Constraint': "['a', 's', 'h', 'o', 'w', 'i', 'y', 'c', 'b', 'r']"}]
    if RowConstraint_json != RowConstraint_Previous_json:
        MinMaxRatio = [0, 1]
        nUniqueVal = [1,max(df.nunique())]
    return [RowConstraintArray]+[MinMaxRatio,nUniqueVal]

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
args = []
args.extend([Output('intermediate-value-RowConstraint', 'data')])
args.extend([Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([State('intermediate-value-RowConstraint', 'data')])
args.extend([State("Start Bar", "value")])
args.extend([State(f"pos {Start+i}-title", "children") for i in range(nFigs)])
@app.callback(*args)
def update_intermediate_value_RowConstraint_from_selection(
        *args
        ):
    selectionList = list(args)[0:nFigs]
    print("IN UNVIRFS selectionList", selectionList)
    RowConstraint_json = list(args)[nFigs]
    RowConstraint = json.loads(RowConstraint_json)
    Start = list(args)[nFigs+1]
    titleList = list(args)[nFigs+2:2*nFigs+2]
    print("IN iVR, titleList", titleList)
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
            #print("In table Start", Start)
            #RowConstraint["POS {}".format(j+Start)] = LabelsList
            if LabelsList == []:
                #RowConstraint.pop("POS {}".format(j+Start))
                RowConstraint.pop(titleList[j])
            print("="*50)
    RowConstraint_json = json.dumps(RowConstraint, indent = 4)
    return RowConstraint_json


'''
#=================================  
args = []
#args.extend([Output("dropdown Constraint Pos", "options")])
#args.extend([Output("dropdown Constraint Value", "options")])
args.extend([Output('intermediate-value-RowConstraint', 'data')])
#args.extend([Output("dropdown Constraint Pos", "options")])
#args.extend([Output("dropdown Constraint Value", "options")])
args.extend([Output(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([Input('dropdown Constraint Pos', 'value')])
args.extend([Input('dropdown Constraint Value', 'value')])
#args.extend([Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([State('intermediate-value-RowConstraint', 'data')])
args.extend([State(f"pos {Start+i}-title", "children") for i in range(nFigs)])
args.extend([State(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
@app.callback(*args)
def update_intermediate_value_RowConstraint(
        ConsPos,
        SingleConsValue,
        #RowConstraint_json,
        *args,):
    def Add_Constraint_From_Dropdown(
            ConsPos,
            SingleConsValue,
            RowConstraint,
            titleList,
            selectionList
            ):
        if SingleConsValue != None:
            RowConstraint[ConsPos] = [SingleConsValue]
        Sel = selectionList[titleList.index(ConsPos)]
        if Sel == None:
            Sel = {}
        print("tar sel loc", titleList.index(ConsPos))
        print("SingleConsValue",SingleConsValue)
        if 'points' not in Sel.keys():
            Sel['points'] = []
        #for y in SingleConsValue:
        Sel['points']+= [{'y':SingleConsValue}]
        print("selectionList", selectionList)
        return RowConstraint,selectionList
    
    print("list(args)[nFigs]", list(args)[nFigs])
    RowConstraint_json = list(args)[nFigs]
    RowConstraint = json.loads(RowConstraint_json)
    ctx = dash.callback_context
    #titleList = list(args)[0:nFigs]
    #selectionList = list(args)[nFigs:2*nFigs]
    selectionList = list(args)[0:nFigs]
    titleList = list(args)[nFigs+1:2*nFigs+1]
    print("In UIVR, selectionList", selectionList)
    if not ctx.triggered:
        button_id = 'No clicks yet'
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    print("In up in va Row, button_id", button_id)
    if button_id in [
            "dropdown Constraint Pos", "dropdown Constraint Value"]:
        RowConstraint, selectionList = Add_Constraint_From_Dropdown(
            ConsPos,
            SingleConsValue,
            RowConstraint,
            titleList,
            selectionList,
            #*args,
            )
    RowConstraint_json = json.dumps(RowConstraint, indent = 4)
    return RowConstraint_json+selectionList#dropdownConsPosList+dropdownConsValueList
'''

'''
#=================================  
args = []
#args.extend([Output("dropdown Constraint Pos", "options")])
#args.extend([Output("dropdown Constraint Value", "options")])
args.extend([Output('intermediate-value-RowConstraint', 'data')])
#args.extend([Output("dropdown Constraint Pos", "options")])
#args.extend([Output("dropdown Constraint Value", "options")])
#args.extend([Output(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
@app.callback(*args)
def PrintSel(*args):
    selectionList = list(args)[0:nFigs]
    print("selectionList", selectionList)
    for j,selected_data in enumerate(selectionList):
        LabelsList = []
        print("In table j,selected_data", j,selected_data)
        if selected_data:# and selected_data['points']:
            print("selected_data", selected_data)
            for point in selected_data['points']:
                print("j,label", j, point['y'])
                LabelsList.append(point['y'])
            print("LabelsList", LabelsList)
            #RowConstraint[titleList[j]] = LabelsList
            print("In table Start", Start)
            RowConstraint["POS {}".format(j+Start)] = LabelsList
            if LabelsList == []:
                RowConstraint.pop("POS {}".format(j+Start))
            print("RowConstraint in table", RowConstraint)
            print("="*50)
#=================================
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

    app.run_server(debug=True, use_reloader=False, port = 8051)
    
