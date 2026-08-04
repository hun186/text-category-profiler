import os
import pandas as pd

dataSetPath = os.path.join("dataset", 'ChnSentiCorp_htl_all.csv')
all_data = pd.read_csv(dataSetPath, dtype=str)
all_data = all_data.applymap(lambda x: str(x).strip())
all_data = all_data.sample(frac=1).reset_index(drop=True)

train_data = all_data.iloc[:6212]
dev_data = all_data.iloc[6212:6989]
test_data = all_data.iloc[6989:]

#去除標題儲存。
train_data.to_csv('train.tsv', sep='\t', header=False, index=False)
dev_data.to_csv('dev.tsv', sep='\t', header=False, index=False)
test_data.to_csv('test.tsv', sep='\t', header=False, index=False)

