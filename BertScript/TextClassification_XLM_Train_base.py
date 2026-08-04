#from datasets import load_dataset
#imdb = load_dataset("imdb")
import os
from sklearn.metrics import precision_recall_fscore_support
from sklearn.metrics import accuracy_score
from transformers import TFXLMRobertaModel
from transformers import AutoTokenizer

from transformers import pipeline



from transformers import AutoTokenizer

model_checkpoint = "./xlm-roberta-base"
tokenizer = AutoTokenizer.from_pretrained(
    model_checkpoint,truncation=True, max_length=180)

#print("tokenizer.vocab_size",tokenizer.vocab_size)
#print("tokenizer.special_tokens_map",tokenizer.special_tokens_map)

#def tokenize_text(example):
#    return tokenizer(example["text"], truncation=True, max_length=180)
def tokenize_text(text):
    return tokenizer(text, truncation=True, max_length=180)


os.environ["WANDB_DISABLED"] = "true"


label_names = ["AUKUS", "Scrap","Uncertainty-Table Of Contents"]
id2label = {idx:label for idx, label in enumerate(label_names)}
print(id2label)

'''
def map_labels(example):
    # Shift labels to start from 0
    label_id = example["stars"] - 1
    return {"labels": label_id, "label_name": id2label[label_id]}

product_dataset = product_dataset.map(map_labels)
'''

label2id = {v:k for k,v in id2label.items()}

datasetDir = "dataset"

tokenized_dataset = {}
tokenized_dataset['train']=[]
tokenized_dataset['validation']=[]

#trainingSet = []
with open(os.path.join(datasetDir,"train.tsv"),encoding='utf-8') as f:
    for line in f:
        sample = line.strip().split("\t")
        tokenized_dataset['train'].append({"labels":label2id[sample[0]],"text":sample[1]})
#print("trainingSet",trainingSet)

for sample in tokenized_dataset['train']:
    #print("tokenize_text(sample['text'])",tokenize_text(sample['text']))
    sample.update(tokenize_text(sample['text']))
    del(sample['text'])
#tokenized_dataset['train'] = list(map(tokenize_text,tokenized_dataset['train']))
#print(tokenized_dataset['train'])

with open(os.path.join(datasetDir,"dev.tsv"),encoding='utf-8') as f:
    for line in f:
        sample = line.strip().split("\t")
        #trainingSet.append({"labels":label2id[sample[0]],"text":sample[1]})
        tokenized_dataset['validation'].append({"labels":label2id[sample[0]],"text":sample[1]})
#print("trainingSet",trainingSet)

#tokenized_dataset['validation'] = list(map(tokenize_text,tokenized_dataset['validation']))
#print(tokenized_dataset['train'])
for sample in tokenized_dataset['validation']:
    #print("tokenize_text(sample['text'])",tokenize_text(sample['text']))
    sample.update(tokenize_text(sample['text']))
    del(sample['text'])
print("="*50)
print(tokenized_dataset['train'][0])

#raise Exception

#Loading a pretrained model
from transformers import AutoModelForSequenceClassification

num_labels = len(label_names)
model = AutoModelForSequenceClassification.from_pretrained(model_checkpoint, num_labels=num_labels, label2id=label2id, id2label=id2label)



from transformers import TrainingArguments

model_name = model_checkpoint.split("/")[-1]
batch_size = 12
num_train_epochs = 2
logging_steps = len(tokenized_dataset["train"]) // (batch_size * num_train_epochs)

args = TrainingArguments(
    output_dir=f"{model_name}-finetuned-marc-en",
    evaluation_strategy = "epoch",
    save_strategy = "epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=batch_size,
    per_device_eval_batch_size=batch_size,
    num_train_epochs=num_train_epochs,
    weight_decay=0.01,
    logging_steps=logging_steps,
    #push_to_hub=True,
    #hub_token = 'token value',
)


import numpy as np
from sklearn.metrics import mean_absolute_error

'''
#用戶rate評分使用的metric，如:把五星誤判為兩星比起誤判為四星嚴重地多。
def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)
    return {"MAE": mean_absolute_error(labels, predictions)}

'''
def compute_metrics(pred):
    labels = pred.label_ids
    preds = pred.predictions.argmax(-1)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, preds, average='micro')
    acc = accuracy_score(labels, preds)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }


from transformers import Trainer 

trainer = Trainer(
    model,
    args,
    train_dataset=tokenized_dataset["train"],
    eval_dataset=tokenized_dataset["validation"],
    tokenizer=tokenizer,
    compute_metrics=compute_metrics
)

trainer.train()

#trainer.push_to_hub(commit_message="Training complete!")


'''
def evaluate_corpus(lang):
    # Load the language subset
    dataset = load_dataset(dataset_name, lang, split="validation")
    # Filter for the `sports` product category
    product_dataset = dataset.filter(filter_for_product)
    # Map and create label columns
    product_dataset = product_dataset.map(map_labels)
    # Tokenize the inputs
    tokenized_dataset = product_dataset.map(tokenize_reviews, batched=True)
    # Generate predictions and metrics
    preds = trainer.evaluate(eval_dataset=tokenized_dataset)
    return {"MAE": preds["eval_MAE"]}

evaluate_corpus("fr")
evaluate_corpus("ja")
'''


os.pause()