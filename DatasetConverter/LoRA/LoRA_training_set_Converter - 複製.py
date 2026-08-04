import json
import random
import pprint
import os
pp = pprint.PrettyPrinter(indent=4)

templatesList = json.loads(open("template_Classifier.json",encoding='utf-8').read())
#A = json.loads(open("instruction.json",encoding='utf-8').read())
#print(A[-10:])
#raise Exception
optFN = "instruction_#T#.json"
maxNInstPT = 10000
maxNInstPT = 1000000
optFN = optFN.replace(".json",f"_{maxNInstPT}samples.json")
open(optFN,'wt',encoding='utf-8').write("[")
firstInstPTHasBeenWrited = False

trPath = os.path.join(
    "dataset_20230601011014_PytorchXLM_pt8050_tr_is_running_RunClassfier","train.tsv")
#trPath = "train.tsv"
nInstPT = 0
#wf = open("instruction.json",'at',encoding='utf-8')
with open(trPath,'rt',encoding='utf-8') as f:
    for line in f:

        #print("="*50)
        dataPT = line.split("\t")
        if len(dataPT)>2:
            raise Exception
        instPT = random.choice(templatesList)
        instPT['output'] = "#T#"+dataPT[0]+"#T#"
        instPT['input'] = dataPT[1]
        #print(instPT)
        #try:

        with open(optFN,'at',encoding='utf-8') as wf:
            if firstInstPTHasBeenWrited:
                wf.write(",\n")
            json.dump(instPT,wf,indent=4,ensure_ascii=False)

        #except Exception as e:
            #print(e)
        firstInstPTHasBeenWrited = True
        nInstPT += 1
        if nInstPT % 10000 == 0:
            print(f"{nInstPT} instance point converted.")
            if nInstPT >= maxNInstPT:
                print(f"There are {nInstPT} samples already, quit.")
                break


open(optFN,'at',encoding='utf-8').write("]")