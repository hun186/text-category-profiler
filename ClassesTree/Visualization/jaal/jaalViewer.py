import os
from PackageImport import PackageImporter
PackageImporter.proc()

DirRouteList = os.getcwd().split(os.path.sep)
os.chdir("/".join(DirRouteList[:DirRouteList.index("TopicClassification")+1]))
print(f"Change working directory to {os.getcwd()}")
#if os.getcwd().split(os.path.sep)[] in [
        #"jaal"]:
    #os.chdir("../../")
    #print(f"Change working directory to {os.getcwd()}")

#raise Exception

from jaal.datasets import load_got
import pandas as pd
import csv
import argparse

from ClassesTree.ClassesTree_utils import LoadTree
#from ClassesTree.ClassesTree_utils import SetTreeFiles
from ClassesTree.ClassesTree_utils import GetSubTopics
from ClassesTree.ClassesTree_utils import BuildSubTopicsDict
from ClassesTree.ClassesTree_utils import GetRoots
from ClassesTree.ClassesTree_utils import BuildInfoScoreTable
from ClassesTree.ClassesTree_utils import CountDegree
from ClassesTree.longestPath import longestPath

#from utils.utilities import hasher
from utils.utilities import str2bool
#from utils.df_utils import CSVtodf
from utils.df_utils import flattenList


def ClassfierOptionParser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--ArtCluPort", help="Input the port for hosting the web.",
        type=int, default=8050)
    parser.add_argument(
        "-pub", "--public", help="Publish the web.",
        type=str2bool, default=False)
    parser.add_argument(
        "-QRt", "--QueryRoot", help="Query with the topic as root.",
        type=str, default="Spacetime Singularity Of Tree")
        #type=str, default="TW Affairs")
    #args = parser.parse_args()
    args, unknown = parser.parse_known_args()
    return args, unknown

def setCategoryOfTopic(topic,ancestors):
    '''
    Get the high level ancients as category.
    topic:CERP-Insurance Industry
    Category:{'International Economics', 'Asia-Pacific Affairs', 'CN Affairs'}
    目前Jaal只接受20個以下的類型用於塗色
    '''
    catKey = sorted(ancestors[topic].keys())[-1:][0]
    return tuple(sorted(ancestors[topic][catKey]))

def JaalViewMain(QueryRoot = "TW Affairs",createMode = False,hostIP='127.0.0.1'):
    tpcTree = LoadTree(["TopicTree.csv","TopicTree_AK4.csv"],)
    #tpcTree = LoadTree(TreeFile,
                           #OnlyLettersDigitsLabels= OnlyLettersDigitsLabels)
    RootTopics = GetRoots(tpcTree)
    print(f"After loading, RootTopics is {RootTopics}")
    
    #print("tpcTree",tpcTree)
    tpcTreeTemp = []
    for [x,y] in tpcTree:
        if [x,y] not in tpcTreeTemp:
            tpcTreeTemp.append([x,y])
    tpcTree = tpcTreeTemp
    #print(f"RootTopics is {RootTopics}")
    #time.sleep(10)
    #print("len(tpcTree)",len(tpcTree))
    tpcs = GetSubTopics(RootTopics,tpcTree,GroupByDepth=True)
    #print("tpcs",tpcs)
    #print("tpcs.keys()",tpcs.keys())
    #raise Exception
    #load the data
    
    #InputCSV = "TopicTree.csv"
    #tpc_df = CSVtodf(InputCSV)
    #print(node_df)
    #edge_df = pd.DataFrame()
    #edge_df["from"] = tpc_df["#母類別"]
    #edge_df["to"] = tpc_df["子類別"]
    edge_df = pd.DataFrame(tpcTree, columns = ['from', 'to']) 
    edge_df["strength"] = "medium"
    #print(tpcTree[:5])
    
    #print(edge_df)
    edge_df = edge_df#[:150]
    #edge_df = edge_df[:-1]
    
    node_lv_list = []
    #node_lv_dict = dict()
    #nodOc = set()
    for key in tpcs.keys():
        for nod in tpcs[key]:
            node_lv_list.append([nod,int(key)])
            #if nod in nodOc:
                #raise Exception
            #nodOc.add(nod)
    #print("nodOc",nodOc)
    #print(node_lv_dict)
    node_df = pd.DataFrame(node_lv_list, columns = ['id', 'depth'])
    edge_weight_tpcTree = [[x,y,1] for [x,y] in tpcTree]
    RootLGPDict = {
        root:longestPath(source=root,edges=edge_weight_tpcTree) for root in RootTopics}
    #print("RootLGPDict",RootLGPDict)
    #print("node_df.columns",node_df.columns)
    node_df["LGPdepth"] = node_df.apply(
        lambda x:max([RootLGPDict[root][x.id] for root in RootTopics]),axis=1)
    degreeDict = CountDegree(edges=tpcTree)
    node_df["InDegree"] = node_df.apply(
        lambda x:degreeDict["In"][x.id],axis=1)
    node_df["OutDegree"] = node_df.apply(
        lambda x:degreeDict["Out"][x.id],axis=1)
    node_df["Degree"] = node_df.apply(
        lambda x:degreeDict["In_Out"][x.id],axis=1)
    #del degreeDict
    node_df["idc"] = node_df["id"]
    node_df=node_df.set_index("idc")
    tpcs_pars = BuildSubTopicsDict([[y,x] for [x,y] in tpcTree])
    node_df["ancestors"] = node_df.apply(lambda x:tuple(sorted(set([f"#T#{y}#T#" for y in 
        flattenList(tpcs_pars[x.id].values())]))), axis=1)
    node_df["category"] = node_df.apply(
        lambda x:setCategoryOfTopic(topic=x.id,ancestors=tpcs_pars),axis=1)
    InfoScoreTable = BuildInfoScoreTable(tpcTree = tpcTree)
    node_df["InfoScore"] = node_df.apply(lambda x:InfoScoreTable.get(x.id,0),axis=1)
    node_df["InfoScore_Level"] = node_df.apply(
        lambda x:
            80 if x.InfoScore >1000 else(
            60 if x.InfoScore > 500 else(
            40 if x.InfoScore > 300 else(
            20 if x.InfoScore > 100 else(
            1
            )))),
            axis=1)
    node_df["Positivity"] = node_df.apply(
        lambda x:
            "Pos" if x.InfoScore >50 else(
            "Neu" if x.InfoScore >-40 else(
            "Neg"
            )),
        axis=1)
    #為了便於快速有圖示找出Root，使用longestPath Depth，計算edge weight。
    edge_df["endpoint_LGPdepth_weight"] = edge_df.apply(
        #lambda x:node_df["depth"][x["from"]]+ node_df["depth"][x["to"]],
        lambda x:node_df["LGPdepth"][x["from"]]+ node_df["LGPdepth"][x["to"]],
        axis=1)
    '''
    #print("node_df['depth']",node_df["depth"])
    print("node_df['depth'][CN Strategy]",node_df["depth"]["CN Strategy"])
    print("node_df['depth'][CN Military]",node_df["depth"]["CN Military"])
    print("node_df['depth'][CN Military Administration]",node_df["depth"]["CN Military Administration"])
    print("node_df['LGPdepth'][CN Strategy]",node_df["LGPdepth"]["CN Strategy"])
    print("node_df['LGPdepth'][CN Military]",node_df["LGPdepth"]["CN Military"])
    print("node_df['LGPdepth'][CN Military Administration]",node_df["LGPdepth"]["CN Military Administration"])
    print(edge_df[edge_df["from"]=="CN Military"])
    '''
    node_df["ancestors"] = node_df["ancestors"].astype(str)
    node_df["category"] = node_df["category"].astype("category")
    #print("type(node_df)",type(node_df))
    #init Jaal and run server
    #edge_df, node_df = load_got()
    
    #QueryRoot = "CN Affairs"
    #QueryRoot = args.QueryRoot
    node_df = node_df.query(f'ancestors.str.contains("#T#{QueryRoot}#T#")')
    edge_df = edge_df.loc[edge_df["from"].isin(node_df["id"]) & edge_df["to"].isin(node_df["id"])]
    #print("edge_df",edge_df)
    #print("-"*50)
    #print("edge_df[strength]",edge_df["strength"])
    #print("-"*50)
    #print("node_df",node_df)
    #print("node_df.columns",node_df.columns)
    #print("-"*50)
    #print("node_df[category]",node_df["category"])
    #print("-"*50)
    #print("node_df[category][-10]",node_df["category"][-10])
    #print("-"*50)
    #print("node[infoscore]",node_df["InfoScore"])
    print("node[InfoScore] max",max(node_df["InfoScore"]))
    print("node[InfoScore] min",min(node_df["InfoScore"]))
    print("node[InfoScore_Level] max",max(node_df["InfoScore_Level"]))
    print("node[InfoScore_Level] min",min(node_df["InfoScore_Level"]))
    #print("node_df[ancestors]",node_df["ancestors"])
    from jaal import Jaal
    #https://visjs.github.io/vis-network/docs/network/layout.html#

    #help(Jaal.plot)
    print(f"# of nodes: {len(node_df)}")
    print(f"# of edges: {len(edge_df)}")
    #print(edge_df.loc[393,:])
    #print(node_df.columns)
    #print(node_df['depth'])
    #host = "223.140.14.10",
    #port = 7050,
    directed=True
    vis_opts={'height': '600px', # change height
              'interaction':{'hover': True}, # turn on-off the hover 
              'physics':{'stabilization':{'iterations': 100}},
              'layout':{
                  'hierarchical':{
                      'enabled':False,
                      #'enabled':True,
                      #'levelSeparation': 150,
                      'sortMethod':"directed",
                      },
                  }
              }
    if createMode == True:
        return Jaal(edge_df, node_df).create(
            #host = '0.0.0.0',
            host = hostIP,
            directed=directed,
            vis_opts=vis_opts,
            )
    else:
        Jaal(edge_df, node_df).plot(
            port = 8053,
            #host = '0.0.0.0',
            host = hostIP,
            directed=True,
            vis_opts=vis_opts,
            )

if __name__ == '__main__':
    args,__ = ClassfierOptionParser()
    if args.public == True:
        hostIP = '0.0.0.0'
    else:
        hostIP = '127.0.0.1'
    JaalViewMain(QueryRoot = args.QueryRoot,hostIP=hostIP)
