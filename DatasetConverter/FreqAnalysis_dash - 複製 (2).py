import time
import pandas as pd
import json

from MP_utils import MPlogger
from MP_utils import multicoreJob

from utilities import wrap
from utilities import ShowElapsedTime

from df_utils import dfOutputer

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



OFNM = "test_funnel"
Start = 0
MinMaxRatio = 1
MaxnUniqueVal = 16
ChunkUnit = 1
nFigs = 16
#nFigs_json = json.dumps(str(nFigs))
ConsPosNum = 0
nProcess= 1
page_current = 0
PAGE_SIZE = 10
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


def build_visualizations(df, Start,nFigs,MinMaxRatio,MaxnUniqueVal,RowConstraint = None):
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
        if  Ratio <= MinMaxRatio or len(numbers) < MaxnUniqueVal:
            figList.append(go.Figure(go.Funnel(y = terms,x =numbers)))
            titleList.append("POS {}".format(ChunkPos))
            nChosenFig +=1
        ChunkPos += 1
    if len(figList) < nFigs:
        figList.extend([go.Figure()]*(nFigs - len(figList)))
        titleList.extend([None]*(nFigs - len(titleList)))
    #print("in build vis, RowConstraint",RowConstraint)
# =============================================================================
#     ShowingRows = []
#     if RowConstraint is not None:
#         for key in RowConstraint.keys():
#             if key == None:
#                 continue
#             print(RowConstraint)
#             keyPos = int(key.split(" ")[1])
#             ConstList = RowConstraint[key]
#             Partdf = df.loc[df[keyPos].isin(ConstList)]
#             for i in range(Partdf.shape[0]):
#                 sent = ''.join((Partdf.iloc[i]).dropna())
#                 ShowingRows.append(sent)
#         
#     else:
#         for i in range(1):
#             sent = ''.join((df.iloc[i]).dropna())
#             ShowingRows.append(sent)
#         
#     print("in build ShowingRows[0:2]", ShowingRows[0:2])
#     #print(figList, titleList)
#     #print(figList, titleList)
#     ShowingRowsFig = go.Figure(
#         data=[go.Table(
#                 header=dict(values=['text']),
#                  cells=dict(
#                      values=[ShowingRows],
#                      line_color='darkslategray',
#                      fill_color='lightcyan',
#                      align='left',
#                      font_size=16,
#                      height=30)
#                  )
#               ])
# =============================================================================
    return figList, titleList#, ShowingRowsFig



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


def RowsFilter(RowConstraint = None):
    #df['index'] = range(1, len(df) + 1)
    ShowingRows = []
    #global df
    FilteredDF = df
    if RowConstraint != None:
        for key in RowConstraint.keys():
            if key == None or key == 'null':
                continue
            keyPos = int(key.split(" ")[1])
            ConstList = RowConstraint[key]
            FilteredDF = FilteredDF.loc[FilteredDF[keyPos].isin(ConstList)]
        for i in range(FilteredDF.shape[0]):
            sent = ''.join((FilteredDF.iloc[i]).dropna())
            ShowingRows.append(sent)
        

    #if len(ShowingRows) == 0:
        #sent = ''.join((df.iloc[0]).dropna())
        #ShowingRows.append(sent)
    ShowingDF = pd.DataFrame(ShowingRows, columns = ["text"])
    if ShowingDF.shape[0] > 0:
        #ShowingDF.columns = ["text"]
        ShowingDF[' index'] = range(1, len(ShowingDF) + 1)
        #print("ShowingDF\n", ShowingDF)
    dfOutputer(ShowingDF[["text"]], "test").run()
    return FilteredDF, ShowingDF

#FreqCountList = build_FreqCountList(ChunkUnit)
#visList = build_visualizationsOld(Start,nFigs,MinMaxRatio,MaxnUniqueVal)
df = build_ChunkDF(ChunkUnit)
FilteredDF_json = df.to_json(date_format='iso', orient='split')
FilteredDF, ShowingDF = RowsFilter()
#visList = build_visualizations(Start,nFigs,MinMaxRatio,MaxnUniqueVal)
#figList, titleList, ShowingRowsFig = build_visualizations(Start,nFigs,MinMaxRatio,MaxnUniqueVal)
figList, titleList = build_visualizations(FilteredDF, Start,nFigs,MinMaxRatio,MaxnUniqueVal)
#df[' index'] = range(1, len(df) + 1)

print(" in vis ShowingDF",ShowingDF)
page_size = PAGE_SIZE
ShowingData = ShowingDF.iloc[
        page_current*page_size:(page_current+ 1)*page_size
    ].to_dict('records')
#print("ShowingData", ShowingData)



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
        max=FilteredDF.shape[1]-nFigs, label="Start Point",
        value = 0),
    rc.CustomSlider(
        id="MinMaxRatio Bar", min=0, 
        max=1, label="Min-Max Ratio Upper Bound", step=0.01,
        value = 1),
    rc.CustomSlider(
        id="MaxnUniqueVal Bar", min=0, 
        max=32, label="Max number of Unique Value",
        value = 32),
    rc.CustomSlider(
        id="nFigs Bar", min=0, 
        max=256, label="Number of Figs",
        value = 16),
    #rc.CustomSlider(id="nLine", min=0, max=290, label="Number of Lines Once"),
    #rc.CustomSlider(id="ChunkUnit Bar", min=1, max=6, label="Chunk Unit"),
]



#print("Start", Start)
#FirstPos = int(titleList[0].split(" ")[1])

app.layout = html.Div([
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
                    ),
                ]
            ),
            #dbc.CardFooter("This is the footer"),
        ],
        color="info",
        style={"width": "30rem"},
    ),

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
    

    dbc.Card(
        [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(html.H2("Samples under Constraint:"),width=3),
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
    
    html.H1(children='Chunk Column Count'),
    html.H2("="*50),
    rc.Row([
        rc.Col(rc.Row([html.H2("Start = "),
        html.H2(id = "Start Pos", children=f'{Start}')]),width=3),
        rc.Col(rc.Row([html.H2("Min/Max-Ratio Upper Bound = "),
        html.H2(id = "Min-Max Ratio", children=f'{MinMaxRatio}')]),width=3),
        rc.Col(rc.Row([html.H2("Max number of Unique Value = "),
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
    
    dcc.Store(id='intermediate-value-FilteredDF',  data = FilteredDF_json),
    dcc.Store(id='intermediate-value-RowConstraint',  data = RowConstraint_json),
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


args = []
args.extend([Output(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([Input("Start Bar", "value")])
@app.callback(*args)
def selectionList_clean(
        Start):
    selectionList = [None]*nFigs
    return selectionList#+ dropdownConsPosList+dropdownConsValueList#+[ShowingRows]+[ShowingData]



args = []
args.extend([Output("Start Pos", "children")])
args.extend([Output("Min-Max Ratio", "children")])
args.extend([Output("MaxnUniqueVal", "children")])
args.extend([Output(f"pos {Start+i}-graph", "figure") for i in range(nFigs)])
args.extend([Output(f"pos {Start+i}-title", "children") for i in range(nFigs)])
#args.extend([Output(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([Input("Start Bar", "value")])
args.extend([Input("MinMaxRatio Bar", "value")])
args.extend([Input("MaxnUniqueVal Bar", "value")])
args.extend([Input('intermediate-value-nFigs', 'data')])
args.extend([Input('intermediate-value-FilteredDF', 'data')])


@app.callback(*args)
def vis_update(
        Start,MinMaxRatio,MaxnUniqueVal, nFigs, FilteredDF_json):
    #global titleList
    FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    print("In vis, *args", *args)
    #print("*selectionList", selectionList)
    #figList, titleList, ShowingRows = build_visualizations(
    figList, titleList = build_visualizations(
        FilteredDF, Start,nFigs,MinMaxRatio,MaxnUniqueVal)
    print("In vis, titleList", titleList)


    selectionList = [None]*nFigs
    return [Start,MinMaxRatio,MaxnUniqueVal
            ]+figList+ titleList#+selectionList#+ dropdownConsPosList+dropdownConsValueList#+[ShowingRows]+[ShowingData]


args = []
args.extend([Output("dropdown Constraint Pos", "options")])
args.extend([Output("dropdown Constraint Value", "options")])
#args.extend([Output("ShowingRowsTable-graph", "figure")])
args.extend([Output('datatable-paging', 'data')])
args.extend([Output('datatable-paging', "page_size")])
args.extend([Output('Constraint Dict', 'data')])
args.extend([Output('intermediate-value-RowConstraint', 'data')])
args.extend([Output('intermediate-value-FilteredDF', 'data')])
args.extend([Input("Start Bar", "value")])
args.extend([Input('dropdown Constraint Pos', 'value')])
args.extend([Input('dropdown Constraint Value', 'value')])
args.extend([Input('datatable-paging', "page_current")])
args.extend([Input("Page Size Bar", "value")])
args.extend([Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)])
args.extend([State(f"pos {Start+i}-title", "children") for i in range(nFigs)])
args.extend([State('intermediate-value-RowConstraint', 'data')])
args.extend([State('intermediate-value-FilteredDF', 'data')])

'''
argws = {
    "titleList":[Input(f"pos {Start+i}-title", "children") for i in range(nFigs)],
    "selectionList":[Input(f"pos {Start+i}-graph", "selectedData") for i in range(nFigs)],
    "ConsPos":Input('dropdown Constraint Pos', 'value'),
         "SingleConsValue":Input('dropdown Constraint Value', 'value'),
         "page_current":Input('datatable-paging', "page_current"),
         "page_size":Input('datatable-paging', "page_size"),
         }
'''
#print("argws", argws)
@app.callback(*args)
def table_update(
        Start,
        ConsPos,
        SingleConsValue,
        #RowConstraint_json,
        page_current, page_size,
        #RowConstraint_json,
        *args):
        #):
    #global RowConstraint
    RowConstraint_json = list(args)[2*nFigs]
    RowConstraint = json.loads(RowConstraint_json)
    FilteredDF_json = list(args)[2*nFigs+1]
    FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    #print("In table init, RowConstraint", RowConstraint)
    #titleList = list(args)[0:nFigs]
    #selectionList = list(args)[nFigs:2*nFigs]
    selectionList = list(args)[0:nFigs]
    titleList = list(args)[nFigs:2*nFigs]

    #print("In table selectionList", selectionList)
    
    if ConsPos is not None:
        ConsPosNum = int(ConsPos.split(" ")[1])
    else:
        ConsPosNum = 0

    #print("selection1", selection1)
    LabelsList = []
    #Posj = 0
    #for selected_data in [selection1]:
    
    #RowConstraint = {}
    print("In table RowConstraint b4", RowConstraint)
    if SingleConsValue != None:
        RowConstraint[ConsPos] = [SingleConsValue]
    for j,selected_data in enumerate(selectionList):
        LabelsList = []
        print("In table j,selected_data", j,selected_data)
        if selected_data:# and selected_data['points']:
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

    print("RowConstraint", RowConstraint)
    
    

    
    dropdownConsPosList = [[{'label': i, 'value': i} for i in titleList]]
    dropdownConsValueList = [[
        {'label': i, 'value': i} 
        for i in list(dict(df[ConsPosNum].value_counts()).keys())]]
    #figList, titleList, ShowingRows = build_visualizations(
    FilteredDF, ShowingDF = RowsFilter(RowConstraint)
    #figList, titleList = build_visualizations(
        #FilteredDF, Start,nFigs,MinMaxRatio,MaxnUniqueVal, RowConstraint=RowConstraint)
    
    #print(" in vis ShowingDF",ShowingDF)
    ShowingData = ShowingDF.iloc[
            page_current*page_size:(page_current+ 1)*page_size
        ].to_dict('records')
    #print("ShowingData", ShowingData)
    #print("In table RowConstraint",RowConstraint)
    #RowConstraintDF = pd.DataFrame(data = RowConstraint)
    #RowConstraintDF = pd.DataFrame(columns = ["POS", "Constraint"], data = {"a":3,"b":4})
    #print("In table RowConstraintDF",RowConstraintDF)
    RowConstraintArray = []
    for key in RowConstraint.keys():
        if key == None or key == 'null':
            continue
        RowConstraintArray.append(
            {"POS": key.split(" ")[1], "Constraint":str(RowConstraint[key])})
    print("In table, RowConstraintData", RowConstraintArray)
    RowConstraint_json = json.dumps(RowConstraint, indent = 4)
    print("In table RowConstraint_json", RowConstraint_json)
    FilteredDF_json = FilteredDF.to_json(date_format='iso', orient='split')
    return dropdownConsPosList+dropdownConsValueList+[
        #ShowingRows]+[
            ShowingData]+[page_size]+[RowConstraintArray]+[
                RowConstraint_json]+[FilteredDF_json]#+[RowConstraint]




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
    
