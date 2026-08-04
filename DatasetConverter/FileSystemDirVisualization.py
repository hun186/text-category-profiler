from tulip import tlp
from tulipgui import tlpgui

#from tulip import *
#from tulipogl import *
#from tulipgui import *

# get a dictionary filled with the default plugin parameters values
params = tlp.getDefaultPluginParameters('File System Directory')

# set any input parameter value if needed
params['directory'] = '../BOOKS'
#params['directory'] = r'..\Books\中國官方文件\#T#[PRC-OffDoc]\中华人民共和国国家发展和改革委员会'
params['directory'] = 'test For File System Show'
# params['include hidden files'] = ...
# params['follow symlinks'] = ...
# params['icons'] = ...
# params['tree layout'] = ...
# params['directory color'] = ...
# params['other color'] = ...

graph = tlp.importGraph('File System Directory', params)

viewLabel = graph.getStringProperty("viewLabel")

#for n in graph.getNodes():
  #viewLabel[n] = "Node " + str(n.id)
  
viewFont = graph.getStringProperty("viewFont")
#viewFont = "C:/Windows/Fonts/kaiu.ttf"
for n in graph.getNodes():
  viewFont[n] = "C:/Windows/Fonts/kaiu.ttf"

print("viewFont",viewFont)
# if the plugin declare any output parameter, its value can now be retrieved in the 'params' dictionary
nodelinkView = tlpgui.createNodeLinkDiagramView(graph)
#renderingParameters = nodelinkView.getRenderingParameters()

#nodeLinkView = tlp.createView("Node Link Diagram view", graph)

