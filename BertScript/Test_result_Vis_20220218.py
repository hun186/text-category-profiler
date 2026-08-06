from PackageImport import PackageImporter
PackageImporter.proc()
#import utilities_DB
import numpy as np
import pandas as pd
import multiprocessing as mp
import pprint
import json
import os
import platform
import re
import time
import inspect
from collections import Counter
import random
import ast

import dash
import dash_table
import dash_bootstrap_components as dbc
from dash import dcc
#import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import reusable_components as rc  # see reusable_components.py
import plotly.express as px

import argparse
import setproctitle

from utils.visualization.Dash_utils import LevelDVisProcessor
from utils.visualization.Dash_utils import create_card
from utils.visualization.Dash_utils import get_button_id
from utils.visualization.Dash_utils import DictToDataArray
from utils.data.df_utils import dfFromSQLite3
from utils.data.df_utils import dfOutputer
from utils.data.df_utils import concat_df_str1
from utils.data.df_utils import XLSTodf
from utils.concurrency.MP_utils import multicoreJob
from utils.concurrency.MP_utils import MPlogger
from utils.core.utilities import MKDIR
from utils.core.utilities import hash
from utils.core.utilities import UniqueList
from utils.core.utilities import ListDiff
from utils.core.utilities import ListCap
from utils.core.utilities import ShowElapsedTime
from utils.core.utilities import getFNFromFullPath
from utils.core.utilities import getMFNFromFN
from utils.core.utilities import flattenList
from utils.core.utilities import GetnDigitElementsOfaList
from utils.core.utilities import KeyWordsListToRegx
#from utils.core.utilities import ActorUI
#ActorUI.countScreenSize()
#raise Exception
from utils.data.DB_utils import sqlite3Query
from utils.pipeline.DataConverter_utils import ClassfierOptionParser
args = ClassfierOptionParser()
InfoScoreSumLowerBound = args.InfoScoreSumLowerBound
FixedTestFileBound = args.FixedTestFileBound

from utils.pipeline.DataConverter_utils import LabelListLoader
from utils.pipeline.DataConverter_utils import datasetDirOutputDirPickers
from utils.pipeline.DataConverter_utils import LoadTree
from utils.pipeline.DataConverter_utils import GetSubTopics
from utils.pipeline.DataConverter_utils import BuildInfoScoreTable

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

#app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
app = dash.Dash(__name__,external_stylesheets=[dbc.themes.BOOTSTRAP],meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1'}])

#app = dash.Dash(__name__)

def discrete_background_color_bins(df,n_bins=5,columns='all',cmap='Blues'):
    import colorlover
    '''
    ['BrBG', 'PRGn', 'PiYG', 'PuOr', 'RdBu', 'RdGy', 'RdYlBu', 'RdYlGn', 'Spectral',
     'Accent', 'Dark2', 'Paired', 'Pastel1', 'Pastel2', 'Set1', 'Set2', 'Set3',
     'Blues', 'BuGn', 'BuPu', 'GnBu', 'Greens', 'Greys', 'OrRd', 'Oranges', 'PuBu',
     'PuBuGn', 'PuRd', 'Purples', 'RdPu', 'Reds', 'YlGn', 'YlGnBu', 'YlOrBr', 'YlOrRd']
    '''
    bounds = [i * (1.0 / n_bins) for i in range(n_bins + 1)]
    if columns == 'all':
        if 'id' in df:
            df_numeric_columns = df.select_dtypes('number').drop(['id'], axis=1)
        else:
            df_numeric_columns = df.select_dtypes('number')
    else:
        df_numeric_columns = df[columns]
    df_max = df_numeric_columns.max().max()
    df_min = df_numeric_columns.min().min()
    ranges = [
        ((df_max - df_min) * i) + df_min
        for i in bounds
    ]
    styles = []
    legend = []
    for i in range(1, len(bounds)):
        min_bound = ranges[i - 1]
        max_bound = ranges[i]
        #backgroundColor = colorlover.scales[str(n_bins)]['seq']['Blues'][i - 1]
        backgroundColor = colorlover.scales[str(n_bins)]['seq'][cmap][i-1]
        color = 'white' if i > len(bounds) / 2. else 'inherit'

        for column in df_numeric_columns:
            styles.append({
                'if': {
                    'filter_query': (
                        '{{{column}}} >= {min_bound}' +
                        (' && {{{column}}} < {max_bound}' if (i < len(bounds) - 1) else '')
                    ).format(column=column, min_bound=min_bound, max_bound=max_bound),
                    'column_id': column
                },
                'backgroundColor': backgroundColor,
                'color': color
            })
    
        legend.append(
            html.Div(style={'display': 'inline-block', 'width': '60px'}, children=[
                html.Div(
                    style={
                        'backgroundColor': backgroundColor,
                        'borderLeft': '1px rgb(50, 50, 50) solid',
                        'height': '10px'
                    }
                ),
                html.Small(round(min_bound, 2), style={'paddingLeft': '2px'})
            ])
        )

    return (styles, html.Div(legend, style={'padding': '5px 0 5px 0'}))


def complementaryColor(my_hex):
    """Returns complementary RGB color

    Example:
    >>>complementaryColor('FFFFFF')
    '000000'
    """
    if my_hex[0] == '#':
        my_hex = my_hex[1:]
    rgb = (my_hex[0:2], my_hex[2:4], my_hex[4:6])
    comp = ['%02X' % (255 - int(a, 16)) for a in rgb]
    return ''.join(comp)

'''
def get_labels():
  """See base class."""
  LabelList = []
  LabelFile = "TopicAnalysis_LabelList.txt"
  if os.path.isfile(LabelFile):
      with open(LabelFile,'rt',encoding='utf-8') as f:
          for line in f:
              LabelList.append(line.strip())
      #print("lab", LabelList)
      #raise Exception
      return LabelList
  else:
      print("WARNING! LabelList File can not be found")
'''

def CountRating(df):
    df['Rating'] = df.apply(
        lambda x:'⭐'*(min(x.InfoScoreSum//1000,5)+min((x.InfoScoreMean-100)//50,3)*2),
        axis=1)
    return df

def GetSrcList(sql3File):
    MES = f"Start to Load SrcList from {sql3File}"
    MPlogger.logW(MES=MES,logFile="Test_result_Vis.log")
    query = "SELECT DISTINCT Src FROM sampleSrc \
        WHERE Src IS NOT NULL ORDER BY Src;"
    SrcList = [x[0] for x in list(sqlite3Query(
        sql3File, query = query))]
    print(f"There are totally {len(SrcList)} different files.")
    MES = f"Finished Loading SrcList from {sql3File}"
    MPlogger.logW(MES=MES,logFile="Test_result_Vis.log")
    return SrcList

def BuildRowsList(sql3File, SrcList, 
                  sqlCols=['PartNO','pred_Type','text'],
                  LabelSep = "#T#"):
    '''
    從sql3資料庫載入SrcList相關切片及預測資料，回傳為list格式。
    '''
    def GetInfoScoreStastic(segTuples):
        #如果總片數多於一片，可容許一片負分垃圾不計。
        #如果只有一片，無不計空間。
        segScores = [InfoScoreTable[x[1]] for x in segTuples]
        if len(segScores) > 1:
            InfoScoreSum = sum(segScores)-(min(segScores)<0)*min(segScores)
            InfoScoreMean = int(InfoScoreSum/(len(segTuples)-(min(segScores)<0)))
        else:
            InfoScoreSum = sum(segScores)
            InfoScoreMean = int(InfoScoreSum/len(segTuples))
        return InfoScoreSum, InfoScoreMean

        
    def GetClassOfMostPieces(segTuples):
        c = Counter([stu[1] for stu in segTuples])
        try:
            MostPieces = [x for x in c.keys() if c[x] == max(c.values())]
            MostPieces.sort(key=lambda x:InfoScoreTable[x])
            MostPiece = MostPieces[-1]
        except:
            MostPiece = ""
        #c.most_common(1)
        #print([x for x in c.keys() if c[x] == max(c.values())])
        #print(c.most_common(1))
        #raise Exception
        return MostPiece
    
    def GetClassOfHighestScore(segTuples):
        try:
            LabelsWithScore = [(x[1], InfoScoreTable[x[1]]) for x in segTuples]
            LabelsWithScore.sort(key=lambda x:x[1])
            MaxScore = LabelsWithScore[-1][0]
            MostPiece = GetClassOfMostPieces(segTuples)
            #如果最多片的分數也是最高分，則取最多片當做最高分代表，否則隨機取最高分群組中的一個做代表。
            if InfoScoreTable[MostPiece] == MaxScore:
                Highest = MostPiece
            else:
                Highest = LabelsWithScore[-1][0]
        except:
            Highest = ""
        return Highest
    
    LenSrcList = len(SrcList)
    if LenSrcList < 300:
        nLeftChunk = 120000//LenSrcList
    else:
        nLeftChunk = 80
        
    result = []
    for file in SrcList:
        rowDict = {}
        rowDict["File"]=file
        if file is None:
            continue
        #print("file", file)
        query = 'SELECT {colList} FROM sampleSrc \
            WHERE SRC = "{file}" ORDER BY PartNO;'.format(
            colList=','.join(sqlCols), file=file)
        segTuples = []
        try:
            segTuples = list(sqlite3Query(sql3File,  query = query))
        except Exception as e:
            MES = f"When Apply the query {query} to build segTuples, "
            MES += f"the following error occurs: \n {e}"
            MPlogger.logW(MES)
        #for x in segTuples:
            #print(x)
        #print("segTuples", segTuples)
        #raise Exception
        if segTuples == []:
            continue
        #把PartNo轉成int
        if 'PartNO' in sqlCols:
            #idx = cols.index('PartNO')
            segTuples = [(int(float(x[0])),x[1],x[2]) for x in segTuples]
        #print("segTuples", segTuples)
        MaxPN = max([x[0] for x in segTuples])
        temp = [None]*int(MaxPN+1)
        for stu in segTuples:
            #temp[stu[0]] = (LabelSep+stu[1]+LabelSep,stu[2])
            temp[stu[0]] = LabelSep+stu[1]+LabelSep+","+stu[2]
        
        rowDict["Class Of Most Pieces"] = \
            f"{LabelSep}{GetClassOfMostPieces(segTuples)}{LabelSep}"
        rowDict["Class Of Highest Score"] = \
            f"{LabelSep}{GetClassOfHighestScore(segTuples)}{LabelSep}"
        #print("file",file)
        #raise Exception
        #InfoScoreSum = GetInfoScoreSum(segTuples)
        #InfoScoreMean = int(InfoScoreSum/len(segTuples))
        rowDict["InfoScoreSum"],rowDict["InfoScoreMean"]= \
            GetInfoScoreStastic(segTuples)
        #針對PreambleCols，如果有被計算而賦值，則用之，否則使用預設值。
        #完成PreambleCols後，最後再加上切片文本清單。
        row = []
        #print("rowDict",rowDict)
        for col in PreambleCols:
            if col in rowDict.keys():
                row.append(rowDict[col])
            else:
                row.append(PreambleColsDefault[col])
        row.extend(temp[:nLeftChunk])
        #print("row",row)
        result.append(row)
        '''
        #在第一欄補上Rating預設值""
        #在第四欄補上nMatchingBlock預設值0
        #在第五欄補上nMatchingBlockWithKW預設值0
        result.append(["",
                       InfoScoreSum,
                       InfoScoreMean,
                        0,
                        0,
                       LabelSep+ClassOfMostPieces+LabelSep,
                       LabelSep+ClassOfHighestScore+LabelSep,
                       #getFNFromFullPath(file)]+temp[:400])
                       #加入完整檔名路徑欄位資訊
                       file]+temp[:80])
                       #file.split("\\")[-1]]+temp[:400])
                       #getFNFromFullPath(file)]+temp[:400])
        '''
        
    return result

def to_string(filter):
    operator_type = filter.get('type')
    operator_subtype = filter.get('subType')

    if operator_type == 'relational-operator':
        if operator_subtype == '=':
            return '=='
        else:
            return operator_subtype
    elif operator_type == 'logical-operator':
        if operator_subtype == '&&':
            return '&'
        else:
            return '|'
    elif operator_type == 'expression' and operator_subtype == 'value' and type(filter.get('value')) == str:
        return '"{}"'.format(filter.get('value'))
    else:
        return filter.get('value')

operators = [['ge ', '>='],
             ['le ', '<='],
             ['lt ', '<'],
             ['gt ', '>'],
             ['ne ', '!='],
             ['eq ', '='],
             ['contains '],
             ['datestartswith ']]


def split_filter_part(filter_part):
    for operator_type in operators:
        for operator in operator_type:
            if operator in filter_part:
                name_part, value_part = filter_part.split(operator, 1)
                name = name_part[name_part.find('{') + 1: name_part.rfind('}')]

                value_part = value_part.strip()
                v0 = value_part[0]
                if (v0 == value_part[-1] and v0 in ("'", '"', '`')):
                    value = value_part[1: -1].replace('\\' + v0, v0)
                else:
                    try:
                        value = float(value_part)
                    except ValueError:
                        value = value_part

                # word operators need spaces after them in the filter string,
                # but we don't want these later
                return name, operator_type[0].strip(), value

    return [None] * 3

def construct_filter(derived_query_structure, df, complexOperator=None):

    # there is no query; return an empty filter string and the
    # original dataframe
    if derived_query_structure is None:
        return ('', df)

    # the operator typed in by the user; can be both word-based or
    # symbol-based
    operator_type = derived_query_structure.get('type')

    # the symbol-based representation of the operator
    operator_subtype = derived_query_structure.get('subType')

    # the LHS and RHS of the query, which are both queries themselves
    left = derived_query_structure.get('left', None)
    right = derived_query_structure.get('right', None)

    # the base case
    if left is None and right is None:
        return (to_string(derived_query_structure), df)

    # recursively apply the filter on the LHS of the query to the
    # dataframe to generate a new dataframe
    (left_query, left_df) = construct_filter(left, df)

    # apply the filter on the RHS of the query to this new dataframe
    (right_query, right_df) = construct_filter(right, left_df)

    # 'datestartswith' and 'contains' can't be used within a pandas
    # filter string, so we have to do this filtering ourselves
    if complexOperator is not None:
        right_query = right.get('value')
        #for regex = re.compile(pat, flags=flags)
        #first argument must be string or compiled pattern
        if type(right_query) == int:
            right_query = str(right_query)
        # perform the filtering to generate a new dataframe
        if complexOperator == 'datestartswith':
            return ('', right_df[right_df[left_query].astype(str).str.startswith(right_query)])
        elif complexOperator == 'contains':
            return ('', right_df[right_df[left_query].astype(str).str.contains(right_query)])

    if operator_type == 'relational-operator' and operator_subtype in ['contains', 'datestartswith']:
        return construct_filter(derived_query_structure, df, complexOperator=operator_subtype)

    # construct the query string; return it and the filtered dataframe
    return ('{} {} {}'.format(
        left_query,
        to_string(derived_query_structure) if left_query != '' and right_query != '' else '',
        right_query
    ).strip(), right_df)

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
    #print("dataArray",dataArray)
    #raise Exception
    for x in dataArray:
        result[x['Label']] = x['Color']
    return result

              
def ColorDictToColorDF(ColorDict):
    ColorDictTF = {}
    ColorDictTF["Label"] = list(ColorDict.keys())
    ColorDictTF["Color"] = list(ColorDict.values())
    ColorDF = pd.DataFrame(data=ColorDictTF)
    return ColorDF

def DictToDF(Dict, Cols = ["keys","values"]):
    DictTF = {}
    DictTF[Cols[0]] = list(Dict.keys())
    DictTF[Cols[1]] = list(Dict.values())
    DF = pd.DataFrame(data=DictTF)
    return DF

def build_ChunkDF(sql3File,
                  InfoScoreSumLowerBound=np.nan,
                  FixedTestFileBound=0):
    #第一行為"File"
    #LastChunk += 1
    #result = []
    #https://towardsdatascience.com/loading-large-datasets-in-pandas-11bdddd36f7b
    print("Start to load data from SQL3 File", sql3File)
    ShowElapsedTime(start_time)
    
    '''
    rowslist = []
    #df = dfFromSQLite3(sql3File)
    
    df = dfFromSQLite3(sql3File,tableList = ["sampleSrc"],
                  columnList = ['PartNO','pred_Type','text','Src'],
                  orderList = ["Src"])
    
    print("Finished loading data from SQL3")
    ShowElapsedTime(start_time)
    #df['Src'] = df['Src'].apply(hash)
    print("df",df.columns)
    FileList = df['Src'].unique()
    for file in FileList:
        if file == None:
            continue
        pred_series = df[df['Src']==file][['PartNO', 'pred_Type', 'text']]
        #pred_series = df[df['Src']==file][['PartNO', 'pred_Type']]
        MaxPN = max(pred_series['PartNO'])
        temp = [None]*int(MaxPN+1)
        for index, row in pred_series.iterrows():
            #temp[int(row['PartNO'])] = (row['pred_Type'],row['text'])
            temp[int(row['PartNO'])] = ("#T#"+row['pred_Type']+"#T#",row['text'])
            #temp[int(row['PartNO'])] = row['pred_Type']
        #result.append([file.split("\\")[-1]]+temp[:LastChunk])
        #result.append([file.split("\\")[-1]]+temp)
        rowslist.append([file.split("\\")[-1]]+temp[:400])
    '''
    SrcList = GetSrcList(sql3File)
    sqlCols=['PartNO','pred_Type','text']
    rowslist = BuildRowsList(sql3File, SrcList, sqlCols=sqlCols)

    if FixedTestFileBound!=0 and len(rowslist)>FixedTestFileBound:
        random.shuffle(rowslist)
        rowslist = rowslist[:FixedTestFileBound]

    
    #print(result[:10])
    #print(rowslist[0])
    #raise Exception
    '''
    pp = pprint.PrettyPrinter(indent=4)
    for x in rowslist[3]:
        print("="*50)
        pp.pprint(x)
        print("="*50)
        raise Exception
    '''
    bar_df = pd.DataFrame(rowslist)
    
    #columns=["File"]+[str(i) for i in range(len(bar_df.columns)-1)]
    columns=PreambleCols+[str(i) for i in range(len(bar_df.columns)-len(PreambleCols))]
    bar_df.columns = columns
    #print("InfoScoreSumLowerBound is", InfoScoreSumLowerBound)
    #raise Exception
    if InfoScoreSumLowerBound is not np.nan:
        bar_df = bar_df[bar_df['InfoScoreSum']>=InfoScoreSumLowerBound]
    '''
    bar_df['Rating'] = bar_df['InfoScoreSum'].apply(lambda x:
        '⭐⭐⭐⭐⭐' if x > 5000 else (
        '⭐⭐⭐⭐' if x > 4000 else (
        '⭐⭐⭐' if x > 3000 else (
        '⭐⭐' if x > 2000 else (
        '⭐' if x > 1000 else ''
    )))))
    '''  
    
    if bar_df.shape[0] != 0:
        if "linux" in platform.system().lower():
            bar_df = multicoreJob(nProcess=nProcess).parallelize_dataframe(bar_df, CountRating)
        else:
            bar_df['Rating'] = bar_df.apply(
                lambda x:'⭐'*(min(x.InfoScoreSum//1000,5)+min((x.InfoScoreMean-100)//50,3)*2),
                axis=1)
            



    #bar_df['Article Class'] = bar_df.max(axis=1,skipna=True)
    #numCols=[str(i) for i in range(len(bar_df.columns)-2)]
    #bar_df = bar_df[['Article Class','File']+numCols]

    print("Finished building bar_df")
    ShowElapsedTime(start_time)
    #print("bar_df", bar_df)
    #raise Exception

    if len(bar_df)>300:
        bar_df = bar_df.sort_values(by=['Rating','InfoScoreSum'],ascending=False)
    else:
        bar_df = bar_df.sort_values('File')
    
    #bar_df['File'] = bar_df['File'].apply(getMFNFromFN)
    bar_df_saveTemp = bar_df.copy()
    bar_df_saveTemp['File'] = bar_df_saveTemp['File'].apply(getMFNFromFN)
    OUTPUTMAIN = os.path.join(datasetDir,"Full_bar_df")
    dfOutputer(bar_df_saveTemp,OUTPUTMAIN).run()
    return bar_df

def Build_DataArrayTable(TableID,DataArray,ShownColumns=[],
                         style_cell_conditional=[]):
    MES = f"Build Table {TableID} with \n ShownColumns {ShownColumns} and \n style_cell_conditional {style_cell_conditional}"
    MPlogger.logW(MES=MES,logFile="Test_result_Vis.log")
    return dash_table.DataTable(
        id=TableID,
        #data=DF.to_dict('records'),
        #data = DictToDataArray(MissionDict, keyName='Mission', valueName='Topics'),
        data = DataArray,
        columns=[{'id': str(c), 'name': str(c)} for c in ShownColumns],
        #style_cell={'textAlign': 'center'},
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold'
        },
        style_cell_conditional = style_cell_conditional,
        row_deletable=True,
        row_selectable ='multi',
        editable=True,
        filter_action='native'
    )

#def Build_MissionTable(MissionDict):
def Build_MissionTable(MissionDataArray):
    
    #DF = DictToDF(MissionDict,["Mission","Topics"])
    #print("DF",DF)
    #print("DF.to_dict('records')", DF.to_dict('records'))
    
    #raise Exception
    return dash_table.DataTable(
        id='MissionTable',
        #data=DF.to_dict('records'),
        #data = DictToDataArray(MissionDict, keyName='Mission', valueName='Topics'),
        data = MissionDataArray,
        columns=[{'id': str(c), 'name': str(c)} for c in [
            'Mission', 'Expiry Date', 'Topics', 'Key Word']],
        #style_cell={'textAlign': 'center'},
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold'
        },
        row_deletable=True,
        row_selectable ='multi',
        editable=True,
    )

def Build_ColorTable(ColorDict):
    #ColorDF = ColorDictToColorDF(ColorDict)
    ColorDF = DictToDF(ColorDict,["Label","Color"])
    ColorDF['InfoScore'] = ColorDF['Label'].map(InfoScoreTable)
    print(ColorDF.to_dict('records'))
    #raise Exception
    return dash_table.DataTable(
        id='Colortable',
        data=ColorDF.to_dict('records'),
        columns=[{'id': c, 'name': c} for c in ['Color', 'Label', 'InfoScore']],
        style_cell={'textAlign': 'center'},
        style_data_conditional=[
            {'if': {'row_index': i, 'column_id': 'Color'}, 
             'background-color': ColorDF['Color'][i],
             'color': ColorDF['Color'][i]} 
            for i in range(ColorDF.shape[0])
            ],
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold'
        },
        row_deletable=True,
        row_selectable ='multi',
        filter_action='native'
    )

def Build_style_data_conditional(df, ColorDict):
    style_data_conditional = []
    for label in ColorDict.keys():
        style_data_conditional.extend([
            {
                'if': {
                    'filter_query': '{{{col}}} contains \"{val}\"'.format(
                        col=str(i),val=f"#T#{label}#T#"),
                    'column_id': str(i),
                },
                'backgroundColor': ColorDict[label],
                'color': ColorDict[label]
            } for i in df.columns
            ])
        
    style_cell_conditional = [
        {
            'if': {'column_id': str(i)},
            'width': '2px',
            'minWidth': '2px',
            'maxWidth': '10px',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
        } for i in df.columns if str(i).isdigit()
        ]+[
        {
            'if': {'column_id': "Rating"},
            'width': '60px',
            'minWidth': '60px',
        }
        ]+[
        {
            'if': {'column_id': "InfoScoreSum"},
            'width': '25px',
            'minWidth': '25px',
        }
        ]+[
        {
            'if': {'column_id': "InfoScoreMean"},
            'width': '20px',
            'minWidth': '20px',
        }
        ]+[
        {
            'if': {'column_id': "NumberOfMatchingBlock"},
            'width': '20px',
            'minWidth': '20px',
        }
        ]+[
        {
            'if': {'column_id': "NumberOfMatchingBlockWithKW"},
            'width': '20px',
            'minWidth': '20px',
        }
        ]+[
        {
            'if': {'column_id': "File"},
            'width': '200px',
            'minWidth': '200px',
        }
    ]
    heatmapStyle,legend = discrete_background_color_bins(df,columns=['InfoScoreSum'],cmap='Blues')
    style_data_conditional+= heatmapStyle
    heatmapStyle,legend = discrete_background_color_bins(df,columns=['InfoScoreMean'],cmap='Oranges')
    style_data_conditional+= heatmapStyle
    style_cell={
        'width': '10px',
        'minWidth': '10px',
        'maxWidth': '10px',
        'overflow': 'hidden',
        'textOverflow': 'ellipsis',
    }
    def tooltipVal(value):
        if value == None:
            return ""
        if type(value) in [list,tuple] and len(value) == 2:
            return "Label: {}\n\nText: {}".format(
                value[0].replace("#T#",""),(value[1]))
        #["Label: {}".format(value[0].replace("#T#",""),
                           #
        else:
            return str(value)

    tooltip_data=[
        {
            column: {'value': tooltipVal(value),
                     'type': 'markdown'}
            for column, value in row.items()
        } for row in df.to_dict('records')
    ]
    return style_data_conditional,style_cell_conditional,style_cell,tooltip_data

def df_upd_filter_query(df, filter_query):
    filtering_expressions = filter_query.split(' && ')
    dff = df
    for filter_part in filtering_expressions:
        col_name, operator, filter_value = split_filter_part(filter_part)

        if operator in ('eq', 'ne', 'lt', 'le', 'gt', 'ge'):
            # these operators match pandas series operator method names
            dff = dff.loc[getattr(dff[col_name], operator)(filter_value)]
        elif operator == 'contains':
            dff = dff.loc[dff[col_name].str.contains(filter_value)]
        elif operator == 'datestartswith':
            # this is a simplification of the front-end filtering logic,
            # only works with complete fields in standard format
            dff = dff.loc[dff[col_name].str.startswith(filter_value)]
    return dff

def Build_VisDatatable(
        df, ColorDict, page_current=0, page_size=10, 
        derived_query_structure = None,
        filter_query = ''):
    print("="*50)
    print("Running Build_VisDatatable")
    #print("derived_filter_query_structure", derived_query_structure)
    print("filter_query", filter_query)
    if VisDatatable_page_action == 'custom':
        PartDF = df.iloc[
            page_current*page_size:(page_current+ 1)*page_size]
    elif VisDatatable_page_action == 'native':
        PartDF = df
        
    #PartDF = df_upd_filter_query(PartDF, filter_query)
    #標題欄位，只顯示主檔名，不顯示完整路徑。
    
    PartDF['File'] = PartDF['File'].apply(getMFNFromFN)
    
    
    data=PartDF.to_dict('records')
    style_data_conditional, style_cell_conditional, style_cell, tooltip_data \
        = Build_style_data_conditional(PartDF, ColorDict)
    #print("tooltip_data", tooltip_data)
    #raise Exception
    columns=[{'name': str(i), 'id': str(i), #'deletable':True
              } for i in PartDF.columns]
    #print("style_data_conditional",style_data_conditional)
    open("temp.txt","wt",encoding='utf-8').write(str(data))
    #open("temp.txt","wt",encoding='utf-8').write(str(type(data)))
    print("Start to btd")
    Btd = [dash_table.DataTable(
                id='VisDatatable',
                columns=columns,
                #columns=[{'name': i, 'id': i} for i in ['0','1']],
                tooltip ={i: {
                     'value': str(i),
                     'use_with': 'both'  # both refers to header & data cell
                 } for i in PartDF.columns},
                page_current=page_current,
                page_size=page_size,
                #page_action='native',
                #row_selectable ='multi',
                page_action=VisDatatable_page_action,
                data=data,
                tooltip_data=tooltip_data,
                #filter_action='native',
                filter_action='custom',
                #filter_query='',
                #sort_action="native",
                sort_action="custom",
                #sort_mode="multi",
                sort_mode="single",
                sort_by=[],
                style_data_conditional = style_data_conditional,
                style_cell_conditional = style_cell_conditional,
                style_cell = style_cell,
                tooltip_delay=0,
                tooltip_duration=None,
                style_as_list_view=True,
                #derived_filter_query_structure = derived_query_structure,
                filter_query = filter_query,
                export_format='xlsx',
                #export_format='csv',
                export_headers='display', #'display mode only for xlsx format
                #merge_duplicate_headers=True
                )]
    print("end to btd")
    return Btd
    """
    return dash_table.DataTable(
                id='VisDatatable',
                columns=columns,
                #columns=[{'name': i, 'id': i} for i in ['0','1']],
                tooltip ={i: {
                     'value': str(i),
                     'use_with': 'both'  # both refers to header & data cell
                 } for i in PartDF.columns},
                page_current=page_current,
                page_size=page_size,
                #page_action='native',
                #row_selectable ='multi',
                page_action=VisDatatable_page_action,
                data=data,
                tooltip_data=tooltip_data,
                #filter_action='native',
                filter_action='custom',
                #filter_query='',
                #sort_action="native",
                sort_action="custom",
                #sort_mode="multi",
                sort_mode="single",
                sort_by=[],
                style_data_conditional = style_data_conditional,
                style_cell_conditional = style_cell_conditional,
                style_cell = style_cell,
                tooltip_delay=0,
                tooltip_duration=None,
                style_as_list_view=True,
                #derived_filter_query_structure = derived_query_structure,
                filter_query = filter_query,
                export_format='xlsx',
                #export_format='csv',
                export_headers='display', #'display mode only for xlsx format
                #merge_duplicate_headers=True
                )
    """
def Build_Pred_Block(df, ColorDict, SrcList):
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running Build_Pred_Block")
    #LevelDVisProcessor(df=PartDF, VisPath = 'Src')
    print("df",df)
    print("="*50)
    print("="*50)
    tempList = []
    FileList = list(df['File'])
    
    print("FileList",FileList)
    
    #SrcList = GetSrcList(sql3File)
    #print("SrcList", SrcList)
    for src in SrcList:
        #if src.split("\\")[-1] in FileList:
        if src in FileList:
            tempList.append(src)
    rowslist = []
    #SrcList = GetSrcList(sql3File)
    print("there are {} files in tempList".format(len(tempList)))
    cols = ['Src', 'pred_Type']
    for file in tempList:
        query = 'SELECT {colList} FROM sampleSrc \
            WHERE Src = "{file}" ORDER BY Src;'.format(
            colList=','.join(cols), 
            file = file)
        rowslist.extend(list(sqlite3Query(sql3File,  query = query)))
        
    rowslist = [(getMFNFromFN(x[0]),)+x[1:] for x in rowslist]
    getMFNFromFN
    PredsDF = pd.DataFrame(rowslist, columns =['Src', 'pred_Type'])
    '''
    DTBJobs = []
    DTBJobs.append(LevelDVisProcessor(
                df=PredsDF,
                #method="sunburst",
                method="treemap",
                VisPath = ['Src','pred_Type'], 
                color='pred_Type',
                color_discrete_map=ColorDict
                ))
    DTBJobs.append(LevelDVisProcessor(
                            df=PredsDF,
                            method="sunburst",
                            #method="treemap",
                            VisPath = ['pred_Type', 'Src'], 
                            color='pred_Type',
                            color_discrete_map=ColorDict
                            ))
    if __name__ == '__main__':
        MPresult = multicoreJob(
            DTBJobs, method = "run", nProcess = nProcess).run()
    return[
        dcc.Graph(
            #id="Sunburst-graph",
            id="S1",
            figure = MPresult[0]
            ),
        dcc.Graph(
            #id="Sunburst-graph",
            id="S2",
            figure = MPresult[1]
            ),        
        ]
    '''
    return [dcc.Graph(
            #id="Sunburst-graph",
            id="S1",
            figure=LevelDVisProcessor(
                df=PredsDF,
                #method="sunburst",
                method="treemap",
                VisPath = ['Src','pred_Type'], 
                color='pred_Type',
                color_discrete_map=ColorDict,
                OptAnnotation = True,
                ).run()
            ),
            dcc.Graph(
                        #id="Sunburst-graph",
                        id="S2",
                        figure=LevelDVisProcessor(
                            df=PredsDF,
                            method="treemap",
                            #method="treemap",
                            VisPath = ['pred_Type', 'Src'], 
                            color='pred_Type',
                            color_discrete_map=ColorDict,
                            OptAnnotation = True,
                            ).run()
                        ),
            ]


'''
def Build_Pred_Sunburst(
        df, ColorDict, id,
        ):
    print("="*50)
    print("Running Build_Pred_Sunburst")
    #LevelDVisProcessor(df=PartDF, VisPath = 'Src')
    print("df",df)
    print("="*50)
    print("="*50)
    tempList = []
    FileList = list(df['File'])
    #print("SrcList", SrcList)
    
    SrcList = GetSrcList(sql3File)
    for src in SrcList:
        #if src.split("\\")[-1] in FileList:
        if getFNFromFullPath(src) in FileList:
            tempList.append(src)
    rowslist = []
    #SrcList = GetSrcList(sql3File)
    print("there are {} files in tempList".format(len(tempList)))
    cols = ['Src', 'pred_Type']
    for file in tempList:
        query = 'SELECT {colList} FROM sampleSrc \
            WHERE Src = "{file}" ORDER BY Src;'.format(
            colList=','.join(cols), 
            file = file)
        rowslist.extend(list(sqlite3Query(sql3File,  query = query)))
        
    #rowslist = [(x[0].split("\\")[-1],)+x[1:] for x in rowslist]
    rowslist = [(getFNFromFullPath(x[0]),)+x[1:] for x in rowslist]
    PredsDF = pd.DataFrame(rowslist, columns =['Src', 'pred_Type'])
    return dcc.Graph(
            #id="Sunburst-graph",
            id=id,
            figure=LevelDVisProcessor(
                df=PredsDF,
                #method="sunburst",
                method="treemap",
                VisPath = ['Src','pred_Type'], 
                color='pred_Type',
                color_discrete_map=ColorDict
                ).run()
            )
    '''

def Build_selectLabelsTable():
    print("Start to build selectLabelsTable")
    #print("="*500)
    selectLabelsTable = [
            dash_table.DataTable(
                id='selectLabels Dict',
                data = [],
                columns=[
                    #{"name": i, "id": i} for i in sorted(df.columns)
                    {"name": i, "id": i} for i in ["Label","Color","InfoScore"]
                ],
                page_current=0,
                page_size=10,
                page_action='custom',
                #data=RowConstraint,
                #html.H2(id = "Constraint Dict", children = RowConstraint),
                style_cell={
                    'textAlign': 'center',
                    'backgroundColor': 'rgb(50, 50, 50)',
                    'color': 'white',
                    #'textAlign': 'left',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                },
                row_deletable=True,
                editable=True,
                ),
            #html.Button(
                #'Add Row', 
                #id='editing-Constraint-Dict-button', n_clicks=0),
            ]
    print("finished to build selectLabelsTable")
    return selectLabelsTable
        
def cmapSet():
    result = []
    for CSet in ["Dark24", "Light24", "Plotly"]:
        result.extend(getattr(px.colors.qualitative,CSet))
    result = UniqueList(result)
    return result

def RowsFilter(df, selectedLabels, keywords=[], PiecesBound=[1, 100]):
    #ShowingRows = []
    #print("IN RF, selectedLabels",selectedLabels)
    print("IN RF, PiecesBound",PiecesBound)
    def CountKeyWordMatchingRow(df, keywords):
        print("start to compute conDF")
        
        conDF = concat_df_str1(df.drop(PreambleCols, axis=1).applymap(
            lambda x:','.join(str(x).split(",")[1:]) if x is not None else ""))
        return df[conDF.apply(lambda x:re.match(".*"+keywords[0],x) is not None)]
    def CountMatchingBlock(df, selectedLabels, keywords = []):
        patt = '|'.join(["#T#{}#T#".format(x) for x in selectedLabels])
        nMatchingBlockSeries = df.drop(PreambleCols, axis=1).apply(
            lambda r: r.astype(str).str.contains(
            patt, case=False)).apply(
                lambda row: sum(row[:]==True) ,axis=1)
        if keywords == []:
            nMatchingBlockWithKWSeries = pd.DataFrame(
                0, index=np.arange(len(df)),columns=["KW"])
        else:
            #sample:假設r是"#T#CPTPP#T#,会是重要价值伙伴。它呼吁CPTPP会员国"
            #選擇Label為CPTPP
            #則re.sub(patt,"",str(r))是"会是重要价值伙伴。它呼吁CPTPP会员国"
            nMatchingBlockWithKWSeries = df.drop(PreambleCols, axis=1).applymap(
                lambda r: re.match(patt,str(r)) and (
                    re.match(".*"+keywords[0],re.sub(patt,"",str(r))) is not None)).apply(
                    lambda row: sum(row[:]==True) ,axis=1)
        #使用int64而不使用float
        nMatchingBlockSeries = nMatchingBlockSeries.astype(int)
        nMatchingBlockWithKWSeries = nMatchingBlockWithKWSeries.astype(int)
        return nMatchingBlockSeries, nMatchingBlockWithKWSeries
    newPiecesBoundMinMax = PiecesBound
    #如果關鍵字設定非空，進行列篩選。
    print("In RF, KW",keywords)
    #if keywords != []:
        #df = CountKeyWordMatchingRow(df, keywords)
    '''
    if "linux" in platform.system().lower():
        df = multicoreJob(nProcess=nProcess).parallelize_dataframe(df, CountRating)
    else:
        df = CountKeyWordMatchingRow(df, keywords)
    '''
    if selectedLabels == []:
        FilteredDF = df
    else:
        #FilteredDF = df[df.apply(
            #lambda r: r.astype(str).str.contains(
            #'Informative|Scrap', case=False).any(), axis=1)]
        patt = '|'.join(["#T#{}#T#".format(x) for x in selectedLabels])

        #print("criterion,",df.apply(
            #lambda r: r.astype(str).str.contains(
            #patt, case=False)).count(axis=1))
        print(CountMatchingBlock(df, selectedLabels))
        #FilteredDF = df[df.apply(
            #lambda r: r.astype(str).str.contains(
            #patt, case=False).any(), axis=1)]
        nMatchingBlockSeries, nMatchingBlockWithKWSeries = CountMatchingBlock(
            df, selectedLabels, keywords)
        #print("nMatchingBlockSeries",nMatchingBlockSeries)
        #print("nMatchingBlockWithKWSeries",nMatchingBlockWithKWSeries)
        df["NumberOfMatchingBlock"] = nMatchingBlockSeries
        df["NumberOfMatchingBlockWithKW"] = nMatchingBlockWithKWSeries
        FilteredDF = df[nMatchingBlockSeries.between(
            PiecesBound[0], PiecesBound[1])]
        print("FilteredDF", FilteredDF)
        #FilteredDF = df[df.apply(
            #any([lambda r: r.astype(str).str.contains(
            #label, case=False) for label in selectedLabels]), axis=1)]
        #FilteredDF = df['Scrap' in df[df.columns][0]).any(axis=1)]
            #(df[df.columns].str.contains('Scrap')).any(axis=1)]
        #print("IN RF, FilteredDF",FilteredDF, FilteredDF.shape)
        #raise Exception
        #masked_nMBS = np.ma.masked_equal(
            #nMatchingBlockSeries, 0, copy=False)
        masked_nMBS = nMatchingBlockSeries[nMatchingBlockSeries!=0]
        if len(masked_nMBS) == 0:
            newPiecesBoundMinMax = [0,0]
        else:
            newPiecesBoundMinMax = [max(min(masked_nMBS),1),
                              max(nMatchingBlockSeries)]
    return FilteredDF, newPiecesBoundMinMax

start_time = time.time()

nProcess = mp.cpu_count()-1
ListOnlyOccuringLabels = True
sql3File = "test_results_verification.sql3"
sql3File = "test_results_verification_5G.sql3"
sql3File = "test_results_verification_Large.sql3"
PreambleCols = ["Rating",
                "InfoScoreSum", 
                "InfoScoreMean",
                "NumberOfMatchingBlock",
                "NumberOfMatchingBlockWithKW",
                "Class Of Most Pieces",
                "Class Of Highest Score",
                "File"]
PreambleColsDefault = {
                "Rating":"",
                "InfoScoreSum":0, 
                "InfoScoreMean":0,
                "NumberOfMatchingBlock":"",
                "NumberOfMatchingBlockWithKW":"",
                "Class Of Most Pieces":"",
                "Class Of Highest Score":"",
                "File":""}
r = re.compile("dataset_\d+$")
datasetDirs = list(filter(r.match, os.listdir()))
datasetDirs = sorted(datasetDirs, reverse=True)
datasetDir = datasetDirs[0]
datasetDir, outputDir = datasetDirOutputDirPickers.proc()
#下載專區檔案置放處
#資料集 FPath = os.path.join(OfferingDir,"dataset.rar")
#報告 FPath = os.path.join(OfferingDir,"report.rar")
OfferingDir = os.path.join(datasetDir,"OfferingFiles")
MKDIR(OfferingDir)


sql3File = os.path.join(datasetDir,"test_results_verification.sql3")
nProcess = 15
nFigs = 4
page_current = 0
PAGE_SIZE = 100


AutoSelectSubTopics = "No"
DBTreeFile = "C:/Users/*/Documents/TACA/DB/ZMRAND/Imported/TopicTree.txt"
if os.path.isfile(DBTreeFile) == True:
    TreeFile = DBTreeFile
else:
    TreeFile = "../TACA/DB/ZMRAND/Imported/TopicTree.txt"

#設定是否轉換標籤，只留大小寫字母及數字
OnlyLettersDigitsLabels = False

tpcTree = LoadTree(
    TreeFile,OnlyLettersDigitsLabels= OnlyLettersDigitsLabels)

InfoScoreTable = BuildInfoScoreTable(
    TreeFile,OnlyLettersDigitsLabels)
    

#VisDatatable_page_action使用custom時，搭配filter_action=custom時，
#跳頁可能會自動回到第一頁。
#VisDatatable_page_action使用native時，
#第二頁後的tooltip位置可能會出現異常，沒有更新到正確位置。
VisDatatable_page_action = 'custom'
#VisDatatable_page_action = 'native'
#df = build_ChunkDF(sql3File,InfoScoreSumLowerBound=InfoScoreSumLowerBound,FixedTestFileBound=FixedTestFileBound)

try:
    df = build_ChunkDF(sql3File,
                       InfoScoreSumLowerBound=InfoScoreSumLowerBound,
                       FixedTestFileBound=FixedTestFileBound)
except Exception as e:
    MES = f"When trying to run Test_result_Vis.py, the following error occurs:\n {e}"
    MPlogger.logW(MES=MES,logFile="Test_result_Vis.log")
    sql3File = "test_results_verification_Large.sql3"
    df = build_ChunkDF(sql3File,
                       InfoScoreSumLowerBound=InfoScoreSumLowerBound,
                       FixedTestFileBound=FixedTestFileBound)

SrcList = GetSrcList(sql3File)
LenSrcList = len(SrcList)


#DigitCols = list(filter(r.match, list(df.columns)))
#nDigitCols = len(DigitCols)
nDigitCols = GetnDigitElementsOfaList(list(df.columns))
CutRange = [0, min(40,nDigitCols)]
#print(DigitCols)
#print(nDigitCols)
#print(CutRange)
#raise Exception
selectedLabels = ['Informative']
df_json = df.to_json(date_format='iso', orient='split')
FilteredDF_json = df_json
#FilteredDF = pd.read_json(FilteredDF_json, orient='split')

FilteredDF = df
PartCol = PreambleCols+[str(i) for i in range(CutRange[0],CutRange[1])]
PartColDF = FilteredDF[PartCol]
PartColDF_json = PartColDF.to_json(date_format='iso', orient='split')  
nSamples = df.shape[0]

controls1 = [
    rc.CustomRangeSlider(
        id="CutRange", min=0, 
        max=nDigitCols, label="CutRange", step=1,
        value = CutRange),
]


#df = px.data.medals_wide(indexed=True)
#print("df",df)

cms = cmapSet()
ColorDict = {}
#LabelList = ["Informative", "Scrap"]
#LabelList = get_labels()
if ListOnlyOccuringLabels == True:
    cols=['pred_Type']
    LabelList = sorted(set(
        [x[0] for x in sqlite3Query(SQLname=sql3File, table = "sampleSrc", cols=cols)]))
else:
    print("For TRV, outputDir is ", outputDir)
    LabelFile = os.path.join(outputDir,"TopicAnalysis_LabelList.txt")
    LabelList = LabelListLoader.proc(LabelFile)
    rowslist = BuildRowsList(sql3File, SrcList, cols=cols)

def LoadMissionDataOld(FN='SPCMission.txt',Cols=['Mission','Expiry Date','Topics']):
    result = []
    TpcTag = "#T#"
    KWTage = "#KW#"
    with open(FN,'rt',encoding='utf-8') as f:
        for line in f:
            entries = line.rstrip().split(',')
            result.append(
                {'Mission':entries[0],
                 'Expiry Date':entries[1],
                 'Topics':str([x.lstrip(TpcTag) for x in entries if x.startswith(TpcTag)]),
                 'Key Word':[x.lstrip(KWTage) for x in entries if x.startswith(KWTage)],
                 })
    return result

def LoadMissionData(
        InputXLS="",index_col=None,
        header=0,skiprows=[0],ColPosDict={}):
    CPD = ColPosDict
    df = XLSTodf(InputXLS=InputXLS, index_col=index_col,header=header,skiprows=skiprows)
    result = []
    for MSItem in df.iterrows():
        MSItem = list(MSItem[1])
        #print("row",row)
        AppDict = {}
        for col in ['Mission','Expiry Date','Key Word','Topics']:
            AppDict[col] = MSItem[CPD[col]]
        #for col in ['Topics']:
            #AppDict[col] = ast.literal_eval(MSItem[CPD[col]])
        result.append(AppDict)
    return result



ColPosDict = {'Mission':2,'Expiry Date':4,'Topics':6,'Key Word':7}
print("Start to load MissionDataArray")
MissionDataArray = LoadMissionData(
    InputXLS="訂飲料.xlsx",skiprows = [0],index_col = None,header=0,
    ColPosDict=ColPosDict)
print("Finished to load MissionDataArray")

KeyWordDataArray = [{"Key Word":"一路"},]
MT_style_cell_conditional = [
        {
            'if': {'column_id': "Mission"},
            'width': '500px',
            'minWidth': '500px',
            'maxWidth': '500px',
            'whiteSpace':'normal',
            #'overflow': 'hidden',
            #'textOverflow': 'ellipsis',
        }
    ]

print("LabelList", LabelList)
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
ColorDict_json = json.dumps(ColorDict, indent = 4)
#ColorDict = {"Informative":"#87EC0D", 'Scrap':'#e3e4e1'}
#ColorDF = pd.DataFrame(data=ColorDict)
ColorDF = ColorDictToColorDF(ColorDict)
ColorDF_json = ColorDF.to_json(date_format='iso', orient='split')
selectedLabels = []
selectedLabels_json = json.dumps(selectedLabels, indent = 4)
style_data_conditional,style_cell_conditional,style_cell,tooltip_data \
    = Build_style_data_conditional(df, ColorDict)


PiecesBound = [1, max(nDigitCols,1)]
controls2 = [
    rc.CustomRangeSlider(
        id="PiecesBound", min=1, 
        max=max(nDigitCols,1), 
        label="Bound for Satisfying Blocks With the label checklist",
        step=1,
        value = PiecesBound),
]
            
app.layout = html.Div([
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
                                    #Build_MissionTable(MissionDataArray)
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
                                    #Build_MissionTable(MissionDataArray)
                                    Build_DataArrayTable(
                                        "MissionTable",MissionDataArray,
                                        ShownColumns=['Mission', 'Expiry Date', 'Topics', 'Key Word'],
                                        style_cell_conditional=MT_style_cell_conditional
                                        )
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
                html.Summary('Label of the item'),
                    dbc.Card(
                        [
                            dbc.CardHeader(html.H2("Colortable for Labels")),
                            dbc.CardBody(
                                id="ColortableCard",
                                children = [
                                    Build_ColorTable(ColorDict)]
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
            dbc.Card(
                [
                    dbc.CardHeader(html.H2("Predicting Result Summary")),
                    dbc.CardBody(
                        id="PredResSummaryCard",
                        children = Build_Pred_Block(FilteredDF, ColorDict, SrcList=SrcList),
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
                ])
            ),
        dbc.CardBody(
            id="VisDatatableCard",
            children = Build_VisDatatable(PartColDF, ColorDict),
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
                ])
            ),
        html.Hr(),
        html.Hr(),
        html.Hr(),
        ],
        style={"width": "12"},
        ),
    dcc.Store(id='intermediate-value-df',  data = df_json),
    dcc.Store(id='intermediate-value-PartColDF',  data = PartColDF_json),
    dcc.Store(id='intermediate-value-FilteredDF',  data = FilteredDF_json),
    dcc.Store(id='intermediate-value-ColorDict',  data = ColorDict_json),
    dcc.Store(id='intermediate-value-ColorDF',  data = ColorDF_json),
    #derived_filter_query_structure用來依據filter data設定值更新FilteredDF
    dcc.Store(id='derived_filter_query_structure', data = json.dumps(None, indent = 4)),
    #dcc.Store(id='intermediate-value-selectedLabels',  data = selectedLabels_json),
])


#===========================================================

args = []
args.extend([Output('Colortable', 'selected_rows')])
args.extend([Input('MissionTable', 'derived_virtual_selected_rows')])
args.extend([State('MissionTable', 'data')])
args.extend([State('Colortable', 'data')])
@app.callback(*args)
def MissionTableSelection(
        derived_virtual_selected_rows,
        data,
        Colortable_data,
        #*args
        ):
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running MissionTableSelection.")
    print("derived_virtual_selected_rows", derived_virtual_selected_rows)
    print("data",data)
    print("Colortable_data",Colortable_data)
    selectedLabels = []
    if derived_virtual_selected_rows is None:
        return []
    for i in derived_virtual_selected_rows:
        selectedLabels.extend(ast.literal_eval(data[i]['Topics']))
        #selectedLabels.extend(data[i]['Topics'])
    selectedLabels = sorted(selectedLabels)
    Colortable_rows = []
    for Label in selectedLabels:
        for i,CILPair in enumerate(Colortable_data):
            if CILPair['Label'] == Label:
                Colortable_rows.append(i)
    print("Colortable_rows",Colortable_rows)
    print("Finished MissionTableSelection.")
    return Colortable_rows



                                     

#============================================================

args = []
args.extend([Output('intermediate-value-FilteredDF', 'data')])
args.extend([Output('nSamples', 'children')])
args.extend([Output('nSamples_bottom', 'children')])
args.extend([Output("CutRange", "max")])
args.extend([Output("PiecesBound", "min")])
args.extend([Output("PiecesBound", "max")])
args.extend([Output("PiecesBound", "marks")])
#args.extend([Output("PiecesBound", "value")])
args.extend([Output("derived_filter_query_structure", 'data')])
#args.extend([Output("intermediate-value-selectedLabels", 'data')])
#args.extend([Output('selectedLabels', 'children')])
args.extend([Output("selectLabels Dict", "data")])
args.extend([Output("selectLabels Dict", "style_data_conditional")])
args.extend([Input("AutoSelectSubTopics", "value")])
args.extend([Input("PiecesBound", "value")])
args.extend([Input('Colortable', 'derived_virtual_selected_rows')])
args.extend([Input('VisDatatable', "sort_by")])
args.extend([Input('VisDatatable', "derived_filter_query_structure")])
args.extend([Input('VisDatatable', "filter_query")])
args.extend([Input('KeyWordTable', "selected_rows")])
args.extend([Input('KeyWordTable', "data")])
args.extend([State('intermediate-value-df', 'data')])
args.extend([State('Colortable', 'data')])
args.extend([State('derived_filter_query_structure', 'data')])
@app.callback(*args)
def FilteredDF_update(
        AutoSelectSubTopics,
        PiecesBound,
        derived_virtual_selected_rows,
        sort_by,
        derived_query_structure,
        filter_query,
        kw_dvs_rows,
        kw_data,
        df_json,
        ColortableArray,
        Old_derived_filter_query_structure_json,
        #*args
        ):
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running FilteredDF_update.")
    print("filter_query", filter_query)
    #print("derived_filter_query_structure", derived_query_structure)
    Old_derived_query_structure = json.loads(Old_derived_filter_query_structure_json)
    print("Old_derived_query_structure", Old_derived_query_structure)
    #derived_filter_query_structure = None
    print("receving derived_query_structure is ", derived_query_structure)    
    button_id = get_button_id(
        dash.callback_context, inspect.currentframe().f_code.co_name)
    #下方似乎為舊bug，最新情況不會出現。
    #當page_action=custom, filter_action=custom時，
    #點擊 > page down按紐時，會觸發('VisDatatable', "derived_filter_query_structure")
    #且無法正常回傳當下('VisDatatable', "derived_filter_query_structure")的值，
    #會回傳('VisDatatable', "derived_filter_query_structure")值為None
    #造成篩選錯誤，故加入此檢驗機制，使用filter_query避免誤觸發。
    if filter_query != "" and derived_query_structure == None:
        derived_query_structure = Old_derived_query_structure
        '''
        if button_id == "VisDatatable": 
            print(f"filter_query = {filter_query} which is not empty string.")
            print("But derived_query_structure is None,")
            print("this should be a false trigger, abort updating.")
            raise PreventUpdate
        if button_id in ["Colortable"]:
            print("button_id is Colortable, and filter_query is not empty,")
            print("but receving derived_query_structure is None.")
            print("replace variable derived_query_structure as the old one.")
            derived_query_structure = Old_derived_query_structure

        '''
        '''
        if Old_derived_query_structure == derived_query_structure:
            print("derived_query_structure is not changed, abort updating.")
            raise PreventUpdate
        if derived_query_structure == None:
            derived_query_structure = Old_derived_query_structure
            print("button_id is VisDatatable (derived_query_structure),")
            print("but receving derived_query_structure is None.")
            print("Abort updating.")
            #print("replace variable derived_query_structure as the old one.")
            raise PreventUpdate
        '''
    
    if derived_virtual_selected_rows == None:
        derived_virtual_selected_rows = []
    df =  pd.read_json(df_json, orient='split')
    
    '''
    print("sort_by",sort_by)
    if len(sort_by):
        print("old df",df)
        df = df.sort_values(
            sort_by[0]['column_id'],
            ascending=sort_by[0]['direction'] == 'asc',
            inplace=False)
        print("="*50)
        print("new df",df)
    #else:
        # No sort is applied
        #df = df
    '''
    
    #計算選擇之類別清單selectedLabels
    selectedLabels = [
        ColortableArray[x]['Label'] 
        for x in derived_virtual_selected_rows]
    #如果AutoSelectSubTopics == "Yes"，則自動擴展篩選子類列。
    if AutoSelectSubTopics == "Yes":
        selectedLabels = sorted(set(flattenList(
            [GetSubTopics([x], tpcTree) for x in selectedLabels]
            )))
    #僅考慮確實有出現該類文本的類別
    selectedLabels = sorted(ListCap(selectedLabels,list(ColorDF['Label'])))
    #print("kw_data",kw_data)
    if kw_dvs_rows is None:
        #for i in kw_dvs_rows:
            #keywords.extend(ast.literal_eval(kw_data[i]['Key Word']))
            #keywords.extend(''.join(kw_data[i]['Key Word']))
        keywords = []
    else:
        keywords = [kw_data[i]['Key Word'] for i in kw_dvs_rows]
    #print("Key Word",keywords)
    FilteredDF, [newPBMin, newPBMax] = RowsFilter(
        df,
        selectedLabels = selectedLabels,
        keywords = keywords,
        PiecesBound = PiecesBound)
    marks={i: str(i) for i in [
        newPBMin,
        int((newPBMin+newPBMax)/2),
        newPBMax]}
    
    print("sort_by",sort_by)
    if len(sort_by):
        print("old FilteredDF",FilteredDF)
        FilteredDF = FilteredDF.sort_values(
            sort_by[0]['column_id'],
            ascending=sort_by[0]['direction'] == 'asc',
            inplace=False)
        print("="*50)
        print("new FilteredDF",FilteredDF)
    #else:
        # No sort is applied
        #df = df
    
    (pd_query_string, FilteredDF) = construct_filter(
        derived_query_structure, FilteredDF)
    if pd_query_string != '':
        FilteredDF = FilteredDF.query(pd_query_string)
    ShowElapsedTime(start_time)
    print("Start to tf FilteredDF to FilteredDF_json.")
    FilteredDF_json =  FilteredDF.to_json(date_format='iso', orient='split')
    derived_query_structure_json = json.dumps(
        derived_query_structure, indent = 4)
    #頁面下方表格羅列有出現文本的類別清單資料及格式
    selectedLabelsDF=pd.DataFrame()
    selectedLabelsDF['Label'] = selectedLabels
    selectedLabelsDF['InfoScore'] = selectedLabelsDF['Label'].map(InfoScoreTable)
    selectedLabelsDF['Color'] = selectedLabelsDF['Label'].map(ColorDict)
    selectedLabelsDictArray = selectedLabelsDF.to_dict('records')
    style_data_conditional=[
        {'if': {'filter_query': '{{Label}} = "{}"'.format(ColorDF['Label'][i]),
                'column_id': 'Color'}, 
         'background-color': ColorDF['Color'][i],
         'color': ColorDF['Color'][i],
         } 
        for i in range(ColorDF.shape[0])
        ]
    
    ShowElapsedTime(start_time)
    print("Finished Running FilteredDF_update.")
    return [FilteredDF_json]+[FilteredDF.shape[0]]*2+[
        GetnDigitElementsOfaList(list(FilteredDF.columns))
        #FilteredDF.shape[1]
        ]+[newPBMin,newPBMax,marks]+[derived_query_structure_json
        ]+[selectedLabelsDictArray]+[style_data_conditional]


#=======================================================

args = []
args.extend([Output('intermediate-value-PartColDF', 'data')])
args.extend([Output('VisDatatable', "page_current")])
#args.extend([Output('Chunk Params', 'data')])
#args.extend([Output('Start Bar', 'max')])
#args.extend([Output('Start Bar', 'marks')])
#args.extend([Output('nUniqueVal Bar', 'max')])
#args.extend([Output('nUniqueVal Bar', 'marks')])
#args.extend([Input("LastChunk", "value")])
args.extend([Input("CutRange", "value")])
args.extend([Input('intermediate-value-FilteredDF', 'data')])
#args.extend([Input('VisDatatable', "derived_filter_query_structure")])
args.extend([State('VisDatatable', "page_current")])
#args.extend([Input("Stride Bar", "value")])
@app.callback(*args)
def ChunkDF_update(
        #LastChunk,
        CutRange,
        FilteredDF_json,
        #derived_query_structure,
        page_current):
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running ChunkDF_update.")
    button_id = get_button_id(
        dash.callback_context, inspect.currentframe().f_code.co_name)    

    #df_json = df.to_json(date_format='iso', orient='split')
    FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    PartCol = PreambleCols+[str(i) for i in range(CutRange[0],CutRange[1])]
    #print("In CU, PartCol", PartCol)
    PartColDF = FilteredDF[PartCol]
    '''
    if button_id in ["VisDatatable"]:
        (pd_query_string, PartColDF) = construct_filter(
            derived_query_structure, PartColDF)
        if pd_query_string != '':
            PartColDF = PartColDF.query(pd_query_string)
    '''
    #columns=["File"]+list(range(len(bar_df.columns)-1))
    #FilteredDF.columns = columns
    PartColDF_json = PartColDF.to_json(date_format='iso', orient='split')
    #if button_id not in ['No clicks yet', 'CutRange']:
        #page_current = 0
    ShowElapsedTime(start_time)
    return [PartColDF_json]+[page_current]



#============================================================

args = []
args.extend([Output('VisDatatableCard', 'children')])
args.extend([Output('PredResSummaryCard', 'children')])
args.extend([Input('VisDatatable', "page_current")])
args.extend([Input("Page Size Bar", "value")])
args.extend([Input('intermediate-value-PartColDF', 'data')])
args.extend([Input('intermediate-value-ColorDict', 'data')])
#args.extend([Input('VisDatatable', "derived_filter_query_structure")])
#args.extend([State('VisDatatable', "page_current")])
args.extend([State('Colortable', 'data')])
#args.extend([State('VisDatatable', "derived_filter_query_structure")])
#args.extend([State('derived_filter_query_structure', "data")])
args.extend([State('VisDatatable', "filter_query")])
args.extend([State('intermediate-value-FilteredDF', 'data')])
@app.callback(*args)
def table_update(
        page_current,
        page_size,
        PartColDF_json,
        ColorDict_json,
        #page_current,
        #derived_virtual_selected_rows,
        #derived_query_structure,
        ColortableArray,
        #derived_query_structure,
        #derived_query_structure_json,
        filter_query,
        FilteredDF_json,
        #*args
        ):
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running table_update")
    print("filter_query",filter_query)
    #print("derived_query_structure", derived_query_structure)
    #derived_query_structure = json.loads(derived_query_structure_json)
    #print("derived_query_structure", derived_query_structure)
    button_id = get_button_id(
        dash.callback_context, inspect.currentframe().f_code.co_name)

    if button_id in ["Page Size Bar"]:
        page_current = 0
        
    #df =  pd.read_json(df_json, orient='split')
    PartColDF =  pd.read_json(PartColDF_json, orient='split')
    '''
    if button_id in ["VisDatatable"]:
        (pd_query_string, PartColDF) = construct_filter(
            derived_query_structure, PartColDF)
        if pd_query_string != '':
            PartColDF = PartColDF.query(pd_query_string)
    '''
    ColorDict = json.loads(ColorDict_json)
    #print("Start to in Btd table_update")
    VisData_children = Build_VisDatatable(
        PartColDF, ColorDict, 
        page_current=page_current, page_size=page_size,
        #derived_query_structure = derived_query_structure,
        filter_query=filter_query)
    
    FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    PredSum_children = Build_Pred_Block(
        FilteredDF, ColorDict,SrcList=SrcList)
    ShowElapsedTime(start_time)
    return [VisData_children]+[PredSum_children]


#============================================================

args = []
#args.extend([Output('Constraint Dict', 'data')])
args.extend([Output('intermediate-value-ColorDict', 'data')])
args.extend([Output('ColortableCard', 'children')])
args.extend([Input('Colortable', "data")])
args.extend([State('intermediate-value-ColorDict', 'data')])
@app.callback(*args)
def update_intermediate_value_ColorDict(
        ColortableArray,
        ColorDict_json,
        ):
    ColorDict = DataArrayToDict(ColortableArray)
    #print("IN UIVC ColorDict b4", ColorDict)
    ColorDict_Previous = json.loads(ColorDict_json)
    #print("IN UIVC ColorDict_Previous b4", ColorDict_Previous)
    OldKey = list(ColorDict_Previous.keys())
    NewKey = list(ColorDict.keys())
    if NewKey != OldKey:
        for label in ListDiff(OldKey, NewKey):
            ColorDict[label] = '#D4E9F7'
    ColorDict_json_new = json.dumps(ColorDict, indent = 4)
    children = [Build_ColorTable(ColorDict)]
    return [ColorDict_json_new]+[children]

'''
args = []
#args.extend([Output('Constraint Dict', 'data')])
args.extend([Output('ColortableCard', 'style')])
args.extend([Output('PredResSummaryCard', 'style')])
args.extend([Input('dropdown', "value")])
@app.callback(*args)
def show_hide_element(visibility_state):
    if visibility_state == 'Colortable':
        return [{'display': 'inline'}]+[{'display': 'none'}]
        #return {'display': 'block'}
    if visibility_state == 'Summary':
        #return [Colortable_style]+[Summary_style]
        #return {'display': 'none'}
        return [{'display': 'none'}]+[{'display': 'inline'}]
    return [{'display': 'inline'}]+[{'display': 'inline'}]
    #return [Colortable_style]+[Summary_style]
'''  
'''
@app.callback(Output('ColortableCard', 'style'), [Input('Colortable_toggle', 'value')])
def toggle_container(toggle_value):
    if toggle_value == 'Show':
        return {'display': 'none'}
    else:
        return {'display': 'block'}
'''

'''
@app.callback(
    #Output('VisDatatable', 'data'),
    Output('intermediate-value-FilteredDF', 'data'),
    #Input('VisDatatable', "page_current"),
    #Input('VisDatatable', "page_size"),
    Input('VisDatatable', 'sort_by'),
    #State('VisDatatable', 'data'),
    State('intermediate-value-FilteredDF', 'data'),
    )
def update_table(page_current, page_size, sort_by,FilteredDF_json):
    FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    #print("df",df)
    FilteredDF['File'] = FilteredDF['File'].apply(getMFNFromFN)
    if len(sort_by):
        FilteredDF.sort_values(
            sort_by[0]['column_id'],
            ascending=sort_by[0]['direction'] == 'asc',
            inplace=True
        )

    else:
         No sort is applied
        dff = FilteredDF
    
    return dff.iloc[
        page_current*page_size:(page_current+ 1)*page_size
    ].to_dict('records')

    FilteredDF_json =  FilteredDF.to_json(date_format='iso', orient='split')
    return FilteredDF_json
'''


@app.callback(
    Output("download-dataset", "data"),
    Input("btn_dataset", "n_clicks"),
    prevent_initial_call=True,
)
def func(n_clicks):
    FPath = os.path.join(OfferingDir,"dataset.rar")
    return dcc.send_file(FPath)


@app.callback(
    Output("download-report", "data"),
    Input("btn_report", "n_clicks"),
    prevent_initial_call=True,
)
def func(n_clicks):
    FPath = os.path.join(OfferingDir,"report.rar")
    return dcc.send_file(FPath)

#============================================================


if __name__=='__main__':
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--TRVPort", help="Input the port for hosting the web.",
        type=int, default=8050)
    parser.add_argument(
        "-pub", "--public", help="Publish the web.", action="store_true")
    args = parser.parse_args()
    '''
    args = ClassfierOptionParser()
    if args.public == True:
        hostIP = '0.0.0.0'
    else:
        hostIP = '127.0.0.1'
    ACPort = args.TRVPort
    setproctitle.setproctitle(f'TRV{args.TRVPort}')
    #print("args.InfoScoreSumLowerBound", InfoScoreSumLowerBound)
    #app.run_server(debug=True, use_reloader=False, port = ACPort,host='0.0.0.0')
    '''
    if "linux" in platform.system().lower():
        KillOldServerPSCMD = f"pkill TRV{args.TRVPort}"
        print(f"Running CMD: {KillOldServerPSCMD}")
        os.system(KillOldServerPSCMD)
    '''
    app.run_server(debug=True, use_reloader=False, 
                   port = ACPort, host = hostIP)
    
#項次 領域 項目 單位 日期 備註