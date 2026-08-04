import dash  # pip install dash
import dash_cytoscape as cyto  # pip install dash-cytoscape==0.2.0 or higher
import dash_html_components as html
import dash_core_components as dcc
from dash.dependencies import Output, Input
import pandas as pd  # pip install pandas
import plotly.express as px
import math

from pages.labelViewer.callback_manager import CallbackManager

callback_manager = CallbackManager()


'''
@callback_manager.callback(
    dash.dependencies.Output('label', 'children'),
    [dash.dependencies.Input('call_btn', 'n_clicks')])
def update_label(n_clicks):
    if n_clicks > 0:
        return "Callback called!"
'''


@callback_manager.callback(
    dash.dependencies.Output('org-chart', 'layout'),
    [dash.dependencies.Input('dpdn', 'value')])

#@app.callback(Output('org-chart', 'layout'),
              #Input('dpdn', 'value'))
def update_layout(layout_value):
    if layout_value == 'breadthfirst':
        return {
        'name': layout_value,
        'roots': '[id = "Executive Director (Harriet)"]',
        'animate': True
        }
    else:
        return {
            'name': layout_value,
            'animate': True
        }



@callback_manager.callback(
    dash.dependencies.Output('empty-div', 'children'),
    [dash.dependencies.Input('org-chart', 'mouseoverNodeData'),
     dash.dependencies.Input('org-chart', 'mouseoverEdgeData'),
     dash.dependencies.Input('org-chart', 'tapEdgeData'),
     dash.dependencies.Input('org-chart', 'tapNodeData'),
     dash.dependencies.Input('org-chart', 'selectedNodeData'),
     ])
#
#@app.callback(
    #Output('empty-div', 'children'),
    #Input('org-chart', 'mouseoverNodeData'),
    #Input('org-chart','mouseoverEdgeData'),
    #Input('org-chart','tapEdgeData'),
    #Input('org-chart','tapNodeData'),
    #Input('org-chart','selectedNodeData')
#)

def update_layout(mouse_on_node, mouse_on_edge, tap_edge, tap_node, snd):
    print("Mouse on Node: {}".format(mouse_on_node))
    print("Mouse on Edge: {}".format(mouse_on_edge))
    print("Tapped Edge: {}".format(tap_edge))
    print("Tapped Node: {}".format(tap_node))
    print("------------------------------------------------------------")
    print("All selected Nodes: {}".format(snd))
    print("------------------------------------------------------------")

    return 'see print statement for nodes and edges selected.'


@callback_manager.callback(
    dash.dependencies.Output('my-graph', 'figure'),
    [dash.dependencies.Input('org-chart', 'tapNodeData'),
     dash.dependencies.Input('intermediate-value-df_tree', 'data')
     ])
#@app.callback(
    #Output('my-graph','figure'),
    #Input('org-chart','tapNodeData'),
#)
def update_nodes(data,df_tree_json):
#def update_nodes(data):
    if data is None:
        return dash.no_update
    else:
        #dff = df_tree.copy()
        dff = pd.read_json(df_tree_json, orient='split')
        #dff = df_tree
        dff.loc[dff.name == data['label'], 'color'] = "yellow"
        fig = px.bar(dff, x='name', y='slaves_freed')
        fig.update_traces(marker={'color': dff['color']})
        return fig
