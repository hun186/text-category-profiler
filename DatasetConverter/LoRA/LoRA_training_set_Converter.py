import json
import random
import pprint
import os
import io
import sqlite3
from instructions_set import inst_templates

pp = pprint.PrettyPrinter(indent=4)

#TaskSet = {"Open Classifier"}
#TaskSet = {"Summarization"}
optFN = "trainingSet.json"
maxNInstPT = {
    "Open Classifier": 3000,
    "Summarization": 3000,
    "Keyword Extraction": 3000,
    }
nLeftJobDict = maxNInstPT
#optFN = optFN.replace(".json",f"_{sum(maxNInstPT.values())}samples_test.json")
InstanceOutputFormat = "TWLlama" #alpaca or TWLlama

src = {
       "Open Classifier":[
           #r"D:\shared\TopicClassification\WorkPool\dataset_20230911183631_PytorchXLM_pt8057_is_running_RunClassfier\train.sql3",
           ],
       "Summarization":[
           #漢斯出版社、ScientificResearch等爬蟲所獲文本
           #使用DataConverter_Combiner組裝成train.sql3格式
           r"dataset_summarization\中文摘要\漢斯出版社\train.sql3",
           r"dataset_summarization\英文摘要\ScientificResearch\train.sql3",
           #r"dataset_summarization\人工自標\train.sql3"
           r"dataset_summarization\人工自標\SummarizationTrain.sql3"
           
           ],
       "Keyword Extraction":[
           r"dataset_Keyword Extraction\漢斯出版社\train.sql3",
           ],
       }

for task in list(nLeftJobDict.keys()):
    #print('task',task)
    #print(src.get(task,[]))
    if len(src.get(task,[])) == 0:
        print(f"There is no source for task:{task}, remove this task.")
        nLeftJobDict.pop(task)
print("after check source setting, the left nLeftJobDict:",nLeftJobDict)

def BuildInstance(QueryPointer,instructions,
                  InstanceOutputFormat = "alpaca",idCounter = 0):
    #QueryPointer is a list as it accepts multiple soure
    QP = random.choice(QueryPointer)
    #print("type(QP)",type(QP))
    if isinstance(QP, io.IOBase):
        dataPT = QP.readline().split("\t")
    elif isinstance(QP, sqlite3.Cursor):
        #print(dir(QP))
        dataPT = QP.fetchone() #return a tuple
    if dataPT == None:
        return None,QP
    instPT = dict()
    if len(dataPT)>2:
        raise Exception
    instPT['instruction'] = random.choice(instructions)
    #print(dataPT)
    instPT['input'] = dataPT[1]
    #instPT['output'] = "#T#"+dataPT[0]+"#T#"
    instPT['output'] = dataPT[0]
    if InstanceOutputFormat == "TWLlama":
        instPT['instruction'] = "請摘要以上文章"
        instPT["id"] = f"identity_{idCounter}"
        instPT["conversations"] = [
            {
                "from":"human",
                "value":f"<article>{instPT['input']}</article>\n\n{instPT['instruction']}"
            },
            {
                "from":"gpt",
                "value":f"{instPT['output']}"
            },
        ]
        instPT.pop('input')
        instPT.pop('output')
        instPT.pop('instruction')
    return instPT,QP

def WriteSample(optFN,instPT):
    with open(optFN,'at',encoding='utf-8') as wf:
        global firstInstPTHasBeenWrited
        if firstInstPTHasBeenWrited:
            wf.write(",\n")
        json.dump(instPT,wf,indent=4,ensure_ascii=False)
        firstInstPTHasBeenWrited = True

def SaveInstPTList(instPTList,optFN):
    print(f"開始儲存樣本點清單，共計len(instPTList)筆樣本。")
    #open(optFN,'at',encoding='utf-8').write("]")
    random.shuffle(instPTList)
    optFN = "trainingSet.json"
    optFN = optFN.replace(".json",f"_{len(instPTList)}samples_test.json")
    if os.path.isfile(optFN):
        os.remove(optFN)
    
    with open(optFN,'at',encoding='utf-8') as wf:
        json.dump(instPTList,wf,indent=4,ensure_ascii=False)


def getQueryPointer(src):
    TaskSet = tuple(nLeftJobDict.keys())
    QueryPointerDict = dict()
    #取任務類型
    for task in TaskSet:
        #print("task",task)
        #獲取資料之來源
        #print("src[task]",src[task])
        if task not in src.keys():
            continue
        for file in src[task]:
            if os.path.isfile(file) is not True:
                print(f"WARNING! The file {file} does not exist. Check it please.")
                raise Exception
            if task not in QueryPointerDict:
                QueryPointerDict[task] = []
            if file.endswith(".tsv"):
                #print("file",file)
                QP = open(file,'rt',encoding='utf-8')
            elif file.endswith(".sql3"):
                #print("file",file)
                conn = sqlite3.connect(file)
                FilePath_query = 'SELECT OutLabel,text FROM sampleSrc;'
                QP = conn.execute(FilePath_query)
            QueryPointerDict[task].append(QP)
    #print("QueryPointerDict",QueryPointerDict)
    #raise Exception
    return QueryPointerDict
            
def buildLoRAtrainingSet(nLeftJobDict):
    nFinishedSampleDict = dict()
    #open(optFN,'wt',encoding='utf-8').write("[")
    global firstInstPTHasBeenWrited
    firstInstPTHasBeenWrited = False
    nInstPT = 0
    #print("task:",task)
    #print("inst_templates:",inst_templates)
    #print("Src:",src)
    #print("inst_templates[task]",inst_templates[task]["instructions"])
    QueryPointerDict = getQueryPointer(src)
    TaskSet = tuple(QueryPointerDict.keys())
    print("QueryPointerDict",QueryPointerDict)
    #print([type(x) for x in QueryPointerDict])
    instPTList = []
    while(len(nLeftJobDict.keys()) > 0):
        #print("TaskSet in while",TaskSet)
        #raise Exception
        task = random.choice(TaskSet)
        #print("task",task)
        #如果某子類型任務數量達標，則將鍵值自任務數量表中移除。
        if nLeftJobDict[task] == 0:
            print(f"{task}任務之取樣數量已遠最大目標。")
            nLeftJobDict.pop(task)
            print("TaskSet b4",TaskSet)
            TaskSet = tuple(nLeftJobDict.keys())
            print("TaskSet af",TaskSet)
            
            continue
        if task not in QueryPointerDict.keys():
            print(f"WARNING! There is no QueryPointer for {task}! Abort.")
            raise Exception
        instPT,ChosenQP = BuildInstance(
            QueryPointer=QueryPointerDict[task],
            instructions=inst_templates[task]["instructions"],
            InstanceOutputFormat=InstanceOutputFormat,
            idCounter=nInstPT)
        if instPT == None:
            QueryPointerDict[task].remove(ChosenQP)
            if QueryPointerDict[task] == []:
                #print("task",task)
                QueryPointerDict.pop(task)
                #print("nLeftJobDict b4",nLeftJobDict)
                nLeftJobDict.pop(task)
                #print("nLeftJobDict af",nLeftJobDict)
                #print("-"*50)
                #print("TaskSet b4",TaskSet)
                TaskSet = tuple(nLeftJobDict.keys())
                #print("TaskSet af",TaskSet)
            print("instPT is None, It might run out of this QP. Updated QueryPointerDict is", QueryPointerDict)
            continue
            #QueryPointerDict[task].remove()
            #print()
        instPTList.append(instPT)
        #WriteSample(optFN,instPT)
        #except Exception as e:
            #print(e)
        firstInstPTHasBeenWrited = True
        nInstPT += 1
        #print("nLeftJobDict",nLeftJobDict)
        nLeftJobDict[task] -= 1
        nFinishedSampleDict[task] = nFinishedSampleDict.get(task,0)+1

        if nInstPT % 10000 == 0:
            print(f"{nInstPT} instance point converted.")
    SaveInstPTList(instPTList,optFN)
    print(f"There are {nInstPT} samples already, quit.")
    print(f"已完成取樣數量如下：{nFinishedSampleDict}")
    
if __name__ == '__main__':
    buildLoRAtrainingSet(nLeftJobDict)
    