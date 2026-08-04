#from datasets import load_dataset
#imdb = load_dataset("imdb")
import os
from transformers import TFXLMRobertaModel
from transformers import AutoTokenizer

from transformers import pipeline

os.environ["WANDB_DISABLED"] = "true"

#model = TFXLMRobertaModel.from_pretrained("jplu/tf-xlm-roberta-base")
#model = TFXLMRobertaModel.from_pretrained("./jplu_tf-xlm-roberta-base")
#tokenizer = AutoTokenizer.from_pretrained("./jplu_tf-xlm-roberta-base")

#unmasker = pipeline('fill-mask', model='./xlm-roberta-base')
#print(unmasker("Hello I'm a <mask> model."))

'''
from transformers import AutoTokenizer, AutoModelForMaskedLM

tokenizer = AutoTokenizer.from_pretrained('./xlm-roberta-base')
model = AutoModelForMaskedLM.from_pretrained("./xlm-roberta-base")


# prepare input
text = "Replace me by any text you'd like."
encoded_input = tokenizer(text, return_tensors='pt')

# forward pass
output = model(**encoded_input)
print("="*50)
print("output",output)
print("="*50)
'''

#https://github.com/huggingface/workshops/blob/main/luzern-university/02-text-classification.ipynb
from datasets import get_dataset_config_names

dataset_name = "amazon_reviews_multi"
langs = get_dataset_config_names(dataset_name)
print("="*50)
print(langs)

from datasets import load_dataset

marc_en = load_dataset(path=dataset_name, name="en")
print("="*50)
print(marc_en)

# Peek at first element
print("marc_en[train][0]",marc_en["train"][0])





product_category = "book"

def filter_for_product(example, product_category=product_category):
    return example["product_category"] == product_category

product_dataset = marc_en.filter(filter_for_product)
print(product_dataset)



product_dataset["train"].shuffle(seed=42).select(range(3))[:]





label_names = ["terrible", "poor", "ok", "good", "great"]
id2label = {idx:label for idx, label in enumerate(label_names)}
print(id2label)



def map_labels(example):
    # Shift labels to start from 0
    label_id = example["stars"] - 1
    return {"labels": label_id, "label_name": id2label[label_id]}


product_dataset = product_dataset.map(map_labels)
# Peek at the first example
print(product_dataset["train"][0])

label2id = {v:k for k,v in id2label.items()}


from transformers import AutoTokenizer

model_checkpoint = "./xlm-roberta-base"
tokenizer = AutoTokenizer.from_pretrained(model_checkpoint)

print("tokenizer.vocab_size",tokenizer.vocab_size)
print("tokenizer.special_tokens_map",tokenizer.special_tokens_map)



encoded_str = tokenizer("Today I'm giving an NLP workshop at MLT")
print(encoded_str)


for token in encoded_str["input_ids"]:
    print(token, tokenizer.decode([token]))
    


def tokenize_reviews(examples):
    return tokenizer(examples["review_body"], truncation=True, max_length=180)


tokenized_dataset = product_dataset.map(tokenize_reviews, batched=True)
print(tokenized_dataset)

print("="*50)
print(tokenized_dataset["train"][0])

raise Exception

#Loading a pretrained model
from transformers import AutoModelForSequenceClassification

num_labels = 5
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

#用戶rate評分使用的metric，如:把五星誤判為兩星比起誤判為四星嚴重地多。
def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)
    return {"MAE": mean_absolute_error(labels, predictions)}

'''
def compute_metrics(pred):
    labels = pred.label_ids
    preds = pred.predictions.argmax(-1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average='binary')
    acc = accuracy_score(labels, preds)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }
'''

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

from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
import numpy as np

model = AutoModelForSequenceClassification.from_pretrained("./xlm-roberta-base")
tokenizer = AutoTokenizer.from_pretrained("./xlm-roberta-base")


input_pairs = [
               ("I like this pizza.", "The sentence is positive."),
               ("I like this pizza.", "The sentence is negative."),
               ("I mag diese Pizza.", "Der Satz ist positiv."),
               ("I mag diese Pizza.", "Der Satz ist negativ."),
               ("Me gusta esta pizza.", "Esta frase es positivo."),
               ("Me gusta esta pizza.", "Esta frase es negativo."),
]
inputs = tokenizer(input_pairs, truncation="only_first", return_tensors="pt", padding=True)
logits = model(**inputs, return_dict=True).logits
probs = torch.softmax(logits, dim=1)
probs = probs[..., [0]].tolist()
print("probs", probs)
np.testing.assert_almost_equal(probs, [[0.83], [0.04], [1.00], [0.00], [1.00], [0.00]], decimal=2)

'''
os.pause()