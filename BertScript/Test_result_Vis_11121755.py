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
import random
import ast
import datetime as dte
import uuid
import shutil
#from bisect import bisect_left
import math
from collections import Counter
from functools import partial

import dash
#import dash_table
from dash import dash_table
import dash_bootstrap_components as dbc
from dash import dcc
#import dash_core_components as dcc
from dash import html
#import dash_html_components as html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_pivottable
import dash_uploader as du
import reusable_components as rc  # see reusable_components.py
import plotly.express as px
from flask import request

import setproctitle
from colorama import Fore#, Back, Style

#單篇文章用來進行摘要的片數上限
from TCF_Params.TCFParameters import nPiecesToSummaryUPD

#from ClassesTree_utils import GetTreeFilePath
from text_category_profiler.pipeline.TCF_utils import datasetDirOutputDirPickers
from text_category_profiler.pipeline.TCF_utils import get_finished_date_dir_dict
from text_category_profiler.visualization.Dash_utils import discrete_background_color_bins
from text_category_profiler.visualization.Dash_utils import LevelDVisProcessor
from text_category_profiler.visualization.Dash_utils import create_card
from text_category_profiler.visualization.Dash_utils import get_button_id
from text_category_profiler.visualization.Dash_utils import get_button_id_comp
from text_category_profiler.visualization.Dash_utils import DictToDataArray
from text_category_profiler.visualization.Dash_utils import Build_DataArrayTable
#from text_category_profiler.visualization.Dash_utils import ComputeTwins
from text_category_profiler.data.df_utils import dfFromSQLite3
from text_category_profiler.data.df_utils import dfOutputer
from text_category_profiler.data.df_utils import TSVTextAdapter
#from text_category_profiler.data.df_utils import WeiTechFormatOutputer
from text_category_profiler.data.df_utils import concat_df_str1
from text_category_profiler.data.df_utils import XLSTodf
from text_category_profiler.data.df_utils import compare_dfs
from text_category_profiler.concurrency.MP_utils import multicoreJob
from text_category_profiler.concurrency.MP_utils import MPlogger
from text_category_profiler.concurrency.MP_utils import CommandExecutor
from text_category_profiler.core.utilities import timeNow
from text_category_profiler.core.utilities import OSWALK
from text_category_profiler.core.utilities import MKDIR
from text_category_profiler.core.utilities import hasher
from text_category_profiler.core.utilities import UniqueList
from text_category_profiler.core.utilities import ListDiff
from text_category_profiler.core.utilities import ListCap
from text_category_profiler.core.utilities import SplitList
from text_category_profiler.core.utilities import ShowElapsedTime
from text_category_profiler.core.utilities import getFNFromFullPath
from text_category_profiler.core.utilities import getMFNFromFN
from text_category_profiler.core.utilities import pathSpliter
from text_category_profiler.core.utilities import flattenList
from text_category_profiler.core.utilities import GetnDigitElementsOfaList
from text_category_profiler.core.utilities import KeyWordsListToRegx
from text_category_profiler.core.utilities import DateExtractor
from text_category_profiler.core.utilities import RandomSample
from text_category_profiler.core.utilities import ExtractZip
from text_category_profiler.core.utilities import timeNow
from text_category_profiler.core.utilities import rindex
from text_category_profiler.core.utilities import RandomColor
from text_category_profiler.core.utilities import reCombiner
from text_category_profiler.core.utilities import GetFileSize
from text_category_profiler.core.utilities import SortedDictWithValue
from text_category_profiler.core.utilities import clearPort
from text_category_profiler.core.utilities import NewlineNormalizer
from text_category_profiler.core.utilities import colored_print
from text_category_profiler.core.utilities import countdown_pause
from text_category_profiler.text.similarity_utils import InnerCrossSimilarityForTextList
#from text_category_profiler.core.utilities import ActorUI
#ActorUI.countScreenSize()

#from text_category_profiler.visualization.Graph_utils import ComputeComponent
#from text_category_profiler.visualization.Graph_utils import build_Louvain
from text_category_profiler.pipeline.TCF_utils import ClassfierOptionParser
from text_category_profiler.pipeline.TCF_utils import LoadDatasetCount
from text_category_profiler.data.DB_utils import sqlite3Query

#print("args", args)
#from text_category_profiler.pipeline.DataConverter_utils import LabelListLoader
#from text_category_profiler.pipeline.DataConverter_utils import datasetDirOutputDirPickers
from ClassesTree.ClassesTree_utils import LoadTree
#from ClassesTree.ClassesTree_utils import GetRoots
from ClassesTree.ClassesTree_utils import GetSubTopics
from ClassesTree.ClassesTree_utils import BuildInfoScoreTable
from ClassesTree.ClassesTree_utils import BuildSubTopicsDict
#from ClassesTree.Visualization.jaal.jaalViewer import JaalViewMain
from text_category_profiler.tulip_utils.Graph_Builder import ClusterMetaNodeGraph
from text_category_profiler.tulip_utils.Graph_Builder import BuildGraph
from text_category_profiler.text.TextProcessor_utils import textReader
from text_category_profiler.core.utilities import freeGPUConformer
from text_category_profiler.core.utilities import getIP
from Test_result_Vis_utils import GetInfoScoreStastic
from Test_result_Vis_utils import GetClassOfMostPieces
from Test_result_Vis_utils import GetClassOfHighestScore
from Test_result_Vis_utils import ComputeExempt
from Test_result_Vis_utils import TwinsClassifier
from Test_result_Vis_utils import EvaluatePreference
from Test_result_Vis_utils import ExportDFAllToDatabase

from VisParameters import BinMissionDict
from Test_result_Vis_utils import BinMissionVerifier
#from Test_result_Vis_utils import VisDfToRowTagsList
#from Test_result_Vis_utils import BuildClassesPivotTable
from ClassTable import ClassTable
from VisParameters import SimilarPiecesExemptMethod
from VisParameters_Format import MT_style_cell,MT_style_cell_conditional
from VisParameters_Format import Colortable_style_cell,Colortable_style_cell_conditional,Colortable_style_header

#from GenerativeLanguageModel.GenerativeSummary import SummarizingPathText

from pages.labelViewer import layout_interactivity
from pages.labelViewer.callbacks import callback_manager as callback_manager_labelViewer

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

#df_tree = pd.read_csv("https://raw.githubusercontent.com/Coding-with-Adam/Dash-by-Plotly/master/Cytoscape/org-data.csv")
#df_tree_json = df_tree.to_json(date_format='iso', orient='split')

#app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
app = dash.Dash(__name__,external_stylesheets=[dbc.themes.BOOTSTRAP],
                meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1'}])
callback_manager_labelViewer.attach_to_app(app)

#app = dash.Dash(__name__)
#print("callback_manager_labelViewer att")

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


def CountRating(df):
    df['Rating'] = df.apply(
        lambda x:'⭐'*(min(x.InfoScoreSum//1000,5)+min((x.InfoScoreMean-100)//50,3)*2),
        axis=1)
    return df

def PerformanceColExt(df):
    #df[col] = df.apply(xxxxx) will Raise SettingWithCopyWarning;    
    pd.options.mode.chained_assignment = None
    df['InfoScoreSumInterval'] = df.apply(
        lambda x:
            'G7. 5000+' if x.InfoScoreSum >= 5000 else (
            'G6. 4000~5000' if x.InfoScoreSum >= 4000 else (
            'G5. 3000~3999' if x.InfoScoreSum >= 3000 else (
            'G4. 2000~2999' if x.InfoScoreSum >= 2000 else (
            'G3. 1000~1999' if x.InfoScoreSum >= 1000 else (
            'G2. 500~999' if x.InfoScoreSum>=500 else (
            'G1. 0~499' if x.InfoScoreSum>=0 else (
            'B3. -500~-1' if x.InfoScoreSum>= -500 else (
            'B2. -2000~-501' if x.InfoScoreSum>=-2000 else
            'B1. <-2000'
                )))))))),
        axis=1)
    df['InfoScoreMeanInterval'] = df.apply(
        lambda x:
            'G9. 500+' if x.InfoScoreMean >= 500 else (
            'G8. 300~499' if x.InfoScoreMean >= 300 else (
            'G7. 200~299' if x.InfoScoreMean >= 200 else (
            'G6. 170~200' if x.InfoScoreMean >= 170 else (
            'G5. 130~170' if x.InfoScoreMean >= 130 else (
            'G4. 100~130' if x.InfoScoreMean >= 100 else (
            'G3. 70~100' if x.InfoScoreMean >= 70 else (
            'G2. 40~70' if x.InfoScoreMean >= 40 else (
            'G1. 0~40' if x.InfoScoreMean>=0 else (
            'B4. -50~0' if x.InfoScoreMean>= -50 else (
            'B3. -100~-50' if x.InfoScoreMean>= -100 else (
            'B2. -200~-100' if x.InfoScoreMean>= -200 else (
            'B1. <-200'
                )))))))))))),
        axis=1)
        
    df["Recommanded"] = df.apply(
        lambda x: "推" if x.InfoScoreSum>=500 else "未推", axis=1)
    df["Selected"] = df.apply(
        lambda x: "送編" if x.Selected =="S" else "未送編", axis=1)
    df["Target"] = df.apply(
        lambda x: "目標" if x.Target =="T" else "非目標", axis=1)
    pd.options.mode.chained_assignment = 'warn'
    return df


def GetSrcList(sql3File):
    MES = f"Start to Load FileList from {sql3File}"
    MPLOGGER.logW(MES=MES,logFile="Test_result_Vis.log")
    query = "SELECT DISTINCT File FROM sampleSrc \
        WHERE File IS NOT NULL ORDER BY File;"
    SrcList = [x[0] for x in list(sqlite3Query(
        sql3File, query = query))]
    print(f"There are totally {len(SrcList)} different files.")
    MES = f"Finished Loading SrcList from {sql3File}"
    MPLOGGER.logW(MES=MES,logFile="Test_result_Vis.log")
    return SrcList

def DFfilter(df,
             InfoScoreSumLowerBound = -99999999,
             InfoScoreSumUpperBound = 99999999):
        #依分數區間篩濾
        maskLbd = [True]*len(df)
        maskUbd = [True]*len(df)
        if "Selected" in df.columns:
            maskSel = (df["Selected"]=="S")
        else:
            maskSel = [True]*len(df)
        if "InfoScoreSum" not in df.columns:
            MES = "WARNING!! When applying DFfilter, InfoScoreSum not in df.columns!"
            MPLOGGER.logW(MES=MES,logFile="Test_result_Vis.log")
        #maskTar = (bar_df["Target"]=="T")
        #self.InfoScoreSumLowerBound = 300
        try:
            InfoScoreSumLowerBound = float(InfoScoreSumLowerBound)
            maskLbd = (df['InfoScoreSum'] >= InfoScoreSumLowerBound)
        except:
            pass
        try:
            InfoScoreSumUpperBound = float(InfoScoreSumUpperBound)
            maskUbd = (df['InfoScoreSum'] <= InfoScoreSumUpperBound)
        except:
            pass
        maskFinal = (maskLbd & maskUbd) | maskSel #| maskTar
        return df[maskFinal]
        
class VisDatatableRowsListBuilder:
    def __init__(self, 
                 tpcTree,
                 BinMissionDict,
                 PreambleCols,PreambleColsDefault,
                 sql3File, SrcList, 
                 SelectedFNPatList = [],
                 sqlCols=['PartNO','pred_Type','text'],
                 LabelSep = "#T#",
                 InfoScoreTable = {},
                 nLeftFileChunk = 0,
                 nScoringSegUPD = 100,
                 TextSummarization = False,
                 CountArticleComposition = False,
                 nPiecesToSummaryUPD = 3,
                 BertDatasetSubDir = "dataset",
                 ):
        self.tpcTree = tpcTree
        self.BinMissionDict = BinMissionDict
        self.PreambleCols=PreambleCols
        self.PreambleColsDefault=PreambleColsDefault
        self.sql3File = sql3File
        self.SrcList = SrcList
        self.SelectedFNPatList = SelectedFNPatList
        self.sqlCols = sqlCols
        self.LabelSep = LabelSep
        self.InfoScoreTable = InfoScoreTable
        self.nLeftFileChunk = nLeftFileChunk
        self.nScoringSegUPD = nScoringSegUPD
        self.TextSummarization = TextSummarization
        self.CountArticleComposition = CountArticleComposition
        self.nPiecesToSummaryUPD = nPiecesToSummaryUPD
        self.BertDatasetSubDir = BertDatasetSubDir
        
        #self.show()
        
    def show(self):
        print("sql3File is {}".format(self.sql3File))
        print("SrcList[:20] is {}".format(self.SrcList[:20]))

    #滙出摘要用之文本內容
    def textPrepossingForSummary(
            self,file="",segTuples = []):
        if file == "":
            print("There is no input filename to handle for saving, Abort")
            return
        #print("apply textPrepossingForSummary for file",file)
        SumPath = os.path.join(self.BertDatasetSubDir,"SummarizingSource")
        MKDIR(SumPath)
        nPiecesToSummary = 0
        open(os.path.join(SumPath,file),'wt',encoding='utf-8').close()
        with open(os.path.join(SumPath,file),'at',encoding='utf-8') as f:
            for stu in segTuples:
                #中立類別有0.000002之類的分數，以表達深度用，故留下分數閥值設10。
                if self.InfoScoreTable.get(stu[1],10)>10: 
                    f.write(stu[2])
                    nPiecesToSummary += 1
                if nPiecesToSummary == self.nPiecesToSummaryUPD:
                    print(f"It has cutting out {self.nPiecesToSummaryUPD} pieces, namely {nPiecesToSummaryUPD}*256={nPiecesToSummaryUPD*256} char to summarize, quit cutting.")
                    break
    def run(self):
        '''
        從sql3資料庫載入SrcList相關切片及預測資料，回傳為list格式。
        '''
        result = []
        nExemptPieces = 0
        
        for file in list(filter(None,self.SrcList)):
            rowDict = {}
            rowDict["File"]=file
            #if file is None:
                #continue
            try:
                query = f'SELECT Src FROM sampleSrc \
                    WHERE File = "{file}" ORDER BY PartNO;'
                FileSrcQueryList = sqlite3Query(self.sql3File,query = query, ListForm=True)
            except Exception as e:
                MES = f"When query Src of {file} with SQL QUERY\n {query} \n in Test_result_Vis, the following error occurs:\n{e}\n"
                MPLOGGER.logW(MES,logFile="Exception.log")
                continue
            if FileSrcQueryList ==[None,None]:
                continue
            
            dateCand = DateExtractor.proc(
                    os.path.dirname(FileSrcQueryList[0]))
            if dateCand is not None:
                rowDict["Date"] = dateCand

            query = 'SELECT {colList} FROM sampleSrc \
                WHERE File = "{file}" ORDER BY PartNO;'.format(
                colList=','.join(self.sqlCols), file=file)
            segTuples = []
            try:
                #segTuples = list(sqlite3Query(self.sql3File,  query = query))
                segTuples = sqlite3Query(
                    self.sql3File,query = query, ListForm=True)
                segTuples = UniqueList(segTuples)
            except Exception as e:
                MES = f"When Apply the query {query} to build segTuples in Test_result_Vis.py, "
                MES += f"the following error occurs: \n {e}"
                MPLOGGER.logW(MES,logFile="Exception.log")
            
            if segTuples == []:
                continue
            #把PartNo轉成int
            if 'PartNO' in self.sqlCols:
                #idx = cols.index('PartNO')
                segTuples = [(int(float(x[0])),x[1],x[2]) for x in segTuples]
            #豁免機制，過程中可能會新增標籖，故回傳新的InfoScoreTable。
            #global InfoScoreTable
            if len(segTuples) > 1:
                segTuples, self.InfoScoreTable, nExemptPieces = ComputeExempt(
                    segTuples=segTuples,InfoScoreTable=self.InfoScoreTable,
                    printOnScreen = False,
                    MPLOGGER = MPlogger(logSubDir=f"{self.BertDatasetSubDir}/logs",logFile="Exempt.log"),
                    )
            MaxPN = max([x[0] for x in segTuples])
            temp = [None]*int(MaxPN+1)

            for stu in segTuples:
                #temp[stu[0]] = (LabelSep+stu[1]+LabelSep,stu[2])
                temp[stu[0]] = f"{self.LabelSep}{stu[1]}{self.LabelSep},{stu[2]}"
            
            CMP,CMPText = GetClassOfMostPieces(segTuples,self.InfoScoreTable)
            rowDict["Class Of Most Pieces"] = \
                f"{self.LabelSep}{CMP}{self.LabelSep}"
            rowDict["Text Of Class Of Most Pieces"] = CMPText
            CHS,CHSText = GetClassOfHighestScore(segTuples,self.InfoScoreTable)
            rowDict["Class Of Highest Score"] = \
                f"{self.LabelSep}{CHS}{self.LabelSep}"
            rowDict["Text Of Class Of Highest Score"] = CHSText
            rowDict["NumberOfExemptPieces"] = nExemptPieces
    
            #rowDict["InfoScoreSum"],rowDict["InfoScoreMean"] = \
            ScoreStasticDict = GetInfoScoreStastic(
                    segTuples=segTuples,
                    InfoScoreTable=self.InfoScoreTable,
                    nScoringSegUPD=self.nScoringSegUPD)
            for key in ["InfoScoreSum",
                        "InfoScoreMean",
                        "InfoScoreStd"]:
                rowDict[key] = ScoreStasticDict[key]
            #計算二元推薦之分析結果
            BMVResult = BinMissionVerifier(
                tpcTree=self.tpcTree,
                InfoScoreSum=rowDict["InfoScoreSum"],
                InfoScoreMean=rowDict["InfoScoreMean"],
                segTuples=segTuples,BinMissionDict=self.BinMissionDict).proc()
            for key in BMVResult.keys():
                if BMVResult[key] == True:
                    rowDict[key] = self.BinMissionDict[key].get("Icon","🌞")
            #計算文章類別組成片數
            if self.CountArticleComposition == True:
                rowDict["Compositions"] = SortedDictWithValue(dict(
                    Counter([x[1] for x in segTuples])))
            if self.SelectedFNPatList != []:
                for FNPat in self.SelectedFNPatList:
                    if FNPat in rowDict["File"]:
                        rowDict["Selected"] = "S"
            if "Target" in pathSpliter.proc(os.path.dirname(FileSrcQueryList[0])):
                rowDict["Target"] = "T"

            #如果偏好分數大於0（特定項目被推薦即1分），
            #將該文之正分切片片段取出，並合併，以產出摘要來源文本。
            if self.TextSummarization == True:
                if EvaluatePreference(
                        rowDict=rowDict,BMVResult=BMVResult)>0:
                    self.textPrepossingForSummary(file=file,segTuples=segTuples)
                    
            #針對PreambleCols，如果有被計算而賦值，則用之，否則使用預設值。
            #完成PreambleCols後，最後再加上切片文本清單。
            row = []
            for col in self.PreambleCols:
                if col in rowDict.keys():
                    row.append(rowDict[col])
                else:
                    row.append(self.PreambleColsDefault[col])


            #加上文本切片。
            row.extend(temp[:self.nLeftFileChunk])
            result.append(row)
        return result,self.InfoScoreTable


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
    for x in dataArray:
        result[x['Label']] = x['Color']
    return result

              
def ColorDictToColorDF(ColorDict):
    ColorDictTF = {}
    ColorDictTF["Label"] = list(ColorDict.keys())
    ColorDictTF["Color"] = list(ColorDict.values())
    ColorDF = pd.DataFrame(data=ColorDictTF)
    return ColorDF

def BuildColorDF(ColorDict,ClassTable):
    ColorDictTF = {}
    ColorDictTF["Label"] = list(ColorDict.keys())
    ColorDictTF["Color"] = list(ColorDict.values())
    ColorDF = pd.DataFrame(data=ColorDictTF)
    ColorDF['InfoScore'] = ColorDF['Label'].map(InfoScoreTable)
    ColorDF['InfoScore'] = ColorDF['InfoScore'].round().astype(int, errors='ignore')
    df_datasetCount = LoadDatasetCount(outputDir)
    ClassTableDF = pd.DataFrame(ClassTable).transpose()
    ColorDF['Chinese'] = ColorDF['Label'].map(ClassTableDF["CT"])
    ColorDF['Explaination'] = ColorDF['Label'].map(ClassTableDF["Explaination"])
    ColorDF['nAnotSamples'] = ColorDF['Label'].map(df_datasetCount["Loaded Samples Count"]).astype(int, errors='ignore')
    ColorDF_json = ColorDF.to_json(date_format='iso', orient='split')
    #Colortable_style_data_conditional=[
        #{'if': {'row_index': i, 'column_id': 'Color'}, 
         #'background-color': ColorDF['Color'][i],
         #'color': ColorDF['Color'][i]} 
        #for i in range(ColorDF.shape[0])
        #]
    Colortable_style_data_conditional =[]
    for label in ColorDict.keys():
        Colortable_style_data_conditional.append(
            {
                'if': {
                    'filter_query': '{{{col}}} = \"{val}\"'.format(
                        col="Label",val=label),
                    'column_id': 'Color',
                },
                'backgroundColor': ColorDict[label],
                'color': ColorDict[label]
            }
            )
        
    return ColorDF,ColorDF_json,Colortable_style_data_conditional

def DictToDF(Dict, Cols = ["keys","values"]):
    DictTF = {}
    DictTF[Cols[0]] = list(Dict.keys())
    DictTF[Cols[1]] = list(Dict.values())
    DF = pd.DataFrame(data=DictTF)
    return DF

class VisDatatableDFTransformer:
    '''
    將已預先得到的列清單rowslist，轉換成dataframe格式物件，
    並套用分數範圍篩選。
    '''
    def __init__(self,
                 PreambleCols,
                 rowslist,
                 InfoScoreTable,
                 InfoScoreSumLowerBound=-99999999,
                 InfoScoreSumUpperBound=99999999,
                 FixedTestFileBound=0,
                 VDDFSortParams={},
                 ):
        self.PreambleCols = PreambleCols
        self.rowslist = rowslist
        self.InfoScoreTable = InfoScoreTable
        self.InfoScoreSumLowerBound = InfoScoreSumLowerBound
        self.InfoScoreSumUpperBound = InfoScoreSumUpperBound
        self.FixedTestFileBound = FixedTestFileBound
        
        if VDDFSortParams == {}:
            #依星級及綜分排序
            self.VDDFSortParams = {
                "by":['Twins','Rating','InfoScoreSum'],
                "ascending":[True,False,False]
                }
        else:
            self.VDDFSortParams = VDDFSortParams
            #self.ExportDatabasePath = ExportDatabasePath
        #self.show()
        
    def show(self):
        print("The params for VisDatatableDFTransformer:")
        pp = pprint.PrettyPrinter(indent=4)
        for x in self.rowslist[:3]:
            print("="*50)
            pp.pprint(x)
            print("="*50)
        print("InfoScoreSumLowerBound is {}".format(self.InfoScoreSumLowerBound))
        print("InfoScoreSumUpperBound is {}".format(self.InfoScoreSumUpperBound))
        print("FixedTestFileBound is {}".format(self.FixedTestFileBound))

    def run(self):
        if self.FixedTestFileBound!=0 and len(self.rowslist)>self.FixedTestFileBound:
            #random.shuffle(rowslist)
            #rowslist = rowslist[:FixedTestFileBound]
            self.rowslist = RandomSample(self.rowslist,self.FixedTestFileBound)

            
        bar_df = pd.DataFrame(self.rowslist)
        #print(bar_df.dtypes)
        #time.sleep(100)
        columns=self.PreambleCols+[
            str(i) for i in range(len(bar_df.columns)-len(self.PreambleCols))]
        #定義欄位名
        bar_df.columns = columns
        #bar_df['Date'] = bar_df['Date'].astype(str)
        bar_df["NumberOfExemptPieces"].replace({0: ""}, inplace=True)
        #依分數區間篩濾
        bar_df = DFfilter(bar_df, 
            InfoScoreSumLowerBound = self.InfoScoreSumLowerBound,
            InfoScoreSumUpperBound = self.InfoScoreSumUpperBound
            )
        
        if bar_df.shape[0] != 0:
            if "linux" in platform.system().lower():
                bar_df = multicoreJob(nProcess=nProcess).parallelize_dataframe(bar_df, CountRating)
            else:
                #bar_df.loc[:'Rating'] = ""
                bar_df = multicoreJob(nProcess=1).parallelize_dataframe(bar_df, CountRating)
                #bar_df['Rating'] = bar_df.apply(
                    #lambda x:'⭐'*(min(x.InfoScoreSum//1000,5)+min((x.InfoScoreMean-100)//50,3)*2),
                    #axis=1)
    
        #bar_df['Article Class'] = bar_df.max(axis=1,skipna=True)
        #numCols=[str(i) for i in range(len(bar_df.columns)-2)]
        #bar_df = bar_df[['Article Class','File']+numCols]
    
        print("Finished building bar_df")
        ShowElapsedTime(start_time)
        #dash表格儲存格內容型別只接受string, number, boolean，所以將類別組成字典轉換為字串。
        #bar_df['Compositions'] = bar_df['Compositions'].apply(json.dumps)
        bar_df['Compositions'] = bar_df['Compositions'].apply(lambda x:json.dumps(x, indent=4))#.replace("\n","  \n"))
        
        #為了將無群組的文本(群組值為空字串)排在後面，先替代成np.naj
        #排序好後，再替代回空字串
        bar_df['Twins'] = bar_df['Twins'].replace('',np.nan)
        if len(bar_df) > 0:
            bar_df = bar_df.sort_values(**self.VDDFSortParams)
        else:
            #依檔名排序
            bar_df = bar_df.sort_values('File')
        bar_df['Twins'] = bar_df['Twins'].replace(np.nan,'')
        
        #bar_df['File'] = bar_df['File'].apply(getMFNFromFN)
        '''
        bar_df_saveTemp = bar_df.copy()
        bar_df_saveTemp['File'] = bar_df_saveTemp['File'].apply(getMFNFromFN)
        OUTPUTMAIN = os.path.join(datasetDir,"Full_bar_df")
        dfOutputer(bar_df_saveTemp,OUTPUTMAIN).run()
        '''

        return bar_df

def Build_ColorTable(ColorDF):
    return Build_DataArrayTable(
            "Colortable",ColorDF.to_dict('records'),
            ShownColumns=['Color', 'Label', 'InfoScore','Chinese', 'nAnotSamples', 'Explaination'],
            style_cell=Colortable_style_cell,
            style_cell_conditional=Colortable_style_cell_conditional,
            style_data_conditional=Colortable_style_data_conditional,
            MPLOGGER = MPLOGGER
            )

#def Build_LabelSelector(app,df):
def Build_LabelSelector(app,Roots=[]):
    #return layout_interactivity.create_layout(app,df)
    return layout_interactivity.create_layout(app,Roots=Roots)

def Build_JaalViewCard():
    #JaalViewMain(createMode = True)
    #JaalViewMain()
    #jaalIP = "http://localhost:8053/"
    jaalIP = f"http://{getIP()}:8053"
    print("jaalIP",jaalIP)
    #time.sleep(10)
    return html.Iframe(src=jaalIP,
                style={"height": "1067px", "width": "100%"})

def ISMarksAnalysis(df):
    #SortedIS = list(df['InfoScoreSum'].sort_values().reset_index(drop=True))
    SortedIS = sorted(list(df['InfoScoreSum']))
    LenSIS = len(SortedIS)
    #ISMarks:0%,10%,20%,30%,...100%分數節點
    ISMarks = [SortedIS[min(int(LenSIS*0.1*i),LenSIS-1)] for i in range(11)]
    ISMarks = [int(x) for x in ISMarks]
    #"InfoScore Range" bar 初始取第500高的分數當下限
    print("ISMarks[0:20]", ISMarks[0:20])
    print("SortedIS[0:100]", SortedIS[0:100])
    AutoISlbd = SortedIS[max(-3000,-len(SortedIS))]
    AutoISubd = SortedIS[-1]
    return AutoISlbd,AutoISubd,ISMarks
def Build_InfoScore_Range_Bar(df):
    AutoISlbd,AutoISubd,ISMarks = ISMarksAnalysis(df)
    return rc.CustomRangeSlider(
           id="InfoScore Range", min=ISMarks[0],
           max=ISMarks[-1], 
           label="InfoScore Range",
           #step=1,
           marks = {i: str(i) for i in ISMarks},
           value = [AutoISlbd,AutoISubd]
           )
 
def Build_VisDatatable_style(df, ColorDict, BinMissionDict):
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
    CenterCols = ["Selected","Target"]+list(BinMissionDict.keys())
    for col in CenterCols:
        style_data_conditional.extend([
            {'if': {'column_id': col},
             'textAlign': 'center'} 
            ])
    
    if "Twins" in df.columns:
        '''
        TwinsColorDict = {}
        for ct,TwinGroup in enumerate(df["Twins"].unique()):
            if TwinGroup =="":
                continue
            TwinsColorDict[TwinGroup] = RandomColor(777+ct)
        '''
        for TwinGroup in TwinsColorDict:
            style_data_conditional.extend([
                {
                    'if': {
                        'filter_query': f'{{Twins}} = "{TwinGroup}"',
                        'column_id': "Twins",
                    },
                    'backgroundColor': TwinsColorDict[TwinGroup],
                    'color': TwinsColorDict[TwinGroup]
                }
                ])

    '''
    style_data_conditional.extend([
        {'if': {
            #'filter_query': '{Twins} != ""',
            'filter_query': '{Twins} == "Group {num}"',
            'column_id': "Twins"},
         'backgroundColor':"#EEFF7A",
         'color': '#EEFF7A'} 
        ])
    '''  
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
            'width': '25px',
            'minWidth': '25px',
        },{
            'if': {'column_id': "InfoScoreSum"},
            'width': '25px',
            'minWidth': '25px',
        },{
            'if': {'column_id': "InfoScoreMean"},
            'width': '18px',
            'minWidth': '18px',
        },{
            'if': {'column_id': "InfoScoreStd"},
            'width': '18px',
            'minWidth': '18px',
        },{
            'if': {'column_id': "NumberOfMatchingBlock"},
            'width': '18px',
            'minWidth': '18px',
        },{
            'if': {'column_id': "NumberOfMatchingBlockWithKW"},
            'width': '18px',
            'minWidth': '18px',
        },{
            'if': {'column_id': "NumberOfExemptPieces"},
            'width': '12px',
            'minWidth': '12px',
        },{
            'if': {'column_id': "Date"},
            'width': '12px',
            'minWidth': '12px',
        },{
            'if': {'column_id': "Selected"},
            'width': '12px',
            'minWidth': '12px',
        },{
            'if': {'column_id': "Target"},
            'width': '12px',
            'minWidth': '12px',
        },{
            'if': {'column_id': "File"},
            'width': '200px',
            'minWidth': '200px',
        },{
            'if': {'column_id': "Summary"},
            'width': '14px',
            'minWidth': '14px',
        },{
            'if': {'column_id': "Twins"},
            'width': '12px',
            'minWidth': '12px',
        }
    ]
            
    for col in BinMissionDict.keys():
        style_cell_conditional.extend([{
            'if': {'column_id': col},
            'width': '10px',
            'minWidth': '10px',
            'maxWidth': '10px',
        }])
    heatmapStyle,legend = discrete_background_color_bins(df,columns=['InfoScoreSum'],cmap='Blues')
    style_data_conditional+= heatmapStyle
    heatmapStyle,legend = discrete_background_color_bins(df,columns=['InfoScoreMean'],cmap='Oranges')
    style_data_conditional+= heatmapStyle
    style_cell={
        'width': '10px',
        'minWidth': '5px',
        'maxWidth': '10px',
        'overflow': 'hidden',
        'textOverflow': 'ellipsis',
    }
    def tooltipVal(value):
        if value == None:
            return ""
        if type(value) in [list,tuple] and len(value) == 2:
            res = "Label: {}\n\nText: {}".format(
                value[0].replace("#T#",""),
                    NewlineNormalizer(max_newlines=12).proc(str(value[1])))
        #["Label: {}".format(value[0].replace("#T#",""),
                           #
        else:
            res = NewlineNormalizer(max_newlines=12).proc(str(value))
        return res.replace("\n", "  \n")
    
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


#創建VisDatatable，並回傳目前頁面中的檔名及分數資訊，
#供Build_Pred_Block中的PredsData及dash_pivottable.PivotTable使用。
def Build_VisDatatable(
        df, 
        sql3File,
        ColorDict, BinMissionDict,
        InfoScoreTable = {},
        page_current=0, page_size=10, 
        CutRange=[0,30],
        derived_query_structure = None,
        filter_query = '',
        FilteredDF_OPTFN=""
        ):
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running Build_VisDatatable.")
    #print("derived_filter_query_structure", derived_query_structure)
    print("filter_query", filter_query)
    #FilteredPreambleColsFN = FilteredDF_OPTFN+".sql3"
    #df = dfFromSQLite3(FilteredPreambleColsFN)
    
    if VisDatatable_page_action == 'custom':
        PartDF = df.iloc[
            page_current*page_size:(page_current+ 1)*page_size]
    elif VisDatatable_page_action == 'native':
        PartDF = df
        
    #PartDF = df_upd_filter_query(PartDF, filter_query)
    #print("IN BVD,PartDF['File']",PartDF['File'])
    rowslist = []
    sqlCols = ['PartNO','pred_Type','text']
    LabelSep = "#T#"
    #查詢檔案清單之切片推論結果
    CutRangeMax = 0
    #segTagsDict為各檔案的片段類別清單，用於計算文件相似度。
    for file in PartDF['File']:
        #title = file.rstrip(".txt")
        #segTagsDict[file] = ['' for i in range(segTagsUPD)]
        #if file is None:
            #continue
        #print("file", file)
        colList=','.join(sqlCols)
        query = f'SELECT {colList} FROM sampleSrc \
            WHERE File = "{file}" AND \
                (PartNO BETWEEN {CutRange[0]} AND {CutRange[1]-1})\
                ORDER BY PartNO;'
        #query = f'SELECT {colList} FROM sampleSrc \
            #WHERE File = "{file}" AND \
                #(PartNO BETWEEN {CutRange[0]} AND {segTagsUPD-1})\
                #ORDER BY PartNO;'
        #print("query",query)
        segTuples = []
        try:
            segTuples = list(sqlite3Query(sql3File,  query = query))
        except Exception as e:
            MES = f"When Apply the query {query} to build segTuples with {sql3File} in Test_result_Vis.py,"
            MES += f"the following error occurs: \n {e}\n"
            MPLOGGER.logW(MES,logFile="Exception.log")
            
        #print("segTuples af q",segTuples)
        #把PartNo轉成int
        if 'PartNO' in sqlCols:
            #idx = cols.index('PartNO')
            segTuples = [(int(float(x[0])),x[1],x[2]) for x in segTuples]
            segTuples = sorted(segTuples,key = lambda x:x[0])
        #豁免機制，過程中可能會新增標籖，故回傳新的InfoScoreTable。
        #global InfoScoreTable
        if len(segTuples) > 1:
            segTuples, InfoScoreTable, nExemptPieces = ComputeExempt(
                segTuples=segTuples,InfoScoreTable=InfoScoreTable,
                printOnScreen = False)
            
        query = f'SELECT MAX(PartNO) FROM sampleSrc \
            WHERE File = "{file}";'
        try:
            query_res = int(sqlite3Query(sql3File,query = query,ListForm=True)[0])
            MaxPN = min(query_res+1,300)
        except Exception as e:
            MES = f"When Apply the query {query} to get MaxPN in Test_result_Vis.py,"
            MES += f"the following error occurs: \n {e}"
            MPLOGGER.logW(MES,logFile="Exception.log")
            
            MaxPN = 1
            
        #MaxPN = min(max([x[0] for x in segTuples])+1,300)
        CutRangeMax = max(CutRangeMax,int(MaxPN))
        #infer_pieces = [None]*int(MaxPN)
        infer_pieces = [None]*int(min(CutRange[1],CutRangeMax)+1)
        #stu樣本：(0, 'AUKUS', '法媒看澳洲毁约潜舰军购 叹欧洲势衰2021/9/'）
        for stu in segTuples:
            if stu[0] < CutRange[1]:
            #temp[stu[0]] = (LabelSep+stu[1]+LabelSep,stu[2])
                infer_pieces[stu[0]] = f"{LabelSep}{stu[1]}{LabelSep},{stu[2]}"
        rowslist.append(infer_pieces)

        
    part_infer_df = pd.DataFrame(rowslist)
    part_infer_df = part_infer_df[[
        i for i in range(CutRange[0],min(CutRange[1],CutRangeMax))]]
    part_infer_df.columns = [str(x) for x in part_infer_df.columns]
    PartDF = pd.concat([PartDF.reset_index(drop=True),
                        part_infer_df.reset_index(drop=True)],axis=1)
    #標題欄位，只顯示主檔名，不顯示完整路徑。
    PartDF['File'] = PartDF['File'].apply(getMFNFromFN)
    #PartDF_File = PartDF[['InfoScoreSum','File']].sort_values(
        #by=['InfoScoreSum'],ascending=False)['File'][:30]
    
    PartDF_File = PartDF[['InfoScoreSum','File']]
    data=PartDF.to_dict('records')
    if data == []:
        data = [dict()]
    style_data_conditional, style_cell_conditional, style_cell, tooltip_data \
        = Build_VisDatatable_style(PartDF, ColorDict, BinMissionDict)
    columns=[{'name': str(i), 'id': str(i), 'hideable':True #'deletable':True
              } for i in PartDF.columns]
    #open("temp.txt","wt",encoding='utf-8').write(str(data))
    ShowElapsedTime(start_time)

    print("Finished Running Build_VisDatatable.")
    return [dash_table.DataTable(
                id='VisDatatable',
                columns=columns,
                tooltip ={i: {
                     'value': str(i),
                     'use_with': 'both'  # both refers to header & data cell
                 } for i in PartDF.columns},
                page_current=page_current,
                page_size=page_size,
                #page_action='native',
                row_selectable ='multi',
                page_action=VisDatatable_page_action,
                data=data,
                tooltip_data=tooltip_data,
                css=[{'selector': '.dash-table-tooltip',
                      'rule': 'background-color: white; color: black;border: solid;border-color: red; width:500px !important; max-width:500px !important;',
                      #'z-index': '0',
                      #'position': 'absolute',
                      },
                     ],
                #filter_action='native',
                filter_action='custom',
                filter_options={"case":"insensitive"},
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
                #row_deletable=True,
                editable=True,
                )
        ],PartDF_File,CutRangeMax

def BuildPredsdf(sql3File, FileList):
    '''
    tempList = []
    FileList = list(df['File'])
    for src in SrcList:
        #if src.split("\\")[-1] in FileList:
        if src in FileList:
            tempList.append(src)
    '''
    #tempList = ListCap(FileList,list(df['File']))
    rowslist = []
    #SrcList = GetSrcList(sql3File)
    #ShowElapsedTime(start_time)
    print("Building Predsdf.")
    #print("There are {} files in tempList.".format(len(tempList)))
    #cols = ['Src', 'pred_Type']
    cols = ['File', 'pred_Type']
    #for file in tempList:
    '''
    for file in FileList:
        if not file.endswith(".txt"):
            file = file+".txt"
        #print("file",file)
        query = 'SELECT {colList} FROM sampleSrc \
            WHERE File = "{file}";'.format(
            colList=','.join(cols), 
            file = file)
        rowslist.extend(list(sqlite3Query(sql3File,  query = query)))
    '''
    #考慮到sql3File中的File欄位可能為不含txt副檔名之id或為txt完整檔名，將FileList進行兩種情況之擴增
    FileList = list(FileList)
    FileList.extend([x if x.endswith(".txt") else x+".txt" for x in list(FileList)])
    colList=','.join(cols)
    FileListPat =','.join([f'"{x}"' for x in FileList])
    
    query = f'SELECT {colList} FROM sampleSrc \
        WHERE File IN ({FileListPat});'
    #print("sql3File in BuildPref",sql3File)
    rowslist.extend(sqlite3Query(sql3File,query = query,ListForm = True))
    #print("fin query")
    #print("rowslist",rowslist)
    rowslist = [(getMFNFromFN(x[0]),)+x[1:] for x in rowslist]
    result = pd.DataFrame(rowslist, columns =['Src', 'pred_Type'])
    
    query = f'SELECT File FROM \
        (SELECT File,COUNT(pred_Type) AS CT FROM sampleSrc GROUP BY File)\
        ORDER BY CT DESC;'
    FileListWithNPiecesDESC = sqlite3Query(sql3File,query = query,ListForm = True)
    FileListWithNPiecesDESC = list(filter(None, FileListWithNPiecesDESC))
    ShowElapsedTime(start_time)
    print("Finishing building Predsdf.")
    #print("rowslist",rowslist)
    return result,FileListWithNPiecesDESC
    
def VisDFToPredsDF(df):
    def getLabelFromVisCellVal(CellStr):
        print("CellStr",CellStr)
        print("type(CellStr)",type(CellStr))
        LabelsList = re.match('^#T#.*#T#',CellStr)
        if LabelsList is not None:
            return LabelsList[0].strip("#T#")
        else:
            return ""
    dfcols = df.columns.tolist()
    print(dfcols)
    
    r = re.compile("^\d+$")
    NumCols = list(filter(r.match, dfcols))
    df = df[['File']+NumCols]
    df = df.set_index('File')
    #for col in NumCols:
    print("df b4",df)
    df = df.applymap(
        lambda x:getLabelFromVisCellVal(x) if type(x) == str else x)
    print("df af",df)
    raise Exception
    rowslist = []
    
    PredsDF = pd.DataFrame(rowslist, columns =['Src', 'pred_Type'])
    return PredsDF

def Build_Pred_Block(
        df, sql3File, ColorDict):#, SrcList):#,
        #PartDF_File = pd.DataFrame(columns=['File','InfoScoreSum'])):
    #PartDF_File = PartDF_File[['InfoScoreSum','File']].sort_values(
        #by=['InfoScoreSum'],ascending=False)
    #PartDFFL = list(PartDF_File['File'])
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running Build_Pred_Block function")
    #LevelDVisProcessor(df=PartDF, VisPath = 'Src')
    print("="*50)
    SrcList = GetSrcList(sql3File)
    SrcList = ListCap(SrcList,list(df['File']))
    PredsDF,FileListWithNPiecesDESC = BuildPredsdf(
        sql3File, SrcList)
    #如果檔案總數太多，則樹狀圖S1只使用前100個最多切片的檔案繪圖。
    FileListWithNPiecesDESC = ListCap(SrcList,FileListWithNPiecesDESC)
    #print("FileListWithNPiecesDESC",FileListWithNPiecesDESC)
    if len(FileListWithNPiecesDESC)> 100:
        FileListWithNPiecesDESC = [
            x.rstrip(".txt") for x in FileListWithNPiecesDESC]
        
        #PredsDF_S1 = BuildPredsdf(FileListWithNPiecesDESC[:100])[0]
        PredsDF_S1 = PredsDF[PredsDF['Src'].isin(FileListWithNPiecesDESC[:100])]
    else:
        PredsDF_S1 = PredsDF
    if len(SrcList)> 2000:
        VisPath_type = ['pred_Type']
    else:
        VisPath_type = ['pred_Type', 'Src']
    print("Finished Running Build_Pred_Block function")
    '''
    PredsData = [["Src","pred_Type"]]
    if len(PartDFFL) <40:
        #產製該頁前四十個檔案推論結果的樞紐分析表。
        PredsDF_Part = PredsDF[PredsDF['Src'].isin(PartDFFL)]
        PredsData += PredsDF_Part[PredsDF_Part['Src'].isin(
            PartDFFL[:40])].values.tolist()
    '''
    return [dcc.Graph(
            #id="Sunburst-graph",
            id="S1",
            figure=LevelDVisProcessor(
                df=PredsDF_S1,
                #method="sunburst",
                method="treemap",
                VisPath = ['Src','pred_Type'], 
                color='pred_Type',
                color_discrete_map=ColorDict,
                OptAnnotation = True,
                MPLOGGER = MPLOGGER,
                ).run()
            ),
            dcc.Graph(
                #id="Sunburst-graph",
                id="S2",
                figure=LevelDVisProcessor(
                    df=PredsDF,
                    method="treemap",
                    #method="treemap",
                    VisPath = VisPath_type, 

                    color='pred_Type',
                    color_discrete_map=ColorDict,
                    OptAnnotation = True,
                    ).run()
                        ),
            ]



def Build_Twins_Block(df):#, TwinsColorDict):
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running Build_Twins_Block function")
    #LevelDVisProcessor(df=PartDF, VisPath = 'Src')
    ShowElapsedTime(start_time)
    print("Finished Running Build_Pred_Block function")
    df = df[["File","Twins"]]
    df = df[df["Twins"]!=""]
    if len(df) == 0:
        return "There is no twins group."
    TwinsData = [["File","Twins"]]
    #if len(FileList) <40:
        #如果輸入的檔案清單少於40個，則產製樞紐分析表。
    TwinsData += df.values.tolist()
    if len(df["File"])> 1000:
        VisPath_type = ['Twins']
    else:
        VisPath_type = ['Twins', 'File']
    return [dcc.Graph(
                    id="S3",
                    figure=LevelDVisProcessor(
                        df=df,
                        #method="sunburst",
                        method="treemap",
                        #VisPath = ['Twins','File'], 
                        VisPath = VisPath_type, 
                        color='Twins',
                        color_discrete_map=TwinsColorDict,
                        OptAnnotation = True,
                        OptAnnotation_Value = False,
                        ).run()
                        ),
            dash_pivottable.PivotTable(
                    id=("%s" % dte.datetime.now())+"_Twins",
                    #id='PVT',
                    data=TwinsData,
                    #cols=["pred_Type"],
                    #rows=["Src"],
                    colOrder="value_z_to_a",
                    rowOrder="value_z_to_a",
                    vals=["Count"],
                    menuLimit=5000,
                    rendererName="Table Heatmap"
                    )
            ]



def Build_ShowingFilePVT(sql3File, FileList=[]):
    
    def BuildInferDictTable(PredsDF_Part,PartDFFL):
        #產製各檔案切片推論結果字典表格。
        if len(PartDFFL) <40:
            PVTDict = []
        else:
            PVTDF = PredsDF_Part.groupby(by=["Src","pred_Type"]).sum()
            PVTDF['count'] = 1
            PVTDict = PVTDF.groupby(level=0).apply(lambda df: sorted(
                df.xs(df.name)['count'].to_dict().items(),
                key = lambda x: x[1],reverse=True)).to_dict()      
            PVTDict = [{'Src':k, 'pred_Type':str(v)} for k,v in PVTDict.items()]
            PVTDict = sorted(PVTDict, key=lambda x: PartDFFL.index(x['Src']))
        return dash_table.DataTable(
                id='S5',
                data = PVTDict,
                columns=[
                    {"name": i, "id": i} for i in ["Src","pred_Type"]
                ],
                page_current=0,
                page_size=30,
                #page_action='custom',
                page_action='native',
                filter_action='native',
                merge_duplicate_headers=True,
                #data=RowConstraint,
                #html.H2(id = "Constraint Dict", children = RowConstraint),
                style_cell={
                    'backgroundColor': 'rgb(150, 150, 150)',
                    'color': 'white',
                    'textAlign': 'left',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                },
                row_deletable=True,
                editable=True,
                )
    
    print("="*50)
    ShowElapsedTime(start_time)
    print("Running Build_ShowingFilePVT function")
    if type(FileList) == 'pandas.core.series.Series':
        FileList=list(FileList)
    PredsDF,FileListWithNPiecesDESC = BuildPredsdf(sql3File, FileList)
    PredsData = [["Src","pred_Type"]]
    if len(FileList) <40:
        #如果輸入的檔案清單少於40個，則產製樞紐分析表。
        PredsData += PredsDF.values.tolist()
    ShowElapsedTime(start_time)
    print("Finished running Build_ShowingFilePVT function")
    #print("PredsData",PredsData)

    return dash_pivottable.PivotTable(
        id="%s" % dte.datetime.now(),
        #id='PVT',
        data=PredsData,
        #cols=["pred_Type"],
        #rows=["Src"],
        colOrder="value_z_to_a",
        rowOrder="value_z_to_a",
        vals=["Count"],
        menuLimit=5000,
        rendererName="Table Heatmap"
        )

def Build_PerformancePVT(df):
    #print("In BPFPVT len(df)",len(df))

    cols = ["InfoScoreSum","InfoScoreMean","Date","Target","Selected"]+list(BMKeys)
    df = df[cols]
    #df.columns = df.columns+["InfoScoreSumInterval","InfoScoreMeanInterval"]
    #df["InfoScoreSumInterval"] = np.nan
    #df["InfoScoreMeanInterval"] = np.nan
    #df.loc[:,"InfoScoreSumInterval"] = ""
    #df.loc[:,"InfoScoreMeanInterval"] = ""
    df.insert(df.shape[1],"InfoScoreSumInterval","")
    df.insert(df.shape[1],"InfoScoreMeanInterval","")
    #print("df in BPV",df)

    #if "linux" not in platform.system().lower():
        #nProcess = 1
        #1
    #else:
        #nProcess = mp.cpu_count()-1
    nProcess = mp.cpu_count()-1
    #try:
    df = multicoreJob(nProcess=nProcess).parallelize_dataframe(df, PerformanceColExt)
    
    #df[col] = df.get(col).astype('category') will Raise SettingWithCopyWarning;    
    pd.options.mode.chained_assignment = None
    for col in df.columns:
        if col not in ["InfoScoreSum","InfoScoreMean"]:
            df[col] = df.get(col).astype('category')
    pd.options.mode.chained_assignment = 'warn'
    PVTData = [df.columns.tolist()]
    #print("PVTData b4",PVTData)
    PVTData += df.values.tolist()
    #print("PVTData af",PVTData)
    return dash_pivottable.PivotTable(
        id="%s_%s PFPVT" % (
            dte.datetime.now(),'%030x' % random.randrange(16**30)),
        data=PVTData,
        cols=["Recommanded"],
        rows=["Target","Selected"],
        colOrder="value_z_to_a",
        rowOrder="key_a_to_z",
        vals=["Count"],
        menuLimit=5000,
        rendererName="Table Heatmap"
        )

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
                #page_action='custom',
                page_action='native',
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

def Build_PerformanceTable(df):
    '''
    DFPreambleColsFN:DFPreambleCols_df_ALL.sql3
    '''
    print("IN BPF, df",df)
    if len(df) == 0:
        return

    if os.path.isfile(DFPreambleColsFN):
        query = f'SELECT SUM(CASE WHEN \
            Selected = "S" AND InfoScoreSum >999 THEN 1 ELSE 0 END) AS CountSR \
            From sampleSrc;'
        CountSR = sqlite3Query(
            DFPreambleColsFN, query = query,ListForm = True)
        print("CountSR", CountSR)

    return [dcc.Graph(
            #id="Sunburst-graph",
            id="S1",
            figure=LevelDVisProcessor(
                df=PredsDF_S1,
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
                    VisPath = VisPath_type, 

                    color='pred_Type',
                    color_discrete_map=ColorDict,
                    OptAnnotation = True,
                    ).run()
                        ),
            ]

def cmapSet():
    result = []
    for CSet in ["Dark24", "Light24", "Plotly"]:
        result.extend(getattr(px.colors.qualitative,CSet))
    result = UniqueList(result)
    return result

def RowsFilter(df, selectedLabels, sql3File, keywords=[]):#, PiecesBound=[1, 100]):
    #ShowingRows = []
    def CountKeyWordMatchingRow(df, keywords):
        #print("start to compute conDF")
        conDF = concat_df_str1(df.drop(PreambleCols, axis=1).applymap(
            lambda x:','.join(str(x).split(",")[1:]) if x is not None else ""))
        return df[conDF.apply(lambda x:re.match(".*"+keywords[0],x) is not None)]
    def CountMatchingBlockOld(df, selectedLabels, keywords = []):
        patt = '|'.join(["#T#{}#T#".format(x) for x in selectedLabels])
        nMatchingBlockSeries = df.drop(PreambleCols, axis=1).apply(
            lambda r: r.astype(str).str.contains(
            patt, case=False)).apply(
                lambda row: sum(row[:]==True) ,axis=1)
        if keywords == []:
            nMatchingBlockWithKWSeries = pd.DataFrame(
                "", index=np.arange(len(df)),columns=["KW"])
        else:
            #sample:假設r是"#T#CPTPP#T#,会是重要价值伙伴。它呼吁CPTPP会员国"
            #選擇Label為CPTPP
            #則re.sub(patt,"",str(r))是"会是重要价值伙伴。它呼吁CPTPP会员国"
            nMatchingBlockWithKWSeries = df.drop(PreambleCols, axis=1).applymap(
                lambda r: re.match(patt,str(r)) and (
                    re.match(".*"+keywords[0],re.sub(patt,"",str(r))) is not None)).apply(
                    lambda row: sum(row[:]==True) ,axis=1)
            nMatchingBlockWithKWSeries = nMatchingBlockWithKWSeries.astype(int)
        #使用int64而不使用float
        nMatchingBlockSeries = nMatchingBlockSeries.astype(int)
        return nMatchingBlockSeries, nMatchingBlockWithKWSeries
    
    def CountMatchingBlock(df, selectedLabels, keywords = []):
        patt = '|'.join(["#T#{}#T#".format(x) for x in selectedLabels])
        #FileListPat =' OR '.join([
            #f'(File LIKE "%{x}%")' for x in df["File"]])
        FileListPat =','.join([
            f'"{x}"' for x in df["File"]])
        #pred_Type_patt =' OR '.join([
            #f'(pred_Type LIKE "%{x}%")' for x in selectedLabels])
        pred_Type_patt =','.join([
            f'"{x}"' for x in selectedLabels])        
        
        query = f'SELECT File,SUM(CT) From \
            (SELECT File,pred_Type, COUNT() AS CT FROM sampleSrc \
            WHERE pred_Type IN ({pred_Type_patt}) AND File IN ({FileListPat}) GROUP BY File,pred_Type) \
                GROUP BY File;'
        #print("query", query)
        '''
        query = f'SELECT File,SUM(CT) From \
            (SELECT File,pred_Type, COUNT() AS CT FROM sampleSrc \
            WHERE ({pred_Type_patt}) GROUP BY File,pred_Type) \
                GROUP BY File;'
        '''
        nMatchingBlockSeries = sqlite3Query(
            sql3File, query = query,ListForm = True)
        #nMatchingBlockSeries = [('File A.txt', 10), ('File B', 2)]
        #print("nMatchingBlockSeries b4",nMatchingBlockSeries)
        #nMatchingBlockSeries = [x for x in nMatchingBlockSeries 
                                #if x[0] in list(df["File"])]
        #print("nMatchingBlockSeries",nMatchingBlockSeries)
        nMatchingBlockSeries = pd.DataFrame(
            nMatchingBlockSeries,columns=['File','NumberOfMatchingBlock'])
        #使用int64而不使用float
        nMatchingBlockSeries['NumberOfMatchingBlock']=nMatchingBlockSeries[
            'NumberOfMatchingBlock'].astype(int)
        #print("nMatchingBlockSeries",nMatchingBlockSeries[:10])
        #print('len(nMatchingBlockSeries)',len(nMatchingBlockSeries))
        #print("FileListPat",FileListPat)
        if keywords == []:
            nMatchingBlockWithKWSeries = pd.DataFrame(df['File'])
            nMatchingBlockWithKWSeries['NumberOfMatchingBlockWithKW'] = ""
        else:
            KWListPat ='|'.join([
                f'"{x}"' for x in keywords])
            
            query = f'SELECT File,SUM(CT) From \
                (SELECT File,pred_Type, COUNT() AS CT FROM sampleSrc \
                WHERE (pred_Type IN ({pred_Type_patt})) AND \
                (File IN ({FileListPat})) AND \
                    (text REGEXP ({KWListPat})) \
                    GROUP BY File,pred_Type) \
                    GROUP BY File;'
            nMatchingBlockWithKWSeries = sqlite3Query(
            sql3File, query = query,ListForm = True)
            nMatchingBlockWithKWSeries = pd.DataFrame(
                nMatchingBlockWithKWSeries,columns=['File','NumberOfMatchingBlockWithKW'])
            nMatchingBlockWithKWSeries['NumberOfMatchingBlockWithKW'
                ]=nMatchingBlockWithKWSeries['NumberOfMatchingBlockWithKW'].astype(int)
        result = pd.merge(nMatchingBlockSeries,nMatchingBlockWithKWSeries,
                          on='File')
        return result
    
    #newPiecesBoundMinMax = PiecesBound
    #如果關鍵字設定非空，進行列篩選。
    print("In RF, KW",keywords)
    #if keywords != []:
        #df = CountKeyWordMatchingRow(df, keywords)
    print("selectedLabels",selectedLabels)
    if selectedLabels == []:
        FilteredDF = df
    else:
        #query = 'SELECT DISTINCT File FROM sampleSrc \
            #WHERE pred_Type LIKE {Tags};'.format(
            #Tags=' OR '.join([f'"%{x}%"' for x in selectedLabels]))
        pred_Type_patt =','.join([
            f'"{x}"' for x in selectedLabels])  
        query = f'SELECT DISTINCT File FROM sampleSrc \
            WHERE pred_Type IN ({pred_Type_patt});'

        FileList = sqlite3Query(
            sql3File, query = query,ListForm = True)
        FilteredDF = df[df['File'].isin(FileList)]
        #FilteredDF2 = VDT_DFBuilder.run(ListCap(FileList,df['File']))
        
        #print("FilteredDF2",FilteredDF2)
        #print("FilteredDF==FilteredDF2",FilteredDF==FilteredDF2)
        #raise Exception

        #patt = '|'.join(["#T#{}#T#".format(x) for x in selectedLabels])
        #FilteredDF = df[df.apply(
            #lambda r: r.astype(str).str.contains(
            #patt, case=False).any(), axis=1)]
        MBDF = CountMatchingBlock(FilteredDF, selectedLabels, keywords)
        FilteredDF = FilteredDF.drop(["NumberOfMatchingBlock","NumberOfMatchingBlockWithKW"],axis=1)
        FilteredDF = pd.merge(FilteredDF, MBDF,on = 'File')
        #print("nMatchingBlockSeries",nMatchingBlockSeries)
        #print("nMatchingBlockWithKWSeries",nMatchingBlockWithKWSeries)
        #df["NumberOfMatchingBlock"] = nMatchingBlockSeries
        #df["NumberOfMatchingBlockWithKW"] = nMatchingBlockWithKWSeries
        
        #FilteredDF = df[df["NumberOfMatchingBlock"].between(
            #PiecesBound[0], PiecesBound[1])]

        #FilteredDF = df[df.apply(
            #any([lambda r: r.astype(str).str.contains(
            #label, case=False) for label in selectedLabels]), axis=1)]
        #FilteredDF = df['Scrap' in df[df.columns][0]).any(axis=1)]
            #(df[df.columns].str.contains('Scrap')).any(axis=1)]
        #print("IN RF, FilteredDF",FilteredDF, FilteredDF.shape)
        #raise Exception
        #masked_nMBS = np.ma.masked_equal(
            #nMatchingBlockSeries, 0, copy=False)
        '''
        masked_nMBS = df["NumberOfMatchingBlock"][df["NumberOfMatchingBlock"]!=0]
        
        if len(masked_nMBS) == 0:
            newPiecesBoundMinMax = [0,0]
        else:
            newPiecesBoundMinMax = [max(min(masked_nMBS),1),
                              max(df["NumberOfMatchingBlock"])]
        '''
    return FilteredDF#, newPiecesBoundMinMax


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
    '''
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
    '''
    PartDF = pd.DataFrame()
    dfcols = df.columns.tolist()
    for col in ['TaskNO','Mission','Expiry Date','Key Word','Topics']:
        PartDF[col] = df[dfcols[ColPosDict[col]]]
    result = PartDF.to_dict('records')
    return result





class VisDatatableDFBuilder:
    '''
    篩選源dataframe建購器，.run(SrcList)輸入為文本txt檔案清單。
    '''
    def __init__(self,                 
                 tpcTree,
                 BinMissionDict,
                 PreambleCols,
                 PreambleColsDefault,
                 sql3File, 
                 nProcess=1,
                 #SrcList = [],
                 SelectedFNPatList = [],
                 #從test_results_verification.sql抓取切片資訊的相關欄位
                 sqlCols=['PartNO','pred_Type','text'],
                 InfoScoreTable={},
                 InfoScoreSumLowerBound=-99999999,
                 InfoScoreSumUpperBound=99999999,
                 FixedTestFileBound=0,
                 nLeftFileChunk=0,
                 nScoringSegUPD=100,
                 VDDFSortParams={},
                 SimilarityMethod="difflib",
                 TwinsHighScoreNoUBD=math.inf,
                 TextSummarization = False,
                 CountArticleComposition = False,
                 nPiecesToSummaryUPD = 3,
                 BertDatasetSubDir = "dataset",
                 MPLOGGER = None
                 ):
        self.nProcess = nProcess
        self.tpcTree = tpcTree
        self.BinMissionDict = BinMissionDict
        self.PreambleCols = PreambleCols
        self.PreambleColsDefault = PreambleColsDefault
        self.sql3File = sql3File
        self.sqlCols = sqlCols
        #self.SrcList = SrcList
        self.SelectedFNPatList = SelectedFNPatList
        self.InfoScoreTable = InfoScoreTable
        self.InfoScoreSumLowerBound = InfoScoreSumLowerBound
        self.InfoScoreSumUpperBound = InfoScoreSumUpperBound
        self.nScoringSegUPD = nScoringSegUPD
        self.FixedTestFileBound = FixedTestFileBound
        self.nLeftFileChunk = nLeftFileChunk
        self.SessionPreambleColsOPTMain = self.GetOutputMain()
        self.VDDFSortParams = VDDFSortParams
        self.SimilarityMethod = SimilarityMethod
        self.TwinsHighScoreNoUBD = TwinsHighScoreNoUBD
        self.TextSummarization = TextSummarization
        self.CountArticleComposition = CountArticleComposition
        self.nPiecesToSummaryUPD = nPiecesToSummaryUPD
        self.BertDatasetSubDir = BertDatasetSubDir
        #self.show()
        if MPLOGGER == None:
            self.MPLOGGER = MPlogger()
        else:
            self.MPLOGGER = MPLOGGER

    def show(self):
        print("The params for VisDatatableDFTransformer:")
        pp = pprint.PrettyPrinter(indent=4)
        for x in self.rowslist[:3]:
            print("="*50)
            pp.pprint(x)
            print("="*50)
        print("InfoScoreSumLowerBound is {}".format(self.InfoScoreSumLowerBound))
        print("InfoScoreSumUpperBound is {}".format(self.InfoScoreSumUpperBound))
        print("FixedTestFileBound is {}".format(self.FixedTestFileBound))

    def GetOutputMain(self):
        return os.path.join(
            datasetDir,str(uuid.uuid1()),"PreambleCols_df")

        #return OUTPUTMAIN
    def run(self,SrcList):
        if self.FixedTestFileBound > 0:
            SrcList = RandomSample(SrcList,self.FixedTestFileBound)
        DTBJobs = [VisDatatableRowsListBuilder(
            tpcTree=self.tpcTree,
            BinMissionDict=self.BinMissionDict,
            PreambleCols=self.PreambleCols,
            PreambleColsDefault=self.PreambleColsDefault,
            sql3File=self.sql3File,
            SrcList = SrcListCK,
            SelectedFNPatList = self.SelectedFNPatList,
            sqlCols=self.sqlCols,
            InfoScoreTable=self.InfoScoreTable,
            nLeftFileChunk=self.nLeftFileChunk,
            nScoringSegUPD=self.nScoringSegUPD,
            TextSummarization = self.TextSummarization,
            CountArticleComposition = self.CountArticleComposition,
            nPiecesToSummaryUPD = self.nPiecesToSummaryUPD,
            BertDatasetSubDir = self.BertDatasetSubDir,
            ) for SrcListCK in SplitList(SrcList, nChunks=self.nProcess)]
        #print("run  MPS")
        MPresult = multicoreJob(
            DTBJobs, nProcess=self.nProcess).run()
        #print("MPresult",MPresult)
        
        rowslist, InfoScoreTableList = zip(*MPresult)
        rowslist = flattenList(rowslist)
        del MPresult
        print("rowslist[:3]",rowslist[:3])
        ISPos = self.PreambleCols.index("InfoScoreSum")
        
        #rowslist = sorted(rowslist, key = lambda x:x[ISPos], reverse=True)
        
        rowslist = sorted(rowslist, key = lambda x:x[ISPos])
        Scores = [x[ISPos] for x in rowslist]
        filePos = self.PreambleCols.index("File")
        FileList = [row[filePos] for row in rowslist]
        #1緒估1分鐘的量
        baseNum = int(8*40000/len(FileList))*5
        if "linux" in platform.system().lower():
            baseNum *= int(mp.cpu_count())
        LenHighScoreFileUPD = min(baseNum,len(FileList),self.TwinsHighScoreNoUBD)
        #print("LenHighScoreFileUPD",LenHighScoreFileUPD)
        #raise Exception
        if LenHighScoreFileUPD == 0:
            HighScoreFile = []
            LowScoreFile = FileList
            ScoreEdgePos = -1
        else:
            ScoreEdgePos = -LenHighScoreFileUPD
            #ScoreEdgePos = max(bisect_left(Scores,1000),int(len(Scores)*0.9))
            #ScoreEdgePos = min(max(0,len(Scores)-500),ScoreEdgePos)
            HighScoreFile = FileList[ScoreEdgePos:]
            LowScoreFile = FileList[:ScoreEdgePos]
        #在全部檔案綜整完畢為rowslist後，接續計算C(n,2)內部相似度，加以分群，存至Twins欄。
        print("ScoreEdgePos",ScoreEdgePos)
        print("Start to ComputeTwins.")
        print(f"There are {len(HighScoreFile)} HighScoreFiles \
              with ScoreEdge {Scores[ScoreEdgePos]}")
        print(f"and {len(LowScoreFile)} LowScoreFiles")
        ShowElapsedTime(start_time)
        #LenFL = len(FileList)
        LenHSF = len(HighScoreFile)
        #print()
        #raise Exception
        DTBJobs = [TwinsClassifier(
            HighScoreFile[i],
            HighScoreFile[:i]+LowScoreFile,
            sql3File=self.sql3File,
            sqlCols=self.sqlCols,
            segTagsUPD = 20,
            segTagsLBD = 5,
            #segTextUPD = 2,
            TextUPD = 512,
            PoolRandomOrder = True,
            SimilarityMethod = self.SimilarityMethod, #difflib,dmp,CountVectorCosine
            #在計算片段序列相似度前，是否先進行排序。
            TwinsAfterSort = TwinsAfterSort,
            #ReturnedFileUPD = 1,
            MPLOGGER = self.MPLOGGER
            ) for i in range(LenHSF)]
        random.shuffle(DTBJobs)
        MES = f"There are {len(DTBJobs)} TwinsClassifier Job."
        MPLOGGER.logW(MES, logFile="similarity_Match.log")
        SimilarityList = multicoreJob(
            DTBJobs, nProcess=int(self.nProcess)).run()
        SimilarityList = flattenList(SimilarityList)
        SimilarityList = [
            (file1,#.rstrip(".txt"),
             file2,#.rstrip(".txt"),
             round(maxs,2)) 
            for file1,file2,maxs in SimilarityList if file1 != '' and file2 != '']
        if len(SimilarityList) == 0:
            SimilarityList = [('','',0)]
        Similarity_df = pd.DataFrame(SimilarityList)
        columns=["TargetFile","MatchedFile","Similarity"]
        #定義欄位名
        Similarity_df.columns = columns
        CMP = ClusterMetaNodeGraph(BuildGraph(SimilarityList), "Louvain")    
        nDigit = len(str(max(CMP))) if len(CMP)>0 else 0
        NIC = {}
        temp = {}
        for ke in list(CMP):
            #CMP[f"Group {ke:{nDigit}d}"] = CMP.pop(ke)
            temp[f"Comm {(nDigit-len(str(ke)))*'0'}{ke}"] = CMP.pop(ke)
        CMP = temp
        for ke in CMP:
            for node in CMP[ke]:
                NIC[node] = ke
        #print("NIC",NIC)
        Similarity_df["Comm"] = Similarity_df["TargetFile"].apply(
            lambda x:NIC[x] if x in NIC else "")
        
        OPTFN = os.path.join(datasetDir,"Similarity","Similarity")
        dfOutputer(Similarity_df,OPTFN,
                   IndexCols = ["TargetFile","Comm","Similarity"]).run()

        twinsPos = self.PreambleCols.index("Twins")
        for row in rowslist:
            if row[filePos] in NIC:
                row[twinsPos] = NIC[row[filePos]]
        print("rowslist af [:7]",rowslist[:7])
        #raise Exception
        print("Finished ComputeTwins.")
        ShowElapsedTime(start_time)
        
        for IST in InfoScoreTableList:
            InfoScoreTable.update(IST)
    
        df = VisDatatableDFTransformer(
            rowslist = rowslist,
            PreambleCols = self.PreambleCols,
            InfoScoreTable=self.InfoScoreTable,
            InfoScoreSumLowerBound=self.InfoScoreSumLowerBound,
            InfoScoreSumUpperBound=self.InfoScoreSumUpperBound,
            FixedTestFileBound=self.FixedTestFileBound,
            VDDFSortParams=self.VDDFSortParams).run()

        return df


args = []
args.extend([Output('Colortable', 'selected_rows')])
args.extend([Input('MissionTable', 'derived_virtual_selected_rows')])
args.extend([State('MissionTable', 'data')])
args.extend([State('Colortable', 'data')])
@app.callback(*args,prevent_initial_call=True)
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
    #print("Colortable_data",Colortable_data)
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
    #print("Colortable_rows",Colortable_rows)
    ShowElapsedTime(start_time)
    print("Finished MissionTableSelection.")
    return Colortable_rows



                                     

#============================================================

args = []
args.extend([Output('intermediate-value-FilteredDF', 'data')])
args.extend([Output('nSamples', 'children')])
args.extend([Output('nSamples_bottom', 'children')])
args.extend([Output('current page', 'children')])
#args.extend([Output("CutRange", "max")])
#args.extend([Output("PiecesBound", "min")])
#args.extend([Output("PiecesBound", "max")])
#args.extend([Output("PiecesBound", "marks")])
#args.extend([Output("PiecesBound", "value")])
args.extend([Output("derived_filter_query_structure", 'data')])
#args.extend([Output("intermediate-value-selectedLabels", 'data')])
#args.extend([Output('selectedLabels', 'children')])
args.extend([Output("selectLabels Dict", "data")])
args.extend([Output("selectLabels Dict", "style_data_conditional")])
#args.extend([Output('InfoScoreRangeCard', "children")])

args.extend([Input('intermediate-value-df', 'data')])
#args.extend([Input('InfoScore Range', "value")])
args.extend([Input("AutoSelectSubTopics", "value")])
args.extend([Input("PiecesBound", "value")])
args.extend([Input('Colortable', 'derived_virtual_selected_rows')])
args.extend([Input('VisDatatable', "sort_by")])
args.extend([Input('VisDatatable', "derived_filter_query_structure")])
args.extend([Input('VisDatatable', "filter_query")])
args.extend([Input('KeyWordTable', "selected_rows")])

args.extend([State('KeyWordTable', "data")])

#args.extend([State('Colortable', 'data')])
#derived_virtual_data為當下經過filter後的值
#data為原始未經過filter的值
args.extend([State('Colortable', "derived_virtual_data")])
args.extend([State('Colortable', "data")])
args.extend([State('derived_filter_query_structure', 'data')])
args.extend([State('VisDatatable', "page_current")])
args.extend([State('current page', 'children')])
args.extend([State('DF_OPT', 'children')])
args.extend([State('FilteredDF_OPT', 'children')])
args.extend([State('TRsql3FileDataset Dir', 'children')])
@app.callback(*args,prevent_initial_call=True)
def FilteredDF_update(
        df_json,
        #ISRange,
        AutoSelectSubTopics,
        PiecesBound,
        derived_virtual_selected_rows,
        sort_by,
        derived_query_structure,
        filter_query,
        kw_dvs_rows,
        kw_data,
        
        #ColortableArray,
        Colortable_derived_virtual_data,
        ColortableArray,
        Old_derived_filter_query_structure_json,
        page_current,
        current_page,
        DF_OPTFN,
        FilteredDF_OPTFN,
        TRsql3FileDatasetDir
        #*args
        ):
    
    print("="*50)
    ShowElapsedTime(start_time)
    MES = f"使用者登錄IP及伺服器port為{request.remote_addr}, {args.TRVPort},"
    MES += f"DF_OPTFN為{DF_OPTFN}"
    MPLOGGER.logW(MES=MES,logFile="Test_result_Vis_LogIP.log")
    print("Running FilteredDF_update.")
    print("filter_query", filter_query)
    #print("derived_filter_query_structure", derived_query_structure)
    Old_derived_query_structure = json.loads(Old_derived_filter_query_structure_json)
    print("Old_derived_query_structure", Old_derived_query_structure)
    #derived_filter_query_structure = None
    print("receving derived_query_structure is ", derived_query_structure)    

    button_id_comp = get_button_id_comp(
        dash.callback_context, inspect.currentframe().f_code.co_name)
    if button_id_comp == "VisDatatable.page_current":
        print("Chinaging Page. Abort FilteredDF_update")
        raise PreventUpdate
        
    button_id = get_button_id(
        dash.callback_context, inspect.currentframe().f_code.co_name)

    '''
    if button_id == "VisDatatable":
        if all([filter_query == "",
                Old_derived_query_structure==derived_query_structure,
                sort_by == [],
                ]):
            print("filter_query is empty, derived_query_structure is not changed, sort_by=[]")
            print("this should be a false trigger, abort updating.")
            raise PreventUpdate
    '''

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
    #df =  pd.read_json(df_json, orient='split')
    DFPreambleColsFN = DF_OPTFN+".sql3"
    if os.path.isfile(DFPreambleColsFN):
        df = dfFromSQLite3(DFPreambleColsFN)
    else:
        df =  pd.read_json(df_json, orient='split')
    
    #print("df_json",df_json)
    #print("df['Date']",df['Date'])
    #計算選擇之類別清單selectedLabels
    selectedLabels = [
        Colortable_derived_virtual_data[x]['Label'] 
        for x in derived_virtual_selected_rows]
    #如果AutoSelectSubTopics == "Yes"，則自動擴展篩選子類列。
    if AutoSelectSubTopics == "Yes":
        selectedLabels = sorted(set(flattenList(
            [GetSubTopics([x], tpcTree) for x in selectedLabels]
            )))
    #僅考慮確實有出現該類文本的類別
    ColorDF = pd.DataFrame.from_records(ColortableArray)
    selectedLabels = sorted(ListCap(selectedLabels,list(ColorDF['Label'])))
    #print("kw_data",kw_data)
    if kw_dvs_rows is None:
        #for i in kw_dvs_rows:
            #keywords.extend(ast.literal_eval(kw_data[i]['Key Word']))
            #keywords.extend(''.join(kw_data[i]['Key Word']))
        keywords = []
    else:
        keywords = [kw_data[i]['Key Word'] for i in kw_dvs_rows]
    '''
    if button_id == "InfoScore Range":
        df = DFfilter(df,
                      InfoScoreSumLowerBound = ISRange[0],
                      InfoScoreSumUpperBound = ISRange[1])
    '''
    sql3File = os.path.join(TRsql3FileDatasetDir,"test_results_verification.sql3")
    FilteredDF = RowsFilter(
        df,
        selectedLabels = selectedLabels,
        sql3File = sql3File,
        keywords = keywords)
    print("sort_by",sort_by)
    #print("len(FilteredDF)",len(FilteredDF))
    if len(sort_by):
        FilteredDF = FilteredDF.sort_values(
            sort_by[0]['column_id'],
            ascending=sort_by[0]['direction'] == 'asc',
            inplace=False)

    #else:
        # No sort is applied
        #df = df
    
    (pd_query_string, FilteredDF) = construct_filter(
        derived_query_structure, FilteredDF)
    if pd_query_string != '':
        FilteredDF = FilteredDF.query(pd_query_string)
    ShowElapsedTime(start_time)
    FilteredPreambleColsFN = FilteredDF_OPTFN+".sql3"
    #如果磁碟可寫入，且先前已有成功將FilteredDF存檔的先例，則不存至FilteredDF_json。
    if os.path.isfile(FilteredPreambleColsFN):
        FilteredDF_json = '{}'
    else:
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
    
    dfOutputer(FilteredDF[PreambleCols],FilteredDF_OPTFN).run()
    #print("FilteredDF_json",FilteredDF_json)
    ShowElapsedTime(start_time)
    print("Finished Running FilteredDF_update.")
    return [FilteredDF_json]+[
        FilteredDF.shape[0]]*2+[
        page_current+1
        #GetnDigitElementsOfaList(list(FilteredDF.columns))
        #FilteredDF.shape[1]
        #]+[newPBMin,newPBMax,marks
        #]+[[newPBMin,newPBMax]
        ]+[derived_query_structure_json
        ]+[selectedLabelsDictArray]+[style_data_conditional]


#=======================================================

args = []
#args.extend([Output('intermediate-value-PartColDF', 'data')])
args.extend([Output('VisDatatable', "page_current")])
args.extend([Output('PredResSummaryCard', 'children')])
args.extend([Output('TwinsCard', 'children')])
#args.extend([Output('Chunk Params', 'data')])
#args.extend([Output('Start Bar', 'max')])
#args.extend([Output('Start Bar', 'marks')])
#args.extend([Output('nUniqueVal Bar', 'max')])
#args.extend([Output('nUniqueVal Bar', 'marks')])
#args.extend([Input("LastChunk", "value")])
#args.extend([Input("CutRange", "value")])
args.extend([Input('intermediate-value-FilteredDF', 'data')])
#args.extend([State('intermediate-value-ShowingFileScoreDF', 'data')])
#args.extend([Input('VisDatatable', "derived_filter_query_structure")])
args.extend([State('Colortable', "data")])
args.extend([State('VisDatatable', "page_current")])
args.extend([State('FilteredDF_OPT', 'children')])
args.extend([State('TRsql3FileDataset Dir', 'children')])
#args.extend([Input("Stride Bar", "value")])
@app.callback(*args,prevent_initial_call=True)
def ChunkDF_update(
        #LastChunk,
        #CutRange,
        FilteredDF_json,
        #derived_query_structure,
        #ShowingFileScoreDF_json,
        ColortableArray,
        page_current,
        FilteredDF_OPTFN,
        TRsql3FileDatasetDir):
    print("="*50)    
    ShowElapsedTime(start_time)
    print("Running ChunkDF_update.")
        
    sql3File = os.path.join(TRsql3FileDatasetDir,"test_results_verification.sql3")

    button_id = get_button_id(
        dash.callback_context, inspect.currentframe().f_code.co_name)    

    #df_json = df.to_json(date_format='iso', orient='split')
    FilteredPreambleColsFN = FilteredDF_OPTFN+".sql3"
    if os.path.isfile(FilteredPreambleColsFN):
        FilteredDF = dfFromSQLite3(FilteredPreambleColsFN)
    else:
        FilteredDF =  pd.read_json(FilteredDF_json, orient='split')

    #PartCol = PreambleCols+[str(i) for i in range(CutRange[0],CutRange[1])]
    #print("In CU, PartCol", PartCol)
    #PartColDF = FilteredDF[PartCol]
    '''
    if button_id in ["VisDatatable"]:
        (pd_query_string, PartColDF) = construct_filter(
            derived_query_structure, PartColDF)
        if pd_query_string != '':
            PartColDF = PartColDF.query(pd_query_string)
    '''
    #columns=["File"]+list(range(len(bar_df.columns)-1))
    #FilteredDF.columns = columns
    #PartColDF_json = PartColDF.to_json(date_format='iso', orient='split')
    #if button_id not in ['No clicks yet', 'CutRange']:
    #if button_id in ['intermediate-value-FilteredDF']:
        #page_current = 0
    
    ShowElapsedTime(start_time)
    print("Running Build_Pred_Block and Build_Twins_Block")
    ColorDict = DataArrayToDict(ColortableArray)
    PredSum_children = Build_Pred_Block(
        FilteredDF, sql3File, ColorDict)
    TwinsCard_children = Build_Twins_Block(FilteredDF)
    print("Finishing Running Build_Pred_Block and Build_Twins_Block")
    ShowElapsedTime(start_time)
    return [
        #PartColDF_json]+[
            page_current]+[PredSum_children]+[TwinsCard_children]



#============================================================

args = []
args.extend([Output('VisDatatableCard', 'children')])
args.extend([Output("CutRange", "max")])
args.extend([Output("CutRange", "marks")])
#args.extend([Output('PredResSummaryCard', 'children')])
#args.extend([Output('intermediate-value-ShowingFileScoreDF', 'data')])
args.extend([Output('ShowingFilePVTCard', 'children')])
args.extend([Output('PerformanceCardFiltered', "children")])
args.extend([Input('VisDatatable', "page_current")])
args.extend([Input("Page Size Bar", "value")])
args.extend([Input("CutRange", "value")])
#args.extend([Input('intermediate-value-PartColDF', 'data')])
#args.extend([Input('intermediate-value-ColorDict', 'data')])
#args.extend([Input('VisDatatable', "derived_filter_query_structure")])
#args.extend([State('VisDatatable', "page_current")])
args.extend([Input('Colortable', 'data')])
args.extend([Input('VisDatatable', 'data')])
#args.extend([State('Colortable', 'data')])
#args.extend([State('VisDatatable', "derived_filter_query_structure")])
#args.extend([State('derived_filter_query_structure', "data")])
args.extend([State('VisDatatable', "filter_query")])
args.extend([State('intermediate-value-FilteredDF', 'data')])
args.extend([State('FilteredDF_OPT', 'children')])
args.extend([State('TRsql3FileDataset Dir', 'children')])
@app.callback(*args,prevent_initial_call=True,
              suppress_callback_exceptions=True)
def table_update(
        page_current,
        page_size,
        CutRange,
        #PartColDF_json,
        #ColorDict_json,
        #page_current,
        #derived_virtual_selected_rows,
        #derived_query_structure,
        ColortableArray,
        VisDatatableArray,
        #derived_query_structure,
        #derived_query_structure_json,
        filter_query,
        FilteredDF_json,
        FilteredDF_OPTFN,
        TRsql3FileDatasetDir
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
    FilteredPreambleColsFN = FilteredDF_OPTFN+".sql3"
    if os.path.isfile(FilteredPreambleColsFN):
        FilteredDF = dfFromSQLite3(FilteredPreambleColsFN)
    else:
        FilteredDF =  pd.read_json(FilteredDF_json, orient='split')
    #PartColDF =  pd.read_json(PartColDF_json, orient='split')
    
    
    page_max = len(FilteredDF)//page_size+(len(FilteredDF)%page_size!=0) -1
    if page_current > page_max:
        print(f"page_current {page_current} > page_max {page_max}. Abort updating.")
        raise PreventUpdate
    '''
    if button_id in ["VisDatatable"]:
        (pd_query_string, PartColDF) = construct_filter(
            derived_query_structure, PartColDF)
        if pd_query_string != '':
            PartColDF = PartColDF.query(pd_query_string)
    '''
    ColorDict = DataArrayToDict(ColortableArray)
    #df = pd.DataFrame.from_records(VisDatatableArray)
    #print("Vis df['File']",df['File'])
    sql3File = os.path.join(TRsql3FileDatasetDir,"test_results_verification.sql3")
    VisData_children,ShowingFileScoreDF,CutRangeMax = Build_VisDatatable(
        #PartColDF, ColorDict, BinMissionDict,
        FilteredDF,
        sql3File,
        ColorDict, BinMissionDict,
        InfoScoreTable=InfoScoreTable,
        page_current=page_current, page_size=page_size,
        CutRange=CutRange,
        filter_query=filter_query,
        FilteredDF_OPTFN=FilteredDF_OPTFN)
    marks={i: str(i) for i in [
        0,
        int((0+CutRangeMax)/2),
        CutRangeMax]}
    #print("PartDF_File",PartDF_File)
    #raise Exception
    #PartDF_File = []
    #FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    #PredSum_children = Build_Pred_Block(
        #FilteredDF, ColorDict,SrcList=SrcList,PartDF_File=PartDF_File)#,PartDF_File = PartDF_File)
    #ShowElapsedTime(start_time)
    #return [VisData_children]+[PredSum_children]
    PartDFFL = ShowingFileScoreDF.sort_values(
        by=["InfoScoreSum"],ascending=False)["File"]
    #PredsDF = BuildPredsdf(df, PartDFFL)
    ShowingFilePVTCard_children = Build_ShowingFilePVT(sql3File, FileList=PartDFFL)
    PerformanceCardFiltered_children = Build_PerformancePVT(FilteredDF)
            
    return [VisData_children]+[CutRangeMax]+[marks
            ]+[ShowingFilePVTCard_children]+[
            PerformanceCardFiltered_children]
#============================================================   

@app.callback(
    Output("download-dataset", "data"),
    Input("btn_dataset", "n_clicks"),
    prevent_initial_call=True,
)
def func1(n_clicks):
    FPath = os.path.join(OfferingDir,"dataset.rar")
    return dcc.send_file(FPath)


@app.callback(
    Output("download-report", "data"),
    Input("btn_report", "n_clicks"),
    prevent_initial_call=True,
)
def func2(n_clicks):
    FPath = os.path.join(OfferingDir,"report.rar")
    return dcc.send_file(FPath)

@app.callback(
    Output('download-select-rows', 'data'),
    Input('save-table-button', 'n_clicks'),
    State('VisDatatable', 'derived_virtual_data'),
    State('VisDatatable', 'selected_rows'),
    prevent_initial_call=True,
)
#@app.callback(*args)
def save_current_table(
        savebutton, 
        #FilteredDF_json, 
        derived_virtual_data,
        selected_row_indices):
    
    df = pd.DataFrame.from_records(derived_virtual_data)
    dfcols = df.columns.tolist()
    r = re.compile("^\d+$")
    NumCols = list(filter(r.match, dfcols))
    cols = PreambleCols + [str(x) for x in sorted([int(x) for x in NumCols])]
    df = df[cols]
    if selected_row_indices:
        table_df = df.loc[selected_row_indices] #filter according to selected rows
    #selectedLabels = [
        #VisDatatable_derived_virtual_data[x]
        #for x in derived_virtual_selected_rows]
    if savebutton:
        OUTPUTMAIN="VisDataSavedRows"
        OUTPUTMAIN = os.path.join(OfferingDir,OUTPUTMAIN)
        dfOutputer(table_df,OUTPUTMAIN).run()
        #return [dcc.send_file(OUTPUTMAIN+".xlsx")]+[f"輸出及儲存{len(table_df)}列"]
        return dcc.send_file(OUTPUTMAIN+".xlsx")
    

args = []
args.extend([Output('intermediate-value-df', 'data')])
args.extend([Output('MessageBox', 'children')])
args.extend([Output('VisDatatable', "filter_query")])
args.extend([Output('intermediate-value-ColorDF', 'data')])
args.extend([Output('VisDatatable', "sort_by")])
args.extend([Output('ColortableCard', "children")])
args.extend([Output('InfoScoreRangeCard', "children")])
#args.extend([Output('Session Dataset Dir', 'children')])
#args.extend([Output('Colortable', 'data')])
#args.extend([Output('Colortable', 'style_data_conditional')])
args.extend([Output('TRsql3FileDataset Dir', 'children')])
args.extend([Output('DF_ALL_OPT', 'children')])
#args.extend([Input('InfoScore Range', "value")])
args.extend([Input('ReplaceDF', 'n_clicks')])
args.extend([Input('btn_InfoScore', 'n_clicks')])
args.extend([Input('Uploaded Filename', 'children')])
args.extend([Input('FinishedTask', 'value')])
args.extend([State('intermediate-value-FilteredDF', 'data')])
args.extend([State('DF_ALL_OPT', 'children')])
args.extend([State('FilteredDF_OPT', 'children')])
args.extend([State('DF_OPT', 'children')])
args.extend([State('DateSession ID', 'children')])
#args.extend([State('Session Dataset Dir', 'children')])
args.extend([State('TRsql3FileDataset Dir', 'children')])
args.extend([State('intermediate-value-ColorDF', 'data')])
args.extend([State('ColortableCard', 'children')])
args.extend([State('InfoScoreRangeCard', 'children')])
args.extend([State('InfoScore Range', "value")])
args.extend([State('Colortable', 'data')])
args.extend([State('Colortable', 'style_data_conditional')])
args.extend([State('intermediate-value-datasetDirDict', 'data')])


#args.extend([State('VisDatatable', "data")])
@app.callback(*args,prevent_initial_call=True)
def update_output(
        
        ReplaceDF_n_clicks,
        InfoScore_n_clicks,
        UploadedFilename,
        FinishedTaskSQLPath,
        FilteredDF_json,
        DF_ALL_OPTFN,
        FilteredDF_OPTFN,
        DF_OPTFN,
        date_session_id,
        #SessionDatasetDir,
        TRsql3FileDatasetDir,
        ColorDF_json,
        ColortableCard_children,
        InfoScoreRangeCard_children,
        ISRange,
        #VisDatatableArray
        ColortableArray,
        Colortable_style_data_conditional,
        datasetDirDict_json
        ):
    print("="*50)
    #print("*"*50)
    #print("*"*50)
    ShowElapsedTime(start_time)
    print("Running update_output.")
    #回傳值初始化，如有需要變更，再另外計算。
    #如果啓動原因是上傳自備文本(Uploaded Filename)，
    #則依自備文本計算新的Colortable、InfoScore　Range，並回傳。
    returned_df = FilteredDF_json
    returned_Colortable = ColortableCard_children
    returned_InfoScore_Range_Bar = InfoScoreRangeCard_children
    Message = ""
    
    button_id = get_button_id(
        dash.callback_context, inspect.currentframe().f_code.co_name)
    #取代篩選源
    if button_id == "ReplaceDF":
        #print("VisDatatableArray",VisDatatableArray)
        FilteredPreambleColsFN = FilteredDF_OPTFN+".sql3"
        DFPreambleColsFN = DF_OPTFN+".sql3"
        if os.path.isfile(FilteredPreambleColsFN) and FilteredDF_json == '{}':
            #FilteredDF = dfFromSQLite3(FilteredPreambleColsFN)
            #FilteredDF_json = FilteredDF.to_json(date_format='iso', orient='split')        
            shutil.copy(FilteredPreambleColsFN, DFPreambleColsFN)
        Message = f'已取代篩選源{ReplaceDF_n_clicks}次，如欲回復原始篩選源，請按F5 Refresh。使用者IP為{request.remote_addr}'
        print("IN upOut, FilteredDF_json",FilteredDF_json)

        
    #自傳文本推論
    elif button_id == "Uploaded Filename":
        #讀取模型資料集字典
        datasetDirDict = json.loads(datasetDirDict_json)
        #date_session_id = timeNow(FMT = "%Y-%m%d-%H%M-")+session_id
        #print("datasetDirDict bf",datasetDirDict)
        
        SessionDatasetDir = os.path.join(
            datasetDir_VisSelf, date_session_id)
        
        FTSessionDir = os.path.join("FixedTest_VisSelfService",
                                    date_session_id)
        print("FTSessionDir", FTSessionDir)
        print("filenames",UploadedFilename)
        try:
            FN = getFNFromFullPath(UploadedFilename)
        except:
            raise PreventUpdate            
        src = os.path.join(FTSessionDir, FN)
        desDir = os.path.join(FTSessionDir, "FT", "Using", "#T#[Scrap]")
        MKDIR(desDir)
        des = os.path.join(desDir, FN)
        
        #print(f"{Fore.LIGHTYELLOW_EX}src:{src},desDir:{desDir}{Fore.RESET}")
        colored_print(f"src:{src},desDir:{desDir}")
        #shutil.move(src,des)
        #executor = CommandExecutor(lambda: ExtractZip(des))
        executor = CommandExecutor(lambda: ExtractZip(src,output_dir=desDir))
        
        executor.run()  # 啟動執行緒
        executor.join()  # 等待執行緒完成
        
        SessionDatasetDir = os.path.join(
            datasetDir_VisSelf, date_session_id)
            #"BertScript",datasetDir_VisSelf, date_session_id)
        TRsql3FileDatasetDir = SessionDatasetDir
        DF_ALL_OPTFN = os.path.join(
            SessionDatasetDir,"DFPreambleCols_df_ALL")
        #UploadedFilename = os.path.join("BertScript",UploadedFilename)
        print("SessionDatasetDir", SessionDatasetDir)
        datasetDirDict[date_session_id[:14]] = SessionDatasetDir
        #print(f"Finished ExtractZIP {des}")
        #time.sleep(60)
                
        FTDir = os.path.join(FTSessionDir, "FT")
        #BertDataDir = os.path.join("BertScript",SessionDatasetDir,"dataset")
        BertDataDir = os.path.join(SessionDatasetDir)
        TCFMainCMD = f"python TCFMain.py -p {args.TRVPort} -ts y\
            -RunTRV False -TRVHost False -FTPath {FTDir} \
            -WPRoot WorkPool_VisSelfService -mdlType {modelType}"
            #-BertDataDir {BertDataDir} -mdlType {modelType}"
        executor = CommandExecutor(TCFMainCMD)
        executor.run()  # 啟動執行緒
        executor.join()  # 等待執行緒完成
        #os.system(
            #f"python TCFMain.py -ts y\
                  #-RunTRV False -TRVHost False -FTPath {FTDir} \
                  #-BertDataDir {BertDataDir} -mdlType {modelType}")
        colored_print("Finished TCFMain.py for uploaded file.")
        #countdown_pause(60)
        #src = os.path.join(BertDataDir,"test_results_verification.sql3")
        #des = os.path.join("BertScript",SessionDatasetDir,"test_results_verification.sql3")
        #shutil.copyfile(src,des)
        Message = "已完成自傳任務推論。請於下方「已完成自定任務條目」選擇上載時間條目載入。"
        
    elif button_id == "FinishedTask":
        #os.chdir("BertScript")
        #date_dir_dict = get_finished_date_dir_dict(port=ACPort)
        #print("date_dir_dict",date_dir_dict)
        #countdown_pause(60)
        TRsql3FileDatasetDir = os.path.join(datasetDir_VisSelf,FinishedTaskSQLPath)
        sql3File = os.path.join(TRsql3FileDatasetDir,"test_results_verification.sql3")
        #sql3File = os.path.join(datasetDir_VisSelf,FinishedTaskSQLPath,"test_results_verification.sql3")
        #print("sql3File",sql3File)
        #print("os.path.isfile(sql3File)",os.path.isfile(sql3File))
        #countdown_pause(60)
        SrcList = GetSrcList(sql3File)
        ShowElapsedTime(start_time)
        colored_print("Running VDT_DFBuilder.")
        #print("sql3File",sql3File)
        #countdown_pause(60)
        DF_ALL_PreambleColsFN = DF_ALL_OPTFN+".sql3"
        #if os.path.isfile(DF_ALL_PreambleColsFN):
            #print("Found DFPreambleCols_df_ALL Files, loading.")
            #df = dfFromSQLite3(DF_ALL_PreambleColsFN)
        #else:
            #print("Didn't find DFPreambleCols_df_ALL Files, computing and saving.")
        VDT_DFBuilder = VisDatatableDFBuilder(
            nProcess=nProcess,
            tpcTree=tpcTree,
            BinMissionDict=BinMissionDict,
            PreambleCols=PreambleCols,
            PreambleColsDefault=PreambleColsDefault,
            sql3File=sql3File, 
            #SrcList = SrcList,
            SelectedFNPatList = SelectedFNPatList,
            #從test_results_verification.sql抓取切片資訊的相關欄位
            sqlCols=sqlCols,
            InfoScoreTable=InfoScoreTable,
            #InfoScoreSumLowerBound=InfoScoreSumLowerBound,
            #InfoScoreSumUpperBound=InfoScoreSumUpperBound,
            nScoringSegUPD=nScoringSegUPD,
            FixedTestFileBound=FixedTestFileBound,
            nLeftFileChunk=nLeftFileChunk,
            SimilarityMethod=SimilarityMethod,
            TwinsHighScoreNoUBD=TwinsHighScoreNoUBD,
            TextSummarization=TextSummarization,
            CountArticleComposition=CountArticleComposition,
            nPiecesToSummaryUPD=nPiecesToSummaryUPD,
            BertDatasetSubDir=BertDatasetSubDir,
            MPLOGGER=MPLOGGER
            )
        
        df = VDT_DFBuilder.run(SrcList)
        df['Date'] = df['Date'].apply(lambda x:"🌎"+x if len(x)>0 and not x.startswith("🌎") else x)
        #dfOutputer(df[PreambleCols],DF_ALL_OPTFN).run()
        #print("Finished computing and saving DFPreambleCols_df_ALL for uploaded files.")

        returned_InfoScore_Range_Bar = Build_InfoScore_Range_Bar(df)
        Message = "已載入指定任務資料。"
    #elif button_id == "InfoScore Range":
        #InfoScoreSumLowerBound = ISRange[0]
        #InfoScoreSumUpperBound = ISRange[1]
        
    #if button_id in ["InfoScore Range"]:
    if button_id in ["btn_InfoScore"]:
        sql3File = os.path.join(TRsql3FileDatasetDir,"test_results_verification.sql3")
        DF_ALL_PreambleColsFN = DF_ALL_OPTFN+".sql3"
        if os.path.isfile(DF_ALL_PreambleColsFN):
            print("Found DFPreambleCols_df_ALL Files, loading.")
            df = dfFromSQLite3(DF_ALL_PreambleColsFN,
                clause = f" WHERE InfoScoreSum BETWEEN {ISRange[0]} AND {ISRange[1]}")
            df = df.sort_values(VDDFSortParams)
        else:
            print("WARNING!! Didn't find DFPreambleCols_df_ALL Files")
            df = pd.DataFrame()
    #if button_id in ["Uploaded Filename"]:
    #sql3File = os.path.join(TRsql3FileDatasetDir,"test_results_verification.sql3")
    #elif button_id in ["InfoScore Range"]:
    #if button_id in ["InfoScore Range","Uploaded Filename"]:
    #if button_id in ["btn_InfoScore","Uploaded Filename","FinishedTask"]:
    if button_id in ["btn_InfoScore","FinishedTask"]:
        cms = cmapSet()
        ColorDict = {}
        LabelList = []
        if ListOnlyOccuringLabels == True:
            cols=['pred_Type']
            FileListPat =','.join([
                f'"{x}"' for x in list(df["File"])])
            query = f'SELECT DISTINCT pred_Type FROM sampleSrc \
                WHERE File IN ({FileListPat});'
            FileLabelList = sqlite3Query(
                sql3File, query = query,ListForm = True)
            LabelList.extend(FileLabelList)

        LabelList = sorted(set(LabelList))
        LabelList.extend(ExemptLabelList)
        
        ColorDict["可於此格手動輸入特定分類名"] = '#FFFFFF'
        ColorDict["Scrap"] = '#E3E4E1'
        colorIndex = 0
        for label in LabelList:
            if label == "Scrap":
                continue
            else:
                #ColorDict[label] = cms.pop()
                #ColorDict[label] = cms[colorIndex]
                ColorDict[label] = RandomColor(seed = label)
                colorIndex += 1
                colorIndex = colorIndex % len(cms)
           
        #ColorDF = ColorDictToColorDF(ColorDict)
        ColorDF,ColorDF_json,Colortable_style_data_conditional = BuildColorDF(
            ColorDict,ClassTable)
        #ColorDF_json = ColorDF.to_json(date_format='iso', orient='split')
        returned_Colortable = Build_ColorTable(ColorDF)
        


        #dfOutputer(df[PreambleCols],DF_OPTFN).run()
        
        try:
            open("ThisIsAFileToTestWritablity.txt",'wt').close()
            df_json = '{}'
            #FilteredDF_json = dict()
        except:
            df_json = df.to_json(date_format='iso', orient='split')
            #FilteredDF_json = df_json
            
        returned_df = df_json

    ShowElapsedTime(start_time)
    #print("returned_df",returned_df)
    print("Finished Running update_output.")
    return [returned_df]+[Message]+[""]+[ColorDF_json]+[[
        {'column_id': 'InfoScoreSum', 'direction': 'desc'}]]+[
            returned_Colortable]+[
            returned_InfoScore_Range_Bar]+[
        #ColortableArray]+[
        #Colortable_style_data_conditional]+[
            TRsql3FileDatasetDir]+[DF_ALL_OPTFN]
    
#=========客戶端自傳推論相關callback==================================
datasetDir_VisSelf = os.path.join("WorkPool_VisSelfService")
UPLOAD_FOLDER_ROOT = "FixedTest_VisSelfService"
du.configure_upload(app, UPLOAD_FOLDER_ROOT)
@du.callback(
    output=Output('Uploaded Filename', 'children'),
    id='dash-uploader'
    )
def Message_Uploader(filenames):
    return filenames[0]



@app.callback(
    Output("download-dataset-samples", "data"),
    Input("btn_dataset_samples", "n_clicks"),
    prevent_initial_call=True,
)
def func(n_clicks):
    FPath = os.path.join(datasetDir,"samples.zip")
    return dcc.send_file(FPath)

#%%============================================================

@app.callback(
    Output("ParentTopicBar", "options"),
    Output("ParentTopicBar", "value"),
    Output("ChildTopicBar", "options"),
    Output("ChildTopicBar", "value"),
    Output("QueryRoot", "value"),
    Input("CurrentTopicBar", "value"),
    prevent_initial_call=True,
)
def setParChildTopicBarOption(CurrentTopic):#,ParentTopic):
    print("Run setTopicBarOption.")
    ParTopics = ParTopicsDict.get(CurrentTopic,dict()).get(1,[])
    ParentTopicOptions=[{'label': tpc, 'value': tpc} 
             for tpc in ParTopics]
    ParentTopicValue = ParentTopicOptions[0]["value"] if len(ParentTopicOptions) > 0 else None
    ChildTopicOptions=[{'label': tpc, 'value': tpc} 
             for tpc in SubTopicsDict.get(CurrentTopic,dict()).get(1,[])]
    ChildTopicValue = ChildTopicOptions[0]["value"] if len(ChildTopicOptions) > 0 else None
    print("CurrentTopic",CurrentTopic)
    print("ParTopics",ParTopics)
    return [ParentTopicOptions,ParentTopicValue,
            ChildTopicOptions,ChildTopicValue,
            CurrentTopic]

@app.callback(
    Output("SiblingTopicBar", "options"),
    Output("SiblingTopicBar", "value"),
    Input("ParentTopicBar", "value"),
    State("CurrentTopicBar", "value"),
    prevent_initial_call=True,
)
def setSiblingTopicBarOption(ParentTopic,CurrentTopic):
    print("Run setTopicBarOption.")
    print("ParentTopic",ParentTopic)
    print("CurrentTopic",CurrentTopic)
    SiblingTopics = SubTopicsDict.get(ParentTopic,dict()).get(1,[])
    SiblingTopics.remove(CurrentTopic)
    print("SiblingTopics",SiblingTopics)
    SiblingTopicOptions=[{'label': tpc, 'value': tpc} 
             for tpc in SiblingTopics]
    SiblingTopicValue = SiblingTopicOptions[0]["value"] if len(SiblingTopicOptions) > 0 else None
    return [SiblingTopicOptions,SiblingTopicValue,
            ]

'''
@app.callback(
    Output("CurrentTopicBar", "value"),
    
    
    prevent_initial_call=True,
)
def PickTopicInParentTopicBar(n_clicks,ParentTopic):
    print("PickTopicInParentTopicBar")
    if ParentTopic is None:
        raise dash.exceptions.PreventUpdate
    return ParentTopic
'''

@app.callback(
    Output("CurrentTopicBar", "value"),
    Input("btn_PickParentTopic", "n_clicks"),
    Input("btn_PickChildTopic", "n_clicks"),
    Input("btn_PickSiblingTopic", "n_clicks"),
    Input("btn_SetCurrentTopic", "n_clicks"),
    State("ParentTopicBar", "value"),
    State("ChildTopicBar", "value"),
    State("SiblingTopicBar", "value"),
    State("QueryRoot", "value"),
    prevent_initial_call=True,
)
def PickTopicInParentOrChildTopicBar(
        n_clicks1,n_clicks2,n_clicks3,n_clicks4,
        ParentTopic,ChildTopic,SiblingTopic,QueryRoot):
    print("Run PickTopicInParentOrChildTopicBar")
    button_id = get_button_id(
        dash.callback_context, inspect.currentframe().f_code.co_name)
    if button_id in ["btn_PickParentTopic"]:
        if ParentTopic is None:
            raise dash.exceptions.PreventUpdate
        return ParentTopic
    elif button_id in ["btn_PickChildTopic"]:
        if ChildTopic is None:
            raise dash.exceptions.PreventUpdate
        return ChildTopic
    elif button_id in ["btn_PickSiblingTopic"]:
        if SiblingTopic is None:
            raise dash.exceptions.PreventUpdate
        return SiblingTopic
    elif button_id in ["btn_SetCurrentTopic"]:
        if QueryRoot not in InfoScoreTable.keys():
            textList1=[QueryRoot]
            textList2=list(InfoScoreTable.keys())
            SimDict = InnerCrossSimilarityForTextList(
                textList1=textList1,textList2=textList2,saveResult=False)
            Cands = sorted([(k,v) for k,v in SimDict[QueryRoot].items()],
                           key = lambda x:x[1],reverse=True)
            QueryRoot = Cands[0][0]
        return QueryRoot

@app.callback(
    Output("LabelSelectorCard", "children"),
    Input("btn_DrawWithCurrentTopic", "n_clicks"),
    State("CurrentTopicBar", "value"),
    prevent_initial_call=True,
)
def updateLabelSelector(n_clicks,CurrentTopic):
    return Build_LabelSelector(app,Roots=[CurrentTopic])

@app.callback(
    Output("JaalViewerCard", "children"),
    Output("JaalViewerCardDetails", "open"),
    Input("btn_JaalViewer", "n_clicks"),
    prevent_initial_call=True,
)
def buildJaalIframe(n_clicks):
    return Build_JaalViewCard(),True

#%%============================================================
def serve_layout():
#def serve_layout(datasetDir):
    session_id = str(uuid.uuid4())
    date_session_id = timeNow(FMT = "%Y-%m%d-%H%M-")+session_id
    SessionDatasetDir = os.path.join(
        datasetDir, date_session_id)
    MKDIR(SessionDatasetDir)
    #session_id = hash(str(random.randint(1,10000)))
    if args.VisSelfService == True:
        TRsql3FileDatasetDir = SessionDatasetDir
        src = os.path.join(datasetDir,"test_results_verification.sql3")
        des = os.path.join(TRsql3FileDatasetDir,"test_results_verification.sql3")
        shutil.copyfile(src,des)
        
    else:
        TRsql3FileDatasetDir = datasetDir
        
    FilteredDF_OPTFN = os.path.join(SessionDatasetDir,"FilteredPreambleCols_df")
    DF_OPTFN = os.path.join(SessionDatasetDir,"DFPreambleCols_df")
    dfOutputer(df[PreambleCols],DF_OPTFN).run()
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
                                            MPLOGGER = MPLOGGER,
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
                                            style_cell_conditional=MT_style_cell_conditional,
                                            MPLOGGER = MPLOGGER,
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
                                        Build_ColorTable(ColorDF)
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
        
        html.Details([
            html.Summary('Classes Tree Viewer'),
            rc.Row([
                rc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(html.H2("Parent Topic")),
                            dcc.Dropdown(
                                id='ParentTopicBar',
                            ),
                            html.Button("挑選", id="btn_PickParentTopic"),
                        ],
                        color="secondary",
                        ),width = 3),
                rc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(html.H2("Current Topic")),
                            dcc.Dropdown(
                                id='CurrentTopicBar',
                                options=[{'label': tpc, 'value': tpc} 
                                         for tpc in InfoScoreTable.keys()],
                            ),
                            html.Button("展開繪製", id="btn_DrawWithCurrentTopic"),
                        ],
                        color="primary",
                        ),width = 3),
                rc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(html.H2("Child Topic")),
                            dcc.Dropdown(
                                id='ChildTopicBar',
                            ),
                            html.Button("挑選", id="btn_PickChildTopic"),
                        ],
                        color="success",
                        ),width = 3),
            ]),
            html.Hr(),
            rc.Row([
                rc.Col("Current Topic:中心類別，Parent Topic:母類別，Child Topic：子類別，Sibling Topic：兄弟類別（與中心類別同為所選母類別的子類別的類別），框選複製及輸鍵設定區可用於複製類別名稱文字或輸入部份文字，自動蒐索名稱最相似的類別。下拉式選單皆支援關鍵字篩選。"
                       ,width = 3),
                rc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(html.H2("Sibling Topic")),
                            dcc.Dropdown(
                                id='SiblingTopicBar',
                            ),
                            html.Button("挑選", id="btn_PickSiblingTopic"),
                        ],
                        color="warning",
                        ),width = 3),
                rc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(html.H2("框選複製及輸鍵設定區")),
                            dcc.Input(
                                id='QueryRoot',
                                type='text',
                                ),
                            html.Button("設定", id="btn_SetCurrentTopic"),
                        ],
                        color="light",
                        ),width = 3),
            ]),
            html.Hr(),
            dbc.Card(
                [
                    dbc.CardHeader(html.H2("Label Selector with Respect to Tree Structure")),
    
                    dbc.CardBody(
                        id="LabelSelectorCard",
                        children = [
                            #Build_LabelSelector(tpcTree)
                            #Build_LabelSelector(app,df_tree)
                            Build_LabelSelector(app)
                        ]
                        ),
                ],
                color="light",
                #style={"width": "35rem"},
            )
        ], open = True),
        rc.Row([
            rc.Col(
                html.Details([
                    html.Summary('Classes Tree Jaal Viewer'),
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H2("Classes Tree Jaal Viewer")),
                                dbc.CardBody(
                                    children = [
                                        html.Div([
                                            html.Button("繪製分類樹互動Jaal窗格", id="btn_JaalViewer"),
                                            ],className = 'col-6'),
                                    ]
                                    ),
                            ],
                            color="light",
                            #style={"width": "35rem"},
                        )
                ], open = True),
                width=9
            ),
        ]),
        html.Details([
            rc.Row([                
                html.Div([
                    dbc.Card(
                        [
                            dbc.CardHeader(html.H2("分類樹互動Jaal窗格")),
                            dbc.CardBody(
                                id="JaalViewerCard",
                                ),
                        ],
                        #color="warning",
                        ),
                    rc.Row([
                        html.H2('pandas Query語法：id.str.contains("TW Affairs")\n'),
                        html.H2('ancestors.str.contains("#T#TW Affairs#T#")\n'),
                        html.H2('Color Nodes by Positivity, Size Nodes by InfoScore_Level, Size Edges by endpoint_LGPdepth_weight\n'),
                        html.H2('filter on nodes: LGPdepth>12&ancestors.str.contains("#T#CN")\n'),
                        html.H2('filter on edges: endpoint_LGPdepth_weight<5\n'),
                        
                        ]),
                    ],className = 'col-12'),
            ]),
        ],open = False,id='JaalViewerCardDetails'),
        
        rc.Row([
            rc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(html.H2("Predicting Result Summary")),
                        dbc.CardBody(
                            id="PredResSummaryCard",
                            children = Build_Pred_Block(FilteredDF, sql3File, ColorDict),#, SrcList=SrcList),
                        ),
                    ],
                    color="success",
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
                            ),
                    ],
                    color="primary",
                    ),
                width = 9)
        ]),
        rc.Row([
            rc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(html.H2("Performance PivotTable for All Data")),
                        dbc.CardBody(
                            id="PerformanceCardAll",
                            children=Build_PerformancePVT(df),
                            ),
                    ],
                    color="secondary",
                    ),
                width = 9)
        ]),
        rc.Row([
            rc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(html.H2("Performance PivotTable for Filtered Data")),
                        dbc.CardBody(
                            #使用未經Filter的df初始化
                            id="PerformanceCardFiltered",
                            children=Build_PerformancePVT(df),
                            ),
                    ],
                    color="light",
                    ),
                width = 9)
        ]),
        
        rc.Row([
            rc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(html.H2("Twins Group Summary")),
                        dbc.CardBody(
                            id="TwinsCard",
                            #children = Build_Twins_Block(FilteredDF),
                            ),
                    ],
                    color="info",
                    ),
                width = 9)
        ]),

        rc.Row([
            html.Div([
                rc.Card(rc.CardContent(rc.Row([rc.Col(c, width=3) for c in controls1]))),
                ],className = 'col-11'),
            html.Div([
                html.Button("依分數更新篩選源", id="btn_InfoScore"),
                ],className = 'col-1'),
            ]
        ),
        html.Div([
            html.Div([
                dbc.Card(
                    [
                    dbc.CardBody(
                        id="InfoScoreRangeCard",
                        children = Initial_InfoScore_Range_Bar,
                        ),
                    #html.Hr(),
                    #html.Div(id='datatable-query-structure', style={'whitespace': 'pre'})
                    ],
                    style={"width": "11"},
                    )],
                className = 'col-12'),
        ],
        className = 'row'
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
                rc.Col(rc.Row([html.H2(id='MessageBox', children=f'{SystemMessage}', style={'color': 'blue'}),
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
                    rc.Col(
                        rc.Row([
                            html.H2(
                            f'僅會挑選前{args.nScoringSegUPD}片計分。\n'
                                        ),
                            html.H2(
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
                    rc.Col(
                        rc.Row([
                            html.H2("DateSession ID:",hidden=hide_dir_setting),
                            html.H2(id = "DateSession ID",children=f'{date_session_id}',hidden=hide_dir_setting),
                            html.H2("Session資料集工作路徑:",hidden=hide_dir_setting),
                            html.H2(id = "Session Dataset Dir",children=f'{SessionDatasetDir}',hidden=hide_dir_setting),
                            html.H2("切片結果資料庫路徑:",hidden=hide_dir_setting),
                            html.H2(id = "TRsql3FileDataset Dir",children=f'{TRsql3FileDatasetDir}',hidden=hide_dir_setting),
                            html.H2("完整資料庫路徑:",hidden=hide_dir_setting),
                            html.H2(id = "DF_ALL_OPT",children=f'{DF_ALL_OPTFN}',hidden=hide_dir_setting),
                            html.H2("篩選源資料庫路徑:",hidden=hide_dir_setting),
                            html.H2(id = "DF_OPT",children=f'{DF_OPTFN}',hidden=hide_dir_setting),
                            html.H2("篩選後資料庫路徑:",hidden=hide_dir_setting),
                            html.H2(id = "FilteredDF_OPT",children=f'{FilteredDF_OPTFN}',hidden=hide_dir_setting)
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
                    '{}：片段類別樣態符合設定條件'.format(
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
                               ]),width=12),
                rc.Col(rc.Row([html.H2(children=f'模型資料集字典\n：{datasetDirDict}')
                               ]),width=12),
                rc.Col(rc.Row([html.H2(children=f'使用模型：{outputDir}\n')
                               ]),width=12),
                rc.Col(rc.Row([html.H2(children=f'高相似度切片豁免使用方法：{SimilarPiecesExemptMethod}')
                               ]),width=12),
                
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
        Build_Upload_Block(date_session_id,UploadedFilename,VisSelfFinishedState),
        Build_Finished_Task_Block(port=args.TRVPort,datasetDir_VisSelf=datasetDir_VisSelf),
        dcc.Store(id='intermediate-value-df',  data = df_json),
        dcc.Store(id='intermediate-value-FilteredDF',  data = FilteredDF_json),
        #dcc.Store(id='intermediate-value-ColorDict',  data = ColorDict_json),
        dcc.Store(id='intermediate-value-ColorDF',  data = ColorDF_json),
        #dcc.Store(id='intermediate-value-ColorDF',  data = {}),
        #derived_filter_query_structure用來依據filter data設定值更新FilteredDF
        dcc.Store(id='derived_filter_query_structure', data = json.dumps(None, indent = 4)),
        #dcc.Store(id='intermediate-value-selectedLabels',  data = selectedLabels_json),
        #dcc.Store(id='intermediate-value-ShowingFileScoreDF',  data = ShowingFileScoreDF_json), #目前顯示中的檔案及其分數
        #dcc.Store(id='intermediate-value-FilteredDF_OPTFN',  data = FilteredDF_OPTFN_json),
        #dcc.Store(id='intermediate-value-df_tree',  data = df_tree_json),
        dcc.Store(id='intermediate-value-datasetDirDict', data = json.dumps(datasetDirDict, indent = 4)),
    ])



if __name__=='__main__':
    setproctitle.setproctitle(f'CZJTestResultVis')
    #print("=*50")
    #print(os.getcwd().split(os.path.sep)[-1])
    if os.getcwd().split(os.path.sep)[-1] in [
            "DatasetConverter","BertScript"]:
        os.chdir("../")
        print(f"Change working directory to {os.getcwd()}")
    args = ClassfierOptionParser()
    BertDatasetSubDir,outputDir = datasetDirOutputDirPickers(
        args=args,rdy_for_stage="TestResultVis").proc()

    #raise Exception
    #ClassTable
    
    if BertDatasetSubDir == None:
        MES = "-"*50+"\n"
        MES += f"In {args.WorkPoolROOT}, There is no BertDatasetSubDir ready for TestResultVis! ABORT!"
        MPlogger().logW(MES)
        raise Exception
    NewBertDatasetSubDir = BertDatasetSubDir.replace(
        "_rdy_for_TestResultVis","_is_running_TestResultVis")
    #NewBertDatasetSubDir += BertDatasetSubDir + "_is_running_DataConverter"
    os.rename(BertDatasetSubDir,NewBertDatasetSubDir)    
    MES = "-"*50+"\n"
    MES += f"TestResultVis started. WorkDir is {NewBertDatasetSubDir}."
    BertDatasetSubDir = NewBertDatasetSubDir
    MPLOGGER = MPlogger(logSubDir=f"{BertDatasetSubDir}/logs")
    MPLOGGER.logW(MES)
    
    datasetDir = BertDatasetSubDir
    datasetDirDict = {
        "default":BertDatasetSubDir
        }
    
    for logfile in ["similarity.log","similarity_Match.log",
                    "tokens result.txt",
                    "similarity_Match_TextSim.log",
                    "similarity_Match_TextSim_Passed.log",
                    "similarity_Match_TextSim_Failed.log",
                    "SimilarityEdge.txt",
                    "Exempt.log"]:
        #open(logfile,'wt').close()
        #print("refreshing",logfile)
        try:
            logfile = os.path.join("logs",logfile)
            open(logfile,'wt').close()
        except Exception as e:
            MES = f"When refresh logfile {logfile} in Test_result_Vis.py, the following error occurs:\n{e}\n"
            MPLOGGER.logW(MES,logFile="Exception.log")
    #print("b4 args",args)
    args = ClassfierOptionParser()
    #print("args",args)
    InfoScoreSumLowerBound = args.InfoScoreSumLowerBound
    InfoScoreSumUpperBound = args.InfoScoreSumUpperBound
    TextSummarization = args.TextSummarization
    CountArticleComposition = args.CountArticleComposition
    nScoringSegUPD = args.nScoringSegUPD
    SimilarityMethod = args.SimilarityMethod
    #在計算片段序列相似度前，是否先進行排序。
    TwinsAfterSort = args.TwinsAfterSort
    #計算片段序列相似度時，列為計算每篇相似度核心重要文本數量上限
    TwinsHighScoreNoUBD = args.TwinsHighScoreNoUBD
    FixedTestFileBound = args.FixedTestFileBound
    modelType = args.ModelType
    hide_dir_setting = 'hidden'
    loadPreComputed_DF_ALL = False #使用先前舊的DFPreambleCols_df_ALL.sql3，不重新計算。
    if "linux" in platform.system().lower():
        loadPreComputed_DF_ALL = False    
    start_time = time.time()
    
    nProcess = mp.cpu_count()-1
    nProcess = int(mp.cpu_count()/3)
    nProcess = multicoreJob().ComputeNProcess()
    #nProcess = 1
    ListOnlyOccuringLabels = True
    PreambleCols = ["Rating",
                    "InfoScoreSum", 
                    "InfoScoreMean",
                    "InfoScoreStd",
                    "NumberOfMatchingBlock",
                    "NumberOfMatchingBlockWithKW",
                    "Compositions",
                    "Class Of Most Pieces",
                    "Text Of Class Of Most Pieces",
                    "Class Of Highest Score",
                    "Text Of Class Of Highest Score",
                    "NumberOfExemptPieces",
                    "Date",
                    "Selected",
                    "Target",
                    "Twins",
                    "File",
                    "Summary",
                    #"CPC Meeting",
                    ]
    PreambleColsDefault = {
                    "Rating":"",
                    "InfoScoreSum":0, 
                    "InfoScoreMean":0,
                    "InfoScoreStd":0,
                    "NumberOfMatchingBlock":"",
                    "NumberOfMatchingBlockWithKW":"",
                    "Compositions":dict(),
                    "Class Of Most Pieces":"",
                    "Text Of Class Of Most Pieces":"",
                    "Class Of Highest Score":"",
                    "Text Of Class Of Highest Score":"",
                    "NumberOfExemptPieces":"",
                    "Date":"",
                    "Selected":"",
                    "Target":"",
                    "Twins":"",
                    "File":"",
                    "Summary":"",
                    #"CPC Meeting":""
                    }
    BMKeys = BinMissionDict.keys()
    VDDFSortParams = {
        "by":['Twins','Rating','InfoScoreSum'],
        "ascending":[True,False,False]
    }
    #print("VDDFSortParams",VDDFSortParams)

    r = re.compile("dataset_\d+$")
    #datasetDirs = list(filter(r.match, os.listdir()))
    #datasetDirs = sorted(datasetDirs, reverse=True)
    #datasetDir = datasetDirs[0]
    #datasetDir, outputDir = datasetDirOutputDirPickers(args=args).proc()
    if args.modelDir != "":
        outputDir = args.modelDir
    #如果args.VisSelfService值為True，啓用客戶端上傳及推論服務，
    #設定datasetDir為特定目錄。
    if args.VisSelfService == True:
        datasetDir = datasetDir_VisSelf
    if args.VisDatasetDir != "":
        datasetDir = args.VisDatasetDir
    #下載專區檔案置放處
    #print("datasetDir in TRV",datasetDir)
    #資料集 FPath = os.path.join(OfferingDir,"dataset.rar")
    #報告 FPath = os.path.join(OfferingDir,"report.rar")
    OfferingDir = os.path.join(datasetDir,"OfferingFiles")
    MKDIR(OfferingDir)
    #print("datasetDir",datasetDir)
    #raise Exception
    
    sql3File = os.path.join(datasetDir,"test_results_verification.sql3")
    
    #sql3File = "test_results_verification_Large.sql3"
    nFigs = 4
    page_current = 0
    #current_page用於顯示於頁面上，並用於偵測換頁，以控制FilteredDF_update在換頁時不執行。
    current_page = page_current
    PAGE_SIZE = 50
    #PAGE_SIZE = 3
    SystemMessage = ""
    VisSelfFinishedState = False
    #UploadFinishedState = False
    UploadedFilename = ""
    AutoSelectSubTopics = "No"
    
    '''
    DBTreeFile = "C:/Users/*/Documents/TACA/DB/ZMRAND/Imported/TopicTree.csv"
    if os.path.isfile(DBTreeFile) == True:
        TreeFile = DBTreeFile
    else:
        TreeFile = "../TACA/DB/ZMRAND/Imported/TopicTree.csv"
    '''
    #設定是否轉換標籤，只留大小寫字母及數字
    OnlyLettersDigitsLabels = False
    
    #TreeFile = GetTreeFilePath()
    #tpcTree = LoadTree(
        #TreeFile,OnlyLettersDigitsLabels= OnlyLettersDigitsLabels)
    
    #InfoScoreTable = BuildInfoScoreTable(
        #TreeFile,OnlyLettersDigitsLabels,OutputPath = datasetDir)

    TreeBaseFNList = ["TopicTree.csv","TopicTree_AK4.csv"]
    tpcTree = LoadTree(TreeBaseFNList)
    InfoScoreTable = BuildInfoScoreTable(
            tpcTree = tpcTree,OnlyLettersDigitsLabels=False,
            OutputPath = BertDatasetSubDir)
    SubTopicsDict = BuildSubTopicsDict(tpcTree)
    ParTopicsDict = BuildSubTopicsDict([[y,x] for [x,y] in tpcTree])
    
    #VisDatatable_page_action使用custom時，搭配filter_action=custom時，
    #跳頁可能會自動回到第一頁。
    #VisDatatable_page_action使用native時，
    #第二頁後的tooltip位置可能會出現異常，沒有更新到正確位置。
    VisDatatable_page_action = 'custom'
    #VisDatatable_page_action = 'native'
    
    SrcList = GetSrcList(sql3File)
    sqlCols=['PartNO','pred_Type','text']
    LenSrcList = len(SrcList)
    '''
    if LenSrcList < 300:
        nLeftFileChunk = 120000//LenSrcList
    else:
        nLeftFileChunk = 0
    
    '''
    nLeftFileChunk = 0
    
    FixedTestDir = f"../FixedTest/FixedTest_{args.TRVPort}"
    selFLDirList = [FixedTestDir,datasetDir]
    selFNList = ["select.txt","ESselect.tsv"]
    SelectedFNPatList = []
    for selFLDir in selFLDirList:
        for file in OSWALK(selFLDir):
            for selFN in selFNList:
                if getFNFromFullPath(file) == selFN:
                    if os.path.isfile(file):
                        PatList = open(file,'rt',encoding='utf-8').readlines()
                        SelectedFNPatList.extend(
                            [line.split("\t")[0] for line in PatList])
    SelectedFNPatList = UniqueList(
        [x.strip() for x in SelectedFNPatList])
    #print("SelectedFNPatList",SelectedFNPatList)
    #print("In main init, BinMissionDict", BinMissionDict)
    #raise Exception

    
    if os.path.isfile("證券報告.xlsx"):
        InputXLS = "證券報告.xlsx"
    elif os.path.isfile("BertScript/證券報告.xlsx"):
        InputXLS = "BertScript/證券報告.xlsx"
    ColPosDict = {'TaskNO':0,'Mission':2,'Expiry Date':4,'Topics':6,'Key Word':7}
    print("Start to load MissionDataArray")
    MissionDataArray = LoadMissionData(
        #InputXLS="訂飲料.xlsx",
        InputXLS=InputXLS,
        skiprows = [0],index_col = None,header=0,
        ColPosDict=ColPosDict)
    print("Finished to load MissionDataArray")
    #MissionDataArray [{'TaskNO':'R3', 'Mission': '研析中國現有經濟政策對工業產業發展影響。', 'Expiry Date': 20220123, 'Key Word': '中國經濟', 'Topics': "['CN Economics']"}]
    for mission in MissionDataArray:
        try:
            misBin = {
                "active":True,
                "Icon":"💥",
                "Or_Pool":{
                    "Main":{
                        "InfoScoreSumInterval":[300,99999999],
                        "InfoScoreMeanInterval":[30,99999999],
                        "Labels":{
                            "SimpleTag":reCombiner(
                                reList = [f"^{x}$" 
                                    for x in ast.literal_eval(
                                            mission['Topics'])],
                                method = "or"
                                ).proc(),
                            "MatchingBlockInterval":[3,99999999],
                            "RatioInterval":[0.2,1],
                            },
                        },
                    }
                }
            BinMissionDict[mission['TaskNO']] = misBin
        except Exception as e:
            MES = f"When loading mission {mission} in Test_result_Vis.py, the following error occurs:\n{e}\n"
            MPLOGGER.logW(MES,logFile="Exception.log")
        
        
    #print("MissionDataArray",MissionDataArray)
    print("BinMissionDict",BinMissionDict)
    print("BinMissionDict.keys()",BinMissionDict.keys())
    #raise Exception
    
    KeyWordDataArray = [{"Key Word":"一路"},]

    #移去BinMissionDict中active設定為False的部份，其餘的納入輸出。
    for key in list(BMKeys):
        if not BinMissionDict[key].get("active",False):
            del(BinMissionDict[key])
            continue
        PreambleCols.append(key)
        PreambleColsDefault[key] = ""
        

    #偵測先前是否已有計算過此dataset的完整df之sql3存檔，有的話，直接載入，
    #沒有的話，進行計算，並存檔，供未來載用。
    DF_ALL_OPTFN = os.path.join(datasetDir,"DFPreambleCols_df_ALL")
    DF_ALL_PreambleColsFN = DF_ALL_OPTFN+".sql3"
    
    if os.path.isfile(DF_ALL_PreambleColsFN) and loadPreComputed_DF_ALL:
        print("Found DFPreambleCols_df_ALL Files, loading.")
        df = dfFromSQLite3(DF_ALL_PreambleColsFN)
        df['Date'] = df['Date'].apply(lambda x:"🌎"+x if len(x)>0 and not x.startswith("🌎") else x)
        print("Finish loading DFPreambleCols_df_ALL Files.")
    else:
        print("Didn't find DFPreambleCols_df_ALL Files, computing and saving.")

        VDT_DFBuilder = VisDatatableDFBuilder(
            nProcess=nProcess,
            tpcTree=tpcTree,
            BinMissionDict=BinMissionDict,
            PreambleCols=PreambleCols,
            PreambleColsDefault=PreambleColsDefault,
            sql3File=sql3File, 
            #SrcList = SrcList,
            SelectedFNPatList = SelectedFNPatList,
            #從test_results_verification.sql抓取切片資訊的相關欄位
            sqlCols=sqlCols,
            InfoScoreTable=InfoScoreTable,
            InfoScoreSumLowerBound=InfoScoreSumLowerBound,
            InfoScoreSumUpperBound=InfoScoreSumUpperBound,
            FixedTestFileBound=FixedTestFileBound,
            nLeftFileChunk=nLeftFileChunk,
            nScoringSegUPD=nScoringSegUPD,
            VDDFSortParams = VDDFSortParams,
            SimilarityMethod = SimilarityMethod,
            TwinsHighScoreNoUBD = TwinsHighScoreNoUBD,
            TextSummarization = TextSummarization,
            CountArticleComposition = CountArticleComposition,
            nPiecesToSummaryUPD = nPiecesToSummaryUPD,
            BertDatasetSubDir = BertDatasetSubDir,
            MPLOGGER = MPLOGGER
            )

        df = VDT_DFBuilder.run(SrcList)

        df['Date'] = df['Date'].apply(lambda x:"🌎"+x if len(x)>0 and not x.startswith("🌎") else x)
        print("df",df)
        #WTFAIMode=True將會於dfOutputer內使用客製方式微調輸出格式。
        #以RefPATH做為索引參照資料夾，搭配df的資料，
        #將RefPATH內的WTF加工組裝，輸出新檔至WeiTechFormatJob["OutputPATH"]。
        #print("args.WeiTechFormatSepWorkPool",args.WeiTechFormatSepWorkPool)
        if args.WeiTechFormatSepWorkPool == True:
            '''
            new_WeiTechFormatInputPATH = os.path.join(
                os.path.dirname(path),
                "WeiTechFormatSepWorkPool",
                timeNow()+"_"+args.WeiTechFormatInputPATH
                )
            new_WeiTechFormatOutputPATH = os.path.join(
                os.path.dirname(path),
                "WeiTechFormatSepWorkPool",
                timeNow()+"_"+args.WeiTechFormatOutputPATH
                )
            '''
            tN = timeNow()
            new_WeiTechFormatInputPATH = f"{args.WeiTechFormatInputPATH}_{tN}"
            new_WeiTechFormatOutputPATH = f"{args.WeiTechFormatOutputPATH}_{tN}"
            os.rename(args.WeiTechFormatInputPATH,new_WeiTechFormatInputPATH)
            MKDIR(args.WeiTechFormatInputPATH)
            args.WeiTechFormatInputPATH = new_WeiTechFormatInputPATH
            #args.WeiTechFormatOutputPATH = new_WeiTechFormatOutputPATH
        WeiTechFormatJob = {
            "RefPATH":args.WeiTechFormatInputPATH,
            "OutputPATH":args.WeiTechFormatOutputPATH
            #"WTFAIMode":True
            #"OutputCols":[]
            }
        dfOutputer(
            df[PreambleCols],DF_ALL_OPTFN,
            WeiTechFormatJob=WeiTechFormatJob,
            nProcess=nProcess).run()
        print("Finished computing and saving DFPreambleCols_df_ALL.")
        if args.ExportDFAllToDatabase == True:
            #ExportDFAllToDatabase具有清整下列格式File欄位，並抽取日期之功能
            #UUID_re = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
            #UUID_re+"_20\d{2}-\d{2}-\d{2}T"
            ExportDFAllToDatabase(
                df,ExportDatabasePath = args.ExportDatabasePath,
                ExecutionTime = args.ExecutionTime,nProcess=nProcess)
    

    LabelList = []
    ExemptLabelList = [x for x in InfoScoreTable.keys() if x.startswith("Exempt-")]
    
    CutRange = [0, 3]
    try:
        open("ThisIsAFileToTestWritablity.txt",'wt').close()
        df_json = '{}'
        FilteredDF_json = '{}'
    except:
        df_json = df.to_json(date_format='iso', orient='split')
        FilteredDF_json = df_json
    #FilteredDF = pd.read_json(FilteredDF_json, orient='split')
    print("Initialing, df_json",df_json)
    print("Initialing, FilteredDF_json",FilteredDF_json)
    
    FilteredDF = df
    
    current_page_max = len(FilteredDF)//PAGE_SIZE + (len(FilteredDF)%PAGE_SIZE !=0)
    #FilteredDF_OPTFN = ""
    #PartCol = PreambleCols+[str(i) for i in range(CutRange[0],CutRange[1])]
    #PartColDF = FilteredDF[PartCol]
    #PartColDF_json = PartColDF.to_json(date_format='iso', orient='split')  
    ShowingFile = []
    nSamples = df.shape[0]
    #print("PartColDF",PartColDF['Date'])
    controls1 = [
        rc.CustomRangeSlider(
            id="CutRange", min=0, 
            #max=nDigitCols, label="CutRange", step=1,
            max=30, label="CutRange", step=1,
            value = CutRange),
    ]
    
    Initial_InfoScore_Range_Bar = Build_InfoScore_Range_Bar(df)
    if args.AutoInfoScoreBound == True:
        AutoISlbd,AutoISubd,ISMarks = ISMarksAnalysis(df)
        #args.InfoScoreSumLowerBound = AutoISlbd
        #args.InfoScoreSumUpperBound = AutoISubd
        ShowElapsedTime(start_time)
        print("Start to Apply AutoInfoScoreBound.")
        df = DFfilter(df, 
        InfoScoreSumLowerBound = AutoISlbd,
        InfoScoreSumUpperBound = AutoISubd
        )
        ShowElapsedTime(start_time)
        print("Finished Applying AutoInfoScoreBound.")
        print("df",df)
        #dfOutputer(df[PreambleCols],DF_OPTFN).run()
        
    MES = "As args.AutoInfoScoreBound is True, the df is refined with \n"
    MES += f"InfoScore Range=[{AutoISlbd}, {AutoISubd}]"
    MPLOGGER.logW(MES=MES,logFile="Test_result_Vis.log")
    print("rdy to run server, df_json is ",df_json)
    print("rdy to run server, FilteredDF_json is ",FilteredDF_json)

    cms = cmapSet()
    ColorDict = {}
    if ListOnlyOccuringLabels == True:
        cols=['pred_Type']
        #不考慮分數限制等篩選條件，列出test_results_verification所有曾出現的pred_Type值。
        #LabelList = sorted(set(
            #[x[0] for x in sqlite3Query(SQLname=sql3File, table = "sampleSrc", cols=cols)]))
        #考慮分數限制等篩選條件後，列出df剩下出現的檔案中所有曾出現的pred_Type值。
        FileListPat =','.join([
            f'"{x}"' for x in list(df["File"])])
        query = f'SELECT DISTINCT pred_Type FROM sampleSrc \
            WHERE File IN ({FileListPat});'
        FileLabelList = sqlite3Query(
            sql3File, query = query,ListForm = True)
        LabelList.extend(FileLabelList)
    
    #LabelList = sorted(set(LabelList), key=lambda L: (L.lower(), L))
        LabelList = sorted(set(LabelList), key=lambda L: L.lower())
    LabelList.extend(ExemptLabelList)
    print("LabelList", LabelList)
    
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

    ColorDict["可於此格手動輸入特定分類名"] = '#FFFFFF'
    ColorDict["Scrap"] = '#E3E4E1'
    colorIndex = 0
    for label in LabelList:
        if label == "Scrap":
            continue
        else:
            #ColorDict[label] = cms.pop()
            #ColorDict[label] = cms[colorIndex]
            ColorDict[label] = RandomColor(seed = label)
            colorIndex += 1
            colorIndex = colorIndex % len(cms)
    print("ColorDict", ColorDict)
    
    #ColorDF = ColorDictToColorDF(ColorDict)
    #ColorDF = BuildColorDF(ColorDict,ClassTable)
    ColorDF,ColorDF_json,Colortable_style_data_conditional = \
        BuildColorDF(ColorDict,ClassTable)

    if "Twins" in df.columns:
        TwinsColorDict = {}
        #print("df[Twins].unique()",df["Twins"].unique())
        
        for ct,TwinGroup in enumerate(sorted(df["Twins"].unique())):
            if TwinGroup =="":
                continue
            TwinsColorDict[TwinGroup] = RandomColor(777+ct)
        print("TwinsColorDict",TwinsColorDict)


    selectedLabels = []
    selectedLabels_json = json.dumps(selectedLabels, indent = 4)
    style_data_conditional,style_cell_conditional,style_cell,tooltip_data \
        = Build_VisDatatable_style(df, ColorDict, BinMissionDict)
        
        
    from Test_result_Vis_layout import Build_Upload_Block
    from Test_result_Vis_layout import Build_Finished_Task_Block

    app.layout = serve_layout
    #app.layout = serve_layout(datasetDir)
    
    
    #args = ClassfierOptionParser()
    if args.public == True:
        hostIP = '0.0.0.0'
    else:
        hostIP = '127.0.0.1'
    ACPort = args.TRVPort
    #setproctitle.setproctitle(f'TRV{args.TRVPort}')
    #print("args.InfoScoreSumLowerBound", InfoScoreSumLowerBound)
    #app.run_server(debug=True, use_reloader=False, port = ACPort,host='0.0.0.0')
    '''
    if "linux" in platform.system().lower():
        KillOldServerPSCMD = f"pkill TRV{args.TRVPort}"
        print(f"Running CMD: {KillOldServerPSCMD}")
        os.system(KillOldServerPSCMD)
    '''
#%%針對已切好之高分文本，執行文本摘要功能，並反存回sqlite資料庫
    if args.TextSummarization == True:
        SumPath = os.path.join(BertDatasetSubDir,"SummarizingSource")
        SumOptPath = os.path.join(BertDatasetSubDir,"Summary")
        MES = f"Start to summarize the text in {SumPath}"
        MPLOGGER.logW(MES=MES,logFile="Test_result_Vis.log")
        #確認有足夠的GPU RAM執行，如果等夠久還是沒有的話，則繼續以CPU執行。
        if "windows" in platform.system().lower():
            freeGPUmemReq = 6500
        else:
            freeGPUmemReq = 10000
        freeGPUConformer(
            ObjectName = args.BertDatasetSubDir,freeGPUmemReq = freeGPUmemReq,
            #RetryLimit = 1,
            ReachLimitContinueMode = True
            ).proc()
        #將工作目錄下的SumPath下的文本進行摘要。
        #SummarizingPathText(SummarizingSourcePath=SumPath,outputPath=BertDatasetSubDir)
        
        CMD = f"python GenerativeLanguageModel/GenerativeSummary.py"
        #CMD += convert_to_args_str(args)
        CMD += f" -SumPath {SumPath}"
        CMD += f" -SumOptPath {SumOptPath}"
        print("Generative Summary CMD:\n",CMD)
        os.system(CMD)
    
        MES = f"Finished summarizing the text in {SumPath} for {len(OSWALK(SumPath))} files"
        MPLOGGER.logW(MES=MES,logFile="Test_result_Vis.log")
        DF_All_sql3File = os.path.join(BertDatasetSubDir,"DFPreambleCols_df_ALL.sql3")
        #SumOptPath = os.path.join(BertDatasetSubDir,"Summary")
        SumFileDict = dict()
        for file in OSWALK(SumOptPath):
            if any([re.search("Summary_\d{1,3}.txt",file) is None,
                    GetFileSize(file)==0]):
                continue
            key = os.path.basename(os.path.dirname(file))
            if key in SumFileDict:
                SumFileDict[key].append(file)
            else:
                SumFileDict[key] = [file]
        for key in SumFileDict:
            SumFileDict[key].reverse()
        #print("SumFileDict",SumFileDict)
        #print("sorted(OSWALK(SumOptPath))",sorted(OSWALK(SumOptPath)))
        #存入摘要結果至DF_All_sql3File
        for key in SumFileDict:
        #for file in sorted(OSWALK(SumOptPath)):
            file = SumFileDict[key][0]
            #print("="*50)
            #print("file",file)
            FN = os.path.basename(os.path.dirname(file))+".txt"
            SumText = TSVTextAdapter(textReader(file).run())
            query = f'UPDATE sampleSrc SET Summary="{SumText}" WHERE File = "{FN}";'
            #print("sql3File",sql3File)
            #print("query",query)
            sqlite3Query(DF_All_sql3File, query = query)
        df = dfFromSQLite3(DF_All_sql3File)
#%%部署web服務   
    MES = f"args.TRVWebHost is setted as {args.TRVWebHost}.\n"
    if args.TRVWebHost == True:
        if "windows" in platform.system().lower():
            ssl_context = None
        else:
            ssl_context = 'adhoc'
        clearPort(process=f"TRV{args.TRVPort}")
        time.sleep(2)
        setproctitle.setproctitle(f'TRV{args.TRVPort}')
        app.run_server(debug=True, use_reloader=False, 
                       port = ACPort, host = hostIP,
                       ssl_context=ssl_context)
        MES += f"The site is hosted on \n {hostIP}:{ACPort}."
    else:        
        MES = "PGM will only output Full_bar_df and not to host the web site."
    MPLOGGER.logW(MES=MES,logFile="Test_result_Vis.log")
    
    NewBertDatasetSubDir = BertDatasetSubDir.replace(
        "_is_running_TestResultVis","_rdy_for_Spike")
    os.rename(BertDatasetSubDir,NewBertDatasetSubDir)    
    MES = "-"*50+"\n"
    MES += f"TestResultVis is finished. Rename {BertDatasetSubDir} as {NewBertDatasetSubDir}"
    MPLOGGER = MPlogger(logSubDir=f"{NewBertDatasetSubDir}/logs")
    MPLOGGER.logW(MES)
    #os.system("pause")
    
#項次 領域 項目 單位 日期 備註