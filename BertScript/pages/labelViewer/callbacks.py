import json

import dash
from dash.dependencies import Input, Output, State
#import dash_core_components as dcc
from dash import dcc
#import dash_html_components as html
from dash import html

import dash_cytoscape as cyto
from pages.labelViewer.demos import dash_reusable_components as drc



from utils.visualization.Dash_utils import CallbackManager
callback_manager = CallbackManager()

# ############################## CALLBACKS ####################################
@callback_manager.callback(
    dash.dependencies.Output('cytoscape', 'zoom'),
    [dash.dependencies.Input('cyto_slider', 'value')])
def update_zoom(value):
    #print(value)
    return value

@callback_manager.callback(
    dash.dependencies.Output('tap-node-json-output', 'children'),
    [dash.dependencies.Input('cytoscape', 'tapNode')])
#@app.callback(Output('tap-node-json-output', 'children'),
              #[Input('cytoscape', 'tapNode')])
def display_tap_node(data):
    return json.dumps(data, indent=2)



@callback_manager.callback(
    dash.dependencies.Output('tap-edge-json-output', 'children'),
    [dash.dependencies.Input('cytoscape', 'tapEdge')])
#@app.callback(Output('tap-edge-json-output', 'children'),
              #[Input('cytoscape', 'tapEdge')])
def display_tap_edge(data):
    return json.dumps(data, indent=2)



@callback_manager.callback(
    dash.dependencies.Output('cytoscape', 'layout'),
    [dash.dependencies.Input('dropdown-layout', 'value')],
    [dash.dependencies.Input('dropdown-rankDir', 'value')],
    [dash.dependencies.State('cyto_slider', 'value'),])
#@app.callback(Output('cytoscape', 'layout'),
              #[Input('dropdown-layout', 'value')])
def update_cytoscape_layout(
        layout_name,rankDir,zoom):
    layout = {"name":layout_name,
              "animate":True,
              "zoom":zoom}
    if layout["name"] in ["dagre"]:
        #layout["spacingFactor"] = 1.2
        layout["rankSep"] = 100
        #layout["ranksep"] = 1000
        #'TB' for top to bottom flow,
        #'LR' for left to right. 
        #default is undefined, making it plot top-bottom
        layout["rankDir"] = rankDir
    elif layout["name"] in ["cose","cose-bilkent"]:
        layout["idealEdgeLength"] = 120
        layout["animate"] = False
    #elif layout["name"] in ["spread"]:
        #layout["minDist"] = 50
    return layout



'''
@app.callback(Output('cytoscape', 'elements'),
              [Input('cytoscape', 'tapNodeData')],
              [State('cytoscape', 'elements'),
               State('radio-expand', 'value')])
'''
@callback_manager.callback(
    dash.dependencies.Output('cytoscape', 'elements'),
    [dash.dependencies.Input('cytoscape', 'tapNodeData'),
     dash.dependencies.Input('radio-expand', 'value'),],
    [dash.dependencies.State('cytoscape', 'elements'),
     dash.dependencies.State('intermediate-value-genesis_node', 'data'),
     dash.dependencies.State('intermediate-value-default_elements', 'data'),
     dash.dependencies.State('intermediate-value-following_node_di', 'data'),
     dash.dependencies.State('intermediate-value-following_edges_di', 'data'),
     dash.dependencies.State('intermediate-value-followers_node_di', 'data'),
     dash.dependencies.State('intermediate-value-followers_edges_di', 'data')
     ])
def generate_elements(nodeData, 
                      expansion_mode,
                      elements, 
                      
                      genesis_node_json,
                      default_elements_json,
                      following_node_di_json,
                      following_edges_di_json,
                      followers_node_di_json,
                      followers_edges_di_json):
    genesis_node = json.loads(genesis_node_json)
    default_elements = json.loads(default_elements_json)
    following_node_di = json.loads(following_node_di_json)
    following_edges_di = json.loads(following_edges_di_json)
    followers_node_di = json.loads(followers_node_di_json)
    followers_edges_di = json.loads(followers_edges_di_json)
    #print("="*50)
    #print("In GE following_node_di",following_node_di)
    #print("expansion_mode",expansion_mode)
    if not nodeData:
        return default_elements

    # If the node has already been expanded, we don't expand it again
    #print("nodeData",nodeData)
    #print("nodeData['id']",nodeData['id'])
    #print("expansion_mode",expansion_mode)
    #print("="*50)
    #print("elements",elements)
    if nodeData.get('expanded'):
        if nodeData['expanded'][expansion_mode]:
            return elements
    #print("nodeData['id']",nodeData['id'])
    # This retrieves the currently selected element, and tag it as expanded
    for element in elements:
        if nodeData['id'] == element.get('data').get('id'):
            #element['data']['expanded'] = True
            if 'expanded' not in element:
                element['expanded'] = {}
            element['expanded'][expansion_mode] = True
            #print("element expand",element.get('data').get('id'))
            break

    if expansion_mode == 'followers':
        #print("followers_node_di",followers_node_di)
        followers_nodes = followers_node_di.get(nodeData['id'])
        followers_edges = followers_edges_di.get(nodeData['id'])
        #print("="*50)
        #print("followers_nodes",followers_nodes)
        if followers_nodes:
            #for node in followers_nodes:
                #node['classes'] = 'followerNode'
            elements.extend(followers_nodes)
        #print("="*50)
        #print("elements Af extend followers_nodes",elements)
        if followers_edges:
            for follower_edge in followers_edges:
                follower_edge['classes'] = 'followerEdge'
            elements.extend(followers_edges)

    elif expansion_mode == 'following':

        following_nodes = following_node_di.get(nodeData['id'])
        following_edges = following_edges_di.get(nodeData['id'])

        if following_nodes:
            ids = [term['data']['id'] for term in elements]
            for node in following_nodes:
                if node['data']['id'] not in ids:

                #for gennode in genesis_node:
                    #if node['data']['id'] != genesis_node['data']['id']:
                    #if node['data']['id'] != gennode['data']['id']:    

                        #node['classes'] = 'followingNode'
                        elements.append(node)
                
                
                


        if following_edges:
            for follower_edge in following_edges:
                follower_edge['classes'] = 'followingEdge'
            elements.extend(following_edges)
    #print("elements",elements)
    #elements = list(set(elements))
    elements = sorted({v['data']['id']:v for v in elements}.values(),key = lambda x:x['data']['id'])
    #print("="*50)
    #print("elements b4 return",elements)
    return elements

