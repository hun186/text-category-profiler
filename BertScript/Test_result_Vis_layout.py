from PackageImport import PackageImporter
PackageImporter.proc()

import uuid
import shutil
import os

import dash
from dash import dash_table
import dash_bootstrap_components as dbc
from dash import dcc
from dash import html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_pivottable
import dash_uploader as du
import reusable_components as rc  # see reusable_components.py
from flask import request

from utils.utilities import timeNow
from utils.utilities import MKDIR
from utils.TCF_utils import get_finished_date_dir_dict
from utils.df_utils import dfOutputer

from utils.Dash_utils import get_upload_component
from utils.Dash_utils import Build_DataArrayTable

def Build_Upload_Block(date_session_id,UploadedFilename,VisSelfFinishedState):
    # if args.VisSelfService == True:        
    #     CardHeader = html.H2("Upload zip file compressing txt corpus to analysis")
    #     UPLoad_Drag = get_upload_component(
    #                     id='dash-uploader',
    #                     filetypes=['zip'],
    #                     max_file_size=40,
    #                     upload_id = date_session_id)
    #     btn = html.Button("下載自行上傳推論功能之範例檔",
    #                       id="btn_dataset_samples")
    # else:
    #     CardHeader = html.H2()
    #     UPLoad_Drag = html.H2(id='dash-uploader')
    #     btn = html.H2()
    print("Start to Run Build_Upload_Block")
    #CardHeader = html.H2("Upload zip file compressing txt corpus to analysis")
    
    #CardHeader = html.H2([
    #"Upload a zip file smaller than 40MB for text analysis. The compressed file supports text file types such as pdf, docx, xlsx, txt, etc. The text file names should be in ",
    #html.Span("Traditional Chinese or English", style={'color': 'red'}),
    #"."
    #])
    CardHeader = html.H2("Upload a .7z or .zip file under 40MB for text analysis. Supported formats include .pdf, .docx, .xlsx, .txt. 7z is recommended for better handling of non-English filenames.")
    
    UPLoad_Drag = get_upload_component(
                    id='dash-uploader',
                    filetypes=['zip','7z'],
                    #filetypes=['rar'],
                    max_file_size=40,
                    upload_id = date_session_id)#+"_is_running_DataConverter")
    btn = html.Button("下載自行上傳推論功能之範例檔",
                      id="btn_dataset_samples")
    print("Finished Running Build_Upload_Block")
    return dbc.Card(
                [
                dbc.CardHeader(CardHeader),
                dbc.CardBody(
                    rc.Row([
                        UPLoad_Drag,
                        rc.Col(rc.Row([btn,
                                       dcc.Download(id="download-dataset-samples")
                                       ]),width=3),
                        rc.Col(rc.Row([html.H2(id='Uploaded Filename', children=f'{UploadedFilename}'),
                                       ]),width=3),
                        rc.Col(rc.Row([html.H2(id='Vis Self Finished State', children=f'{VisSelfFinishedState}'),
                                       ]),width=3),
                        ])
                    ),
                html.Hr(),
                ],
                color="warning",
                style={"width": "12"},
                )

def Build_Finished_Task_Block(port,datasetDir_VisSelf="WorkPool_VisSelfService"):
    print("Start to Run Build_Finished_Task_Block")
    date_dir_dict = get_finished_date_dir_dict(port=port,datasetDir_VisSelf=datasetDir_VisSelf)
    return dbc.Card(
                [
                dbc.CardHeader(html.H2("已完成自定任務")),
                dbc.CardBody(
                    rc.Row([
                        rc.Col(dcc.Dropdown(
                            id='FinishedTask',
                            options=[{'label': key, 'value': val} 
                                     for key,val in date_dir_dict.items()],
                            #value="2024"
                            ),width = 3),
                        ])
                    ),
                html.Hr(),
                ],
                color="success",
                style={"width": "12"},
                )
        
'''
#KeyWordDataArray = [{"Key Word":"一路"},]
#print("LabelList", LabelList)
#raise Exception
ColorDict["可於此格手動輸入特定分類名"] = '#FFFFFF'
ColorDict["Scrap"] = '#E3E4E1'
colorIndex = 0
for label in LabelList:
    if label == "Scrap":
        continue
    else:
        #ColorDict[label] = cms.pop()
        ColorDict[label] = cms[colorIndex]
        colorIndex += 1
        colorIndex = colorIndex % len(cms)
print("ColorDict", ColorDict)
   
ColorDF = ColorDictToColorDF(ColorDict)
ColorDF = BuildColorDF(ColorDict,ClassTable)
ColorDF_json = ColorDF.to_json(date_format='iso', orient='split')

Colortable_style_data_conditional=[
    {'if': {'row_index': i, 'column_id': 'Color'}, 
     'background-color': ColorDF['Color'][i],
     'color': ColorDF['Color'][i]} 
    for i in range(ColorDF.shape[0])
    ]

#print("df['Date']",df['Date'])
selectedLabels = []
selectedLabels_json = json.dumps(selectedLabels, indent = 4)
style_data_conditional,style_cell_conditional,style_cell,tooltip_data \
    = Build_VisDatatable_style(df, ColorDict, BinMissionDict)
'''

def serve_layout(
        args,datasetDir,df,PreambleCols,
        ColorDF_json,KeyWordDataArray):
#def serve_layout(datasetDir):
    session_id = str(uuid.uuid4())
    
    #session_id = hash(str(random.randint(1,10000)))
    if args.VisSelfService == True:
        SessionDatasetDir = os.path.join(
            datasetDir,timeNow(FMT = "%Y-%m%d-%H%M-")+session_id)
        src = os.path.join(datasetDir,"test_results_verification.sql3")
        des = os.path.join(SessionDatasetDir,"test_results_verification.sql3")
        MKDIR(SessionDatasetDir)
        shutil.copyfile(src,des)
        
    else:
        SessionDatasetDir = datasetDir
        
    FilteredDF_OPTFN = os.path.join(SessionDatasetDir,"FilteredPreambleCols_df")
    DF_OPTFN = os.path.join(SessionDatasetDir,"DFPreambleCols_df")
    dfOutputer(df[PreambleCols],DF_OPTFN).run()
    
    PiecesBound = [1, 100]
    controls2 = [
        rc.CustomRangeSlider(
            id="PiecesBound", min=1, 
            #max=max(nDigitCols,1), 
            max=100, 
            label="Bound for Satisfying Blocks With the label checklist",
            step=1,
            value = PiecesBound),
    ]
    
    return html.Div([
    # =============================================================================
    #         html.P("Medals included:"),
    #         dcc.Checklist(
    #             id='medals',
    #             options=[{'label': x, 'value': x} 
    #                      for x in df.columns],
    #             value=df.columns.tolist(),
    #         ),
    #         dcc.Graph(id="graph"),
    #         
    # =============================================================================
        #dbc.Tooltip([
            #html.P("A first line"),
            #html.P("A second line.")
            #]),
    # =============================================================================
    # 
    #     html.Label('Dropdown'),
    #     dcc.RadioItems(
    #         id='Colortable_toggle',
    #         options=[{'label': i, 'value': i} for i in ['Show', 'Hide']],
    #         value='Show'
    #     ),
    # 
    # =============================================================================
        #dcc.Dropdown(
            #id='dropdown',
            #options=[{'label': 'Colortable for Labels', 'value': 'Colortable'},
                     #{'label': 'Predicting Result Summary', 'value': 'Summary'}],
            #value='Colortable'),
        
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                html.H2("Auto Select SubTopics: "),
                rc.Col(dcc.Dropdown(
                    id='AutoSelectSubTopics',
                    options=[{'label': i, 'value': i} 
                             for i in ["Yes","No"]],
                    value="Yes"
                ),width = 3),
                #rc.Col(html.H2("Samples Predictions:"),width=3),
                rc.Col(
                    rc.Card(rc.CardContent(rc.Row([rc.Col(c, width=3) for c in controls2]))),
                    #rc.Row([html.H2("total Number:"),
                               #html.H2(id = "nSamples", children=f'{nSamples}')
                               #]),
                    width=6),
                    ])
                ),
            #html.Hr(),
            #html.Div(id='datatable-query-structure', style={'whitespace': 'pre'})
            ],
            style={"width": "12"},
            ),
        rc.Row([
            rc.Col(
                html.Details([
                    html.Summary('Key Words'),
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H2("KeyWordTable")),
                                dbc.CardBody(
                                    id="KeyWordTableCard",
                                    children = [
                                        Build_DataArrayTable(
                                            "KeyWordTable",KeyWordDataArray,
                                            ShownColumns=['Key Word'])
                                    ]
                                    ),
                            ],
                            color="warning",
                            style={"width": "35rem"},
                        )
                ], open = True),
                width=3
            ),
        ]),
        rc.Row([
            rc.Col(
                html.Details([
                    html.Summary('Topics of Missions'),
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H2("MissionTable")),
                                dbc.CardBody(
                                    id="MissionTableCard",
                                    children = [
                                        Build_DataArrayTable(
                                            "MissionTable",MissionDataArray,
                                            ShownColumns=['Mission', 'Expiry Date', 'Topics', 'Key Word'],
                                            style_cell=MT_style_cell,
                                            style_cell_conditional=MT_style_cell_conditional
                                            )
                                    ]
                                ),
                            ],
                            color="primary",
                            #style={"width": "35rem"},
                        )
                ], open = True),
                width=9
            ),
        ]),
        
        rc.Row([
            rc.Col(
                html.Details([
                    html.Summary('Label of the item'),
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H2("Colortable for Labels")),
                                dbc.CardBody(
                                    id="ColortableCard",
                                    children = [
                                        #Build_ColorTable(ColorDict)
                                        Build_ColorTable(ColorDF)
                                        #Build_DataArrayTable(
                                            #"Colortable",ColorDF.to_dict('records'),
                                            #ShownColumns=['Color', 'Label', 'InfoScore', 'Chinese', 'Explaination'],
                                            #style_cell=Colortable_style_cell,
                                            #style_cell_conditional=Colortable_style_cell_conditional,
                                            #style_data_conditional=Colortable_style_data_conditional,
                                            #) 
                                    ]
                                    ),
                            ],
                            color="warning",
                            #style={"width": "35rem"},
                        )
                ], open = True),
                width=9
            ),
        ]),
    
        rc.Row([
            rc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(html.H2("Predicting Result Summary")),
                        dbc.CardBody(
                            id="PredResSummaryCard",
                            children = Build_Pred_Block(FilteredDF, sql3File, ColorDict),#, SrcList=SrcList),
                            #children = [dcc.Graph(
                                #id="Sunburst-graph",
                                #figure=Build_Pred_Sunburst(PartColDF, ColorDict))],
                            #),
                        ),
                    ],
                    color="success",
                    #style={"width": "90rem"},
                ),
                width = 9)
        ]),
        
        rc.Row([
            rc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(html.H2("Showing File PivotTable")),
                        dbc.CardBody(
                            id="ShowingFilePVTCard",
                            #children = Build_PVT_Block(FileList=ShowingFile),
                            #children = [dcc.Graph(
                                #id="Sunburst-graph",
                                #figure=Build_Pred_Sunburst(PartColDF, ColorDict))],
                            #),
                        ),
                    ],
                    color="success",
                    #style={"width": "90rem"},
                ),
                width = 9)
        ]),
        
        rc.Row(
            rc.Col(
                rc.Card(rc.CardContent(rc.Row([rc.Col(c, width=3) for c in controls1]))),
                width=12,
            )
        ),
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(html.H2("Samples Predictions:"),width=3),
                rc.Col(rc.Row([html.H2("total Number:"),
                               html.H2(id = "nSamples", children=f'{nSamples}')]),width=3),
                rc.Col(rc.CustomSlider(
                    id="Page Size Bar", min=0, 
                    max=1000, label="Page Size",
                    value = PAGE_SIZE),width=6),
                rc.Col(rc.Row([html.H2("目前所在頁數:"),
                               html.H2(id = "current page", children=f'{current_page}')]),width=3),
                    ])
                ),
            dbc.CardBody(
                id="VisDatatableCard",
                #children = Build_VisDatatable(PartColDF, ColorDict, BinMissionDict,InfoScoreTable)[0],
                children = Build_VisDatatable(FilteredDF, sql3File, ColorDict, BinMissionDict,InfoScoreTable,FilteredDF_OPTFN=FilteredDF_OPTFN)[0],
                ),
            html.Hr(),
            #html.Div(id='datatable-query-structure', style={'whitespace': 'pre'})
            ],
            style={"width": "12"},
            ),
        dbc.Card(
            [
                dbc.CardHeader(html.H2("Select Topics List:")),
                dbc.CardBody(
                    children = Build_selectLabelsTable(),
                ),
                #dbc.CardFooter("This is the footer"),
            ],
            color="info",
            style={"width": "35rem"},
        ),
        
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(rc.Row([html.H2("輸入原始數量:"),
                               html.H2(children=f'{LenSrcList}')
                               ]),width=3),
                rc.Col(rc.Row([html.H2("篩選後數量:"),
                               html.H2(id = "nSamples_bottom",children=f'{nSamples}')
                               ]),width=3),
                rc.Col(rc.Row([html.Button('取代篩選源dataframe', id='ReplaceDF', n_clicks=0),
                               ]),width=3),
                rc.Col(rc.Row([html.H2(id='MessageBox', children=f'{SystemMessage}'),
                               ]),width=3),
                    ])
                ),
            html.Hr(),
            ],
            style={"width": "12"},
            ),
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(rc.Row([html.H2(
                    f'篩選源初始篩選條件: (下限:{args.InfoScoreSumLowerBound}及上限:{args.InfoScoreSumUpperBound}) 或 Selected'
                                ),
                                html.H2(
                    f'篩選使用方法：於表格欄位最上方之空格輸入篩選條件，如: ">500"或關鍵字，按下Enter，在格子外面點一下滑鼠。'
                                )
                               ]),width=12),
                    ])
                ),
            html.Hr(),
            ],
            style={"width": "12"},
            ),
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(rc.Row([html.H2("Session ID:"),
                               html.H2(id = "Session ID",children=f'{session_id}'),
                               html.H2("Session資料集工作路徑:"),
                               html.H2(id = "Session Dataset Dir",children=f'{SessionDatasetDir}'),
                               html.H2("篩選源資料庫路徑:"),
                               html.H2(id = "DF_OPT",children=f'{DF_OPTFN}'),
                               html.H2("篩選後資料庫路徑:"),
                               html.H2(id = "FilteredDF_OPT",children=f'{FilteredDF_OPTFN}')
                               ]),width=3),
                    ])
                ),
            html.Hr(),
            ],
            style={"width": "12"},
            ),
        
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(rc.Row([html.H2(
                    f'🌎:含有日期資訊；Select如為S表示送編；Target如為T表示目標，'
                    '🌞{}：片段類別樣態符合設定條件'.format(
                        ''.join([BinMissionDict[key].get("Icon","")
                                 for key in BinMissionDict]))
                                )
                               ]),width=12),
                    ])
                ),
            html.Hr(),
            ],
            style={"width": "12"},
            ),
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(rc.Row([html.H2(children=f'模型資料集：{datasetDir}')
                               ]),width=3),
                rc.Col(rc.Row([html.H2(children=f'使用模型：{outputDir}')
                               ]),width=3),
                    ])
                ),
            ],
            style={"width": "12"},
            ),
        dbc.Card(
            [
            dbc.CardHeader(children = 
                rc.Row([
                rc.Col(rc.Row([html.Button("下載資料集相關檔案", id="btn_dataset"),
                               dcc.Download(id="download-dataset")
                               #html.H2(id="download-dataset",children=f'{nSamples}')
                               ]),width=3),
                rc.Col(rc.Row([html.Button("下載分析報告", id="btn_report"),
                               dcc.Download(id="download-report")
                               #html.H2(id="download-report",children=f'{nSamples}')
                               ]),width=3),
                rc.Col(rc.Row([html.Button("輸出選擇列為xlsx", id="save-table-button"),
                               dcc.Download(id="download-select-rows")
                               #html.H2(id="download-report",children=f'{nSamples}')
                               ]),width=3),
                rc.Col(rc.Row([html.H2(id='save-table-textbox',children='')
                               ]),width=3),
                    ])
                ),
            html.Hr(),
            ],
            style={"width": "12"},
            ),
        Build_Upload_Block(session_id,UploadedFilename,VisSelfFinishedState),
        dcc.Store(id='intermediate-value-df',  data = df_json),
        #dcc.Store(id='intermediate-value-df',  data = {}),
        #dcc.Store(id='intermediate-value-PartColDF',  data = PartColDF_json),
        dcc.Store(id='intermediate-value-FilteredDF',  data = FilteredDF_json),
        #dcc.Store(id='intermediate-value-FilteredDF',  data = {}),
        #dcc.Store(id='intermediate-value-ColorDict',  data = ColorDict_json),
        dcc.Store(id='intermediate-value-ColorDF',  data = ColorDF_json),
        #dcc.Store(id='intermediate-value-ColorDF',  data = {}),
        #derived_filter_query_structure用來依據filter data設定值更新FilteredDF
        dcc.Store(id='derived_filter_query_structure', data = json.dumps(None, indent = 4)),
        #dcc.Store(id='intermediate-value-selectedLabels',  data = selectedLabels_json),
        #dcc.Store(id='intermediate-value-ShowingFileScoreDF',  data = ShowingFileScoreDF_json), #目前顯示中的檔案及其分數
        #dcc.Store(id='intermediate-value-FilteredDF_OPTFN',  data = FilteredDF_OPTFN_json),
    ])