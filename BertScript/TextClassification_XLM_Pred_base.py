import os
from transformers import pipeline 

finetuned_checkpoint = "./xlm-roberta-base-finetuned-marc-en/checkpoint-626"
finetuned_checkpoint = "./xlm-roberta-base-finetuned-marc-en/checkpoint-6"
classifier = pipeline(
    "text-classification", 
    model=finetuned_checkpoint,
    tokenizer=finetuned_checkpoint,
    truncation=True,max_length=180,
    )#, return_all_scores = True)

print(classifier("I loved reading the Hunger Games!"))
print("="*50)
print(classifier(["ハンガーゲーム」を読むのが好きだった!","I loved reading the Hunger Games!"]))
print("="*50)
print(classifier(["ハンガーゲーム」を読むのが好きだった!"]))
print("="*50)


datasetDir = "dataset"
testSet = []
test_result = []
with open(os.path.join(datasetDir,"test.tsv"),'rt',encoding='utf-8') as f:
    
    for line in f:
        sample = line.strip().split("\t")
        #testSet.append({"labels":label2id[sample[0]],"text":sample[1]})
        
        #print(pred_Type)
        testSet.append(sample[1])
#test_result.append(classifier(sample[1]))
test_result = classifier(testSet)
print(test_result)
with open(os.path.join(datasetDir, 'test_results.tsv'),'wt',encoding='utf-8') as f_ts_result:
    for pred_Type in test_result:
        f_ts_result.write(pred_Type['label']+"\n")

    