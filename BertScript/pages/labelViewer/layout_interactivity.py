import json
import time

import dash
from dash.dependencies import Input, Output, State
#import dash_core_components as dcc
from dash import dcc
#import dash_html_components as html
from dash import html

import dash_cytoscape as cyto
from pages.labelViewer.demos import dash_reusable_components as drc
import reusable_components as rc  # see reusable_components.py

#from text_category_profiler.pipeline.TCF_utils import GetTreeFilePath

from ClassesTree.ClassesTree_utils import LoadTree
from ClassesTree.ClassesTree_utils import GetRoots
from text_category_profiler.core.utilities import flattenList
from text_category_profiler.core.utilities import RandomColor
# Load extra layouts


#app = dash.Dash(__name__)
#server = app.server

def create_layout(app,Roots=[]):
    cyto.load_extra_layouts()
    # ###################### DATA PREPROCESSING ######################
    # Load data
    #print(f"for create_layout in alyout_interactivity.py, Roots is {Roots}")
    '''
    with open('pages/labelViewer/demos/data/sample_network.txt', 'r') as f:
        network_data = f.read().split('\n')
    '''
    #TreeFile = GetTreeFilePath()
    #with open(TreeFile, 'rt', encoding='utf-8') as f:
        #network_data = f.read().split('\n')

    tpcTree = []
    network_data = []
    #Roots = []
    TreeBaseFNList = ["TopicTree.csv","TopicTree_AK4.csv"]
    tpcTree = LoadTree(TreeBaseFNList)
    
    #for TreeBaseFN in ["TopicTree.csv","TopicTree_AK4.csv"]:
        #TreeFile = GetTreeFilePath(TreeBaseFN = TreeBaseFN)
        #tpcTree.extend(LoadTree(
            #TreeFile,OnlyLettersDigitsLabels= False))
        
        #Roots.extend(GetRoots(tpcTree, OnlyLettersDigitsLabels = False))
        #with open(TreeFile, 'rt', encoding='utf-8') as f:
            #network_data.extend(f.read().split('\n'))
    #tpcTree = list(filter(None,tpcTree))
    if Roots == []:
        Roots = GetRoots(tpcTree, OnlyLettersDigitsLabels = False)
    network_data = tpcTree
    #print("Roots",Roots)
    LabelList = sorted(set(flattenList(tpcTree)))
    
    #network_data = [line.rpartition(",")[0] for line in network_data]
    
    # We select the first 750 edges and associated nodes for an easier visualization
    #edges = network_data[:40]
    edges = network_data
    nodes = set()
    
    following_node_di = {}  # user id -> list of users they are following
    following_edges_di = {}  # user id -> list of cy edges starting from user id
    
    followers_node_di = {}  # user id -> list of followers (cy_node format)
    followers_edges_di = {}  # user id -> list of cy edges ending at user id
    
    cy_edges = []
    cy_nodes = []
    
    #for edge in edges:
    for edge in tpcTree:
        
        #if " " not in edge:
            #continue

        
        #if edge.startswith("#") or len(edge.split(",")) < 2:
            #continue
        #source, target = edge.split(",")
                
        #source, target = edge.split(",")[0:2]
        source, target = edge
        #source, target = [x.replace(" ","_") for x in edge.split(",")[0:2]]
        cy_edge = {'data': {'id': source+"-->"+target, 'source': source, 'target': target}}
        #cy_edge = {'data': {'id': source+target, 'source': source, 'target': target}}
        #cy_target = {"data": {"id": target, "label": "User #" + str(target[-5:])}}
        #cy_source = {"data": {"id": source, "label": "User #" + str(source[-5:])}}
        cy_target = {"data": {"id": target, "label": str(target)}}
        cy_source = {"data": {"id": source, "label": str(source)}}


        if source not in nodes:
            nodes.add(source)
            cy_nodes.append(cy_source)
        if target not in nodes:
            nodes.add(target)
            cy_nodes.append(cy_target)
    
        # Process dictionary of following
        if not following_node_di.get(source):
            following_node_di[source] = []
        if not following_edges_di.get(source):
            following_edges_di[source] = []
    
        following_node_di[source].append(cy_target)
        following_edges_di[source].append(cy_edge)
    
        # Process dictionary of followers
        if not followers_node_di.get(target):
            followers_node_di[target] = []
        if not followers_edges_di.get(target):
            followers_edges_di[target] = []
    
        followers_node_di[target].append(cy_source)
        followers_edges_di[target].append(cy_edge)
    #print("followers_node_di",followers_node_di)
    #print("following_edges_di",following_edges_di)
    #print("="*50)
    #print("followers_node_di[Informative]",followers_node_di["Informative"])
    #print("following_node_di[Informative]",following_node_di["Informative"])
    following_node_di_json = json.dumps(following_node_di)
    following_edges_di_json = json.dumps(following_edges_di)    
    followers_node_di_json = json.dumps(followers_node_di)
    followers_edges_di_json = json.dumps(followers_edges_di)
    #print("cy_nodes",cy_nodes)
    genesis_node = cy_nodes[0]
    genesis_node['classes'] = "genesis"
    
    genesis_node = []
    for node in cy_nodes:
        for root in Roots:
            #print("node['data']['id']",node['data']['id'])
            if node['data']['id'] == root: 
                node['classes'] = "genesis"
                #print(node['data']['id'],"match")
                genesis_node.append(node)
    #print("nodes",nodes)
    #print("Roots",Roots)
    #time.sleep(10)
    genesis_node_json = json.dumps(genesis_node)
    #default_elements = [genesis_node]
    default_elements = genesis_node
    default_elements_json = json.dumps(default_elements)
    
    default_stylesheet = [
        {
            "selector": 'node',
            'style': {
                "opacity": 0.65,
                'z-index': 9999,
                'label': 'data(label)',
                "text-wrap": "wrap",
                "text-max-width": 80,
            },
            
        },
        {
            "selector": 'edge',
            'style': {
                "curve-style": "bezier",
                "opacity": 0.45,
                'z-index': 5000
            }
        },
        {
            'selector': '.followerNode',
            'style': {
                'background-color': '#0074D9'
            }
        },
        {
            'selector': '.followerEdge',
            "style": {
                "mid-target-arrow-color": "blue",
                "mid-target-arrow-shape": "vee",
                "line-color": "#0074D9"
            }
        },
        {
            'selector': '.followingNode',
            'style': {
                'background-color': '#FF4136'
            }
        },
        {
            'selector': '.followingEdge',
            "style": {
                "mid-target-arrow-color": "red",
                "mid-target-arrow-shape": "vee",
                "line-color": "#FF4136",
            }
        },
        {
            "selector": '.genesis',
            "style": {
                'background-color': '#B10DC9',
                "border-width": 2,
                "border-color": "purple",
                "border-opacity": 1,
                "opacity": 1,
    
                "label": "data(label)",
                "color": "#B10DC9",
                "text-opacity": 1,
                "font-size": 12,
                'z-index': 9999
            }
        },
        {
            'selector': ':selected',
            "style": {
                "border-width": 2,
                "border-color": "black",
                "border-opacity": 1,
                "opacity": 1,
                "label": "data(label)",
                "color": "black",
                "font-size": 12,
                'z-index': 9999
            }
        }
    ]
    '''
    default_stylesheet.extend([
            {#for ranksep of dagre
            'selector': 'graph',
            "style": {
                "ranksep": 500,
                "rankSep": 500,
                "RankSep": 500,
                }
            }
        ]
    )
    '''
    for label in LabelList:
        default_stylesheet.append(
            {
                #'selector': f'.{label}',
                'selector': f'[label = "{label}"]',
                'style': {
                    'background-color': RandomColor(seed = label),
                    'line-color': RandomColor(seed = label)
                }
            }
            )
    #print("default_stylesheet",default_stylesheet)
    
    # ################################# APP LAYOUT ################################
    styles = {
        'json-output': {
            'overflow-y': 'scroll',
            'height': 'calc(50% - 25px)',
            'border': 'thin lightgrey solid'
        },
        'tab': {'height': 'calc(98vh - 80px)'},
    }
    
    #app.layout = html.Div([
    #return html.Div([
    return rc.Row([
        html.Div(className='col-10', children=[
            cyto.Cytoscape(
                id='cytoscape',
                elements=default_elements,
                stylesheet=default_stylesheet,
                style={
                    'height': '95vh',
                    #"rankSep": "300px",
                    #'height': '200vh',
                    #'height': '100%', #如使用本設定，再加上zoom=2，在DRN可能會造成主圖無法顯示，原因不明。
                    'width': '100%'
                },
                zoomingEnabled=True,
                zoom=1,
                userZoomingEnabled=False,
            )
        ]),
    
        html.Div(className='col-2', children=[
            dcc.Tabs(id='tabs', children=[
                dcc.Tab(label='Ctrl Panel', children=[
                    drc.NamedDropdown(
                        name='Layout',
                        id='dropdown-layout',
                        options=drc.DropdownOptionsList(
                            'random',
                            'grid',
                            'circle',
                            'concentric',
                            'breadthfirst',
                            'cose',
                            #'cose-bilkent',
                            'dagre',
                            'cola',
                            'klay',
                            'spread',
                            'euler'
                        ),
                        value='dagre',
                        clearable=False
                    ),
                    drc.NamedDropdown(
                        name='Dagre hierarchical direction',
                        id='dropdown-rankDir',
                        options=drc.DropdownOptionsList(
                            "TB",
                            "LR",
                        ),
                        value='LR',
                        clearable=False
                    ),
                    
                    drc.NamedRadioItems(
                        name='Expand',
                        id='radio-expand',
                        options=drc.DropdownOptionsList(
                            'followers',
                            'following'
                        ),
                        value='following'
                    )
                ]),
    
                dcc.Tab(label='JSON', children=[
                    html.Div(style=styles['tab'], children=[
                        html.P('Node Object JSON:'),
                        html.Pre(
                            id='tap-node-json-output',
                            style=styles['json-output']
                        ),
                        html.P('Edge Object JSON:'),
                        html.Pre(
                            id='tap-edge-json-output',
                            style=styles['json-output']
                        )
                    ])
                ]),
                
            ]),
            
        #dcc.Slider(id='cyto_slider', min=0.5, max=2, step=0.1),
        rc.CustomSlider(
            id="cyto_slider", min=0.5,
            max=2, label="Zoom", step=0.1,
            value = 1.3,marks={})
        ]),
        dcc.Store(id='intermediate-value-genesis_node',  data = genesis_node_json),
        dcc.Store(id='intermediate-value-default_elements',  data = default_elements_json),
        dcc.Store(id='intermediate-value-following_node_di',  data = following_node_di_json),
        dcc.Store(id='intermediate-value-following_edges_di',  data = following_edges_di_json),
        dcc.Store(id='intermediate-value-followers_node_di',  data = followers_node_di_json),
        dcc.Store(id='intermediate-value-followers_edges_di',  data = followers_edges_di_json),

    ])