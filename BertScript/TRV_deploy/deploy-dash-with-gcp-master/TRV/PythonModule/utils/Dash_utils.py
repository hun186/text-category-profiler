import os

import dash
import dash_table
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State
import reusable_components as rc  # see reusable_components.py
import plotly.express as px

from utils.utilities import MKDIR
import pandas as pd
#import plotly.io as pio; pio.renderers.default='notebook'
from plotly.offline import plot
from utils.MP_utils import MPlogger


class LevelDVisProcessor:
    def __init__(self, df = None, VisPath = None, color = None,
                 color_discrete_map = None,
                 method = "sunburst",
                 OptAnnotation = False,
                 VisOutputSubDir = "LDVisual_",
                 HtmlOutput = "",
                 FolderConstrainList = []):
        self.df = df
        self.VisPath = VisPath
        if color == None:
            color = VisPath[0]
        self.color = color
        self.color_discrete_map = color_discrete_map
        self.method = method
        self.OptAnnotation = OptAnnotation
        self.VisOutputSubDir = VisOutputSubDir
        self.HtmlOutput = HtmlOutput
        self.FolderConstrainList = FolderConstrainList
    def show(self):
        print("VisPath:", self.VisPath)
        print("method:", self.method)
        print("HtmlOutput:", self.HtmlOutput)
        print("FolderConstrainList:", self.FolderConstrainList)
    def run(self):
    #def LevelDVis(df,VisPath,method = "sunburst",HtmlOutput = "",
                  #FolderConstrainList = []):
        #LevelDataVisulization
        #df[VisPath[0]] = df[VisPath[0]].apply(customwrap)
        #df[VisPath[1]] = df[VisPath[1]].apply(customwrap)
        #df[VisPath[2]] = df[VisPath[2]].apply(customwrap)
        # BurstPath = [Column A, Column B, Column C]
        if self.df.shape[0] == 0 :
            MES = "When trying running LevelDVisProcessor, the dataframe is empty and abort the job."
            MPlogger.logW(MES)
            return None
        if self.HtmlOutput == "":
            self.HtmlOutput = "{}_{}.html".format(str(self.VisPath), self.method)
        #fig = getattr(px, self.method)(self.df,path= self.VisPath, color='DataSrcType')
        if self.method in ["sunburst", "treemap"]:
            kwargs = {
                "path": self.VisPath,
                "color": self.color,
                }
            if self.color_discrete_map != None:
                self.color_discrete_map["(?)"]="black"
                kwargs["color_discrete_map"]=self.color_discrete_map
        #elif self.method == "treemap":
            #kwargs = {}
        else:
            kwargs = {}

        fig = getattr(px, self.method)(
            self.df,
            **kwargs
            )
            #kwargs)
        if self.OptAnnotation == True:
            fig.data[0].textinfo= 'label+value+percent parent+percent entry'
            fig.update_layout(
                uniformtext=dict(minsize=10, mode=False),
                #uniformtext=dict(minsize=10, mode='show'),
                #uniformtext=dict(minsize=6, mode='hide'),
                margin = dict(t=50, l=25, r=25, b=25),
                height=700,
            )
        #self.VisOutputSubDir = "LDVisual_"
        if self.FolderConstrainList == []:
            self.VisOutputSubDir += "all"
        else:
            self.VisOutputSubDir += 'Only'
            self.VisOutputSubDir += '_'.join([
                x.lstrip("\\").split("\\")[0] for x in self.FolderConstrainList])
        MKDIR(self.VisOutputSubDir)
        self.HtmlOutput = os.path.join(self.VisOutputSubDir,
                                  self.HtmlOutput)
        #fig.update_layout(uniformtext=dict(minsize=10, mode='hide'))
        #fig.write_html(self.HtmlOutput)
        #return True
        return fig
    
def create_card(card_id, title, description, fig=None):
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

def get_button_id(ctx, funName):
    #ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    #print("In table_update, button_id", button_id)
    print(f"In function {funName}, button_id is {button_id}.")
    return button_id

def DictToDataArray(dictionary, keyName='key', valueName='value'):
    result = []
    for x in dictionary.keys():
        result.append(
            {keyName:x,valueName:str(dictionary[x])})
    return result